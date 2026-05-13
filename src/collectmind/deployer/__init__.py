"""Downstream collection control plane clients."""

from collectmind.deployer.client import CollectorAIClient, DeployResponse
from collectmind.deployer.real_stub import RealCollectorAIClient
from collectmind.deployer.signing import LocalKeySigner
from collectmind.deployer.simulator import SimulatorCollectorAIClient

__all__ = [
    "CollectorAIClient",
    "DeployResponse",
    "LocalKeySigner",
    "RealCollectorAIClient",
    "SimulatorCollectorAIClient",
]
