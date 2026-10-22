"""Local persistent memory foundation for IRIS.

This package is intentionally not integrated into the brain or terminal yet.
"""

from iris.memory.models import (
    MemoryCandidate, MemoryCategory, MemoryConfirmation, MemoryItem,
    MemorySensitivity, MemoryStatus,
)
from iris.memory.policy import MemoryPolicyDecision, MemoryWriteAction, decide_write
from iris.memory.redaction import MemoryRedactionError, contains_secret, reject_secrets
from iris.memory.store import DEFAULT_MEMORY_PATH, MemoryStore, SCHEMA_VERSION
from iris.memory.retrieval import MemoryRetriever, retrieve_memories, search_memories
from iris.memory.context import MemoryContext, MemoryContextMode, build_context

__all__ = [
    "DEFAULT_MEMORY_PATH", "MemoryCandidate", "MemoryCategory", "MemoryConfirmation",
    "MemoryItem", "MemoryPolicyDecision", "MemoryRedactionError", "MemorySensitivity",
    "MemoryStatus", "MemoryStore", "MemoryWriteAction", "SCHEMA_VERSION",
    "contains_secret", "decide_write", "reject_secrets",
    "MemoryContext", "MemoryContextMode", "MemoryRetriever", "build_context",
    "search_memories",
    "retrieve_memories",
]
