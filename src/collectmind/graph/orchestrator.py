"""Orchestrator node (T080). Routes on validation outcome; enforces retry budget."""

from __future__ import annotations

from typing import Literal

from collectmind.graph.session import PolicyGenerationSession
from collectmind.observability.metrics import policy_retry_total


RouteDecision = Literal["generate", "validate", "deploy", "retry", "dead_letter", "done"]


class Orchestrator:
    """Reads diagnostic input, writes execution plan, routes."""

    def initial_plan(self, session: PolicyGenerationSession) -> PolicyGenerationSession:
        session.execution_plan = ["generate", "validate", "deploy"]
        return session

    def route_after_validation(self, session: PolicyGenerationSession, valid: bool) -> RouteDecision:
        if valid:
            return "deploy"
        if session.retry_budget_exhausted():
            return "dead_letter"
        session.retry_count += 1
        policy_retry_total.labels(tenant_id=session.tenant_id).inc()
        return "retry"

    def route_after_deploy(self, deploy_ok: bool) -> RouteDecision:
        return "done" if deploy_ok else "dead_letter"
