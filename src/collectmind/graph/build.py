"""LangGraph composition (T084). Wires the four nodes with retry routing."""

from __future__ import annotations

from dataclasses import dataclass

from collectmind.graph.orchestrator import Orchestrator
from collectmind.graph.policy_deployer import PolicyDeployer
from collectmind.graph.policy_generator import PolicyGenerator
from collectmind.graph.policy_validator import PolicyValidatorNode
from collectmind.graph.session import PolicyGenerationSession


@dataclass
class GraphRun:
    session: PolicyGenerationSession
    final_state: str  # "completed" | "dead_letter"
    validation_attempts: int


class CollectMindGraph:
    """Synchronous graph runner. Honors Principle XII (bounded retry, dead-letter)."""

    def __init__(
        self,
        generator: PolicyGenerator,
        validator: PolicyValidatorNode,
        deployer: PolicyDeployer,
        orchestrator: Orchestrator | None = None,
    ) -> None:
        self._orchestrator = orchestrator or Orchestrator()
        self._generator = generator
        self._validator = validator
        self._deployer = deployer

    def run(self, session: PolicyGenerationSession) -> GraphRun:
        session = self._orchestrator.initial_plan(session)
        attempts = 0
        while True:
            attempts += 1
            self._generator.generate(session)
            result = self._validator.validate(session)
            decision = self._orchestrator.route_after_validation(session, result.ok)
            if decision == "deploy":
                break
            if decision == "dead_letter":
                return GraphRun(session=session, final_state="dead_letter", validation_attempts=attempts)
            # decision == "retry"
            continue

        record = self._deployer.deploy(session)
        deploy_ok = record.get("status") == "accepted"
        final = self._orchestrator.route_after_deploy(deploy_ok)
        return GraphRun(
            session=session,
            final_state="completed" if final == "done" else "dead_letter",
            validation_attempts=attempts,
        )
