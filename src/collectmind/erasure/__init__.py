"""GDPR/CCPA right-to-erasure (FR-020a)."""

from collectmind.erasure.api import router
from collectmind.erasure.dispatcher import ErasureDispatcher

__all__ = ["ErasureDispatcher", "router"]
