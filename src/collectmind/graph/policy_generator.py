"""Policy Generator node (T081). Calls injected PolicyGeneratorClient."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from collectmind.graph.session import PolicyGenerationSession
from collectmind.models.policy import CollectionPolicySpec
from collectmind.slm.client import GenerationRequest, PolicyGeneratorClient


def _prompt_dir() -> Path:
    here = Path(__file__).resolve()
    container = here.parent.parent.parent / "prompts" / "policy_generator" / "v1.0.0"
    if container.exists():
        return container
    return here.parents[3] / "prompts" / "policy_generator" / "v1.0.0"


_PROMPT_DIR = _prompt_dir()
_DEFAULT_DECODING_SEED = 0xC0FFEE


class _PromptRenderer(Protocol):
    def render(self, session: PolicyGenerationSession) -> str: ...


def _render_prompt(session: PolicyGenerationSession) -> str:
    """Minimal in-process prompt renderer; the full Jinja path lands in feature 005."""
    system = (_PROMPT_DIR / "system.md").read_text(encoding="utf-8")
    user_template = (_PROMPT_DIR / "user.md").read_text(encoding="utf-8")
    finding = session.originating_finding
    rendered = (
        user_template.replace("{{ tenant_id }}", session.tenant_id)
        .replace("{{ finding_id }}", finding.get("finding_id", ""))
        .replace("{{ anomaly_type }}", finding.get("anomaly_type", ""))
        .replace("{{ hypothesis_class }}", finding.get("hypothesis_class", ""))
        .replace("{{ hypothesis_statement }}", finding.get("hypothesis_statement", ""))
        .replace("{{ vehicle_scope_json }}", json.dumps(finding.get("vehicle_scope", [])))
        .replace("{{ candidate_signals_json }}", json.dumps(finding.get("candidate_signals", [])))
        .replace("{{ upstream_confidence }}", str(finding.get("upstream_confidence", 0.0)))
        .replace("{{ session_id }}", session.session_id)
    )
    if "{% if retry_context %}" in rendered:
        # Strip the optional block in the simple renderer if no retry context.
        if not session.validation_errors:
            start = rendered.index("{% if retry_context %}")
            end = rendered.index("{% endif %}") + len("{% endif %}")
            rendered = rendered[:start] + rendered[end:]
        else:
            rendered = (
                rendered.replace("{% if retry_context %}", "")
                .replace("{% endif %}", "")
                .replace(
                    "{{ retry_context_json }}",
                    json.dumps({"validation_errors": session.validation_errors}, indent=2),
                )
            )
    return f"{system}\n\n{rendered}"


class PolicyGenerator:
    def __init__(self, client: PolicyGeneratorClient) -> None:
        self._client = client

    def generate(self, session: PolicyGenerationSession) -> dict[str, Any]:
        prompt = _render_prompt(session)
        request = GenerationRequest(
            session_id=session.session_id,
            prompt_template_version=session.prompt_template_version,
            prompt=prompt,
            schema=CollectionPolicySpec.model_json_schema(),
            decoding={"temperature": 0.0, "top_p": 1.0, "top_k": -1, "seed": _DEFAULT_DECODING_SEED},
            retry_context={"validation_errors": session.validation_errors} if session.validation_errors else None,
        )
        response = self._client.generate(request)
        session.generated_policy = response.policy
        session.last_runtime_info = response.runtime_info
        session.last_decoding_seed = _DEFAULT_DECODING_SEED
        return response.policy
