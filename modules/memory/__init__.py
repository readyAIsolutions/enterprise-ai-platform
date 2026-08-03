"""ENI Agent Memory OS Module.

A mem0-style hybrid long-term memory engine: dependency-free semantic /
episodic / declarative / procedural memory with per-user profiles,
deterministic feature-hash embeddings, relevance/importance/recency ranking,
consolidation & de-duplication, and persistent SQLite storage.

The module is a registered Platform Kernel module implementing the standard
lifecycle (``initialize`` / ``health_check`` / ``shutdown``) and the
event-bus wiring contract (``set_event_bus``).

Version: 1.0.0
Python: 3.11+
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from enterprise.platform_kernel import (
    EventBus,
    EventPriority,
    HealthStatus,
    Module,
    module,
)

from .memory import (
    DEFAULT_MEMORY_TYPE,
    MEMORY_TYPES,
    AgentMemory,
    HashEmbedder,
    MemoryContext,
    MemoryEntry,
    MemoryStore,
    ScoredMemory,
    cosine_similarity,
    dot,
    normalize,
)

__version__ = "1.0.0"
__module__ = "memory"

__all__ = [
    "__version__",
    "MemoryModule",
    # Core classes
    "AgentMemory",
    "MemoryStore",
    "MemoryEntry",
    "ScoredMemory",
    "MemoryContext",
    "HashEmbedder",
    # Helpers / constants
    "cosine_similarity",
    "dot",
    "normalize",
    "MEMORY_TYPES",
    "DEFAULT_MEMORY_TYPE",
]

_logger = logging.getLogger("enterprise.memory")


@module(name="memory", version="1.0.0")
class MemoryModule(Module):
    """Enterprise Agent Memory Module.

    Provides persistent, per-user long-term memory with semantic retrieval,
    de-duplication and consolidation. Wraps an :class:`~.AgentMemory` facade
    and exposes it through a clean Platform Kernel lifecycle.

    Configuration (dict passed to ``__init__``):
        database_path (str): SQLite database file path. Relative paths are
            resolved from the repository root. Defaults to
            ``"data/agent_memory.sqlite"``.
        embedding_dim (int): Embedding dimensionality for the default hash
            embedder (default 128).
        top_k (int): Default number of results returned by ``search`` when no
            ``k`` is supplied (default 5).
        max_per_type (int): Per-user/per-type consolidation cap (default 1000).
        similarity_threshold (float): Consolidation merge threshold (default 0.92).
        consolidate_on_search (bool): Run consolidation automatically after
            each write operation (default True).

    Events published (when an event bus is wired via ``set_event_bus``):
        - memory.added        — a memory was stored
        - memory.updated      — a memory was updated
        - memory.searched     — a search was performed
        - memory.deleted      — a memory was deleted
        - memory.forgotten    — memories were batch-forgotten
        - memory.consolidated — consolidation ran
    """

    DEFAULT_DB = "data/agent_memory.sqlite"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._memory: AgentMemory | None = None
        self._event_bus: EventBus | None = None
        self._lock = threading.RLock()
        self._embedding_dim: int = int(self._config.get("embedding_dim", 128) or 128)
        self._top_k: int = int(self._config.get("top_k", 5) or 5)
        self._max_per_type: int = int(self._config.get("max_per_type", 1000) or 1000)
        self._similarity_threshold: float = float(
            self._config.get("similarity_threshold", 0.92) or 0.92
        )
        self._consolidate_on_write: bool = bool(
            self._config.get("consolidate_on_write", True)
        )
        self._database_path: str = self._resolve_db_path(
            str(self._config.get("database_path") or self.DEFAULT_DB)
        )

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _resolve_db_path(raw: str) -> str:
        """Resolve a configured database path to an absolute path.

        ``:memory:`` is passed through unchanged; relative paths are resolved
        against the repository root (``platform_kernel``'s parent) so the
        default ``data/agent_memory.sqlite`` lands inside the repo.
        """
        if raw == ":memory:":
            return raw
        path = Path(raw)
        if path.is_absolute():
            return str(path)
        root = Path(__file__).resolve().parents[2]
        return str(root / path)

    # -- properties ---------------------------------------------------------

    @property
    def memory(self) -> AgentMemory | None:
        """Return the active AgentMemory facade, if initialized."""
        with self._lock:
            return self._memory

    @property
    def top_k(self) -> int:
        """Configured default retrieval result count."""
        return self._top_k

    @property
    def database_path(self) -> str:
        """Resolved SQLite database path."""
        return self._database_path

    # -- lifecycle ----------------------------------------------------------

    async def initialize(self) -> None:
        """Build the AgentMemory facade backed by SQLite persistence.

        On success the module status becomes :data:`HealthStatus.HEALTHY`;
        on failure it becomes :data:`HealthStatus.UNHEALTHY` and the error is
        re-raised so the platform can react.
        """
        with self._lock:
            self._status = HealthStatus.STARTING

        _logger.info(
            "Agent memory initializing (db=%s, dim=%s, top_k=%s)",
            self._database_path,
            self._embedding_dim,
            self._top_k,
        )
        try:
            if self._database_path != ":memory:":
                db_path = Path(self._database_path)
                db_path.parent.mkdir(parents=True, exist_ok=True)
            embedder = HashEmbedder(dim=self._embedding_dim)
            self._memory = AgentMemory(
                database_path=self._database_path, embedder=embedder
            )
            self._status = HealthStatus.HEALTHY
            _logger.info("Agent memory initialized successfully")
        except Exception as exc:
            _logger.exception("Failed to initialize agent memory: %s", exc)
            self._status = HealthStatus.UNHEALTHY
            raise

    async def health_check(self) -> HealthStatus:
        """Return the module health status.

        HEALTHY if the memory facade has been built, UNHEALTHY if
        initialization failed, UNKNOWN if never initialized.
        """
        with self._lock:
            if self._memory is not None and self._status is HealthStatus.HEALTHY:
                return HealthStatus.HEALTHY
            if self._status is HealthStatus.UNHEALTHY:
                return HealthStatus.UNHEALTHY
            self._status = HealthStatus.UNKNOWN
            return self._status

    async def shutdown(self) -> None:
        """Gracefully shut down the module, releasing the memory facade."""
        with self._lock:
            self._status = HealthStatus.STOPPING
            _logger.info("Shutting down agent memory module...")
            self._memory = None
            self._status = HealthStatus.HEALTHY

    # -- event bus wiring ---------------------------------------------------

    def set_event_bus(self, event_bus: EventBus) -> None:
        """Wire the platform EventBus into this module.

        Called by the Platform Kernel after module discovery but before
        ``initialize()``. If an event bus is already active it is replaced
        gracefully.
        """
        with self._lock:
            self._event_bus = event_bus

    def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        """Publish an event on the wired bus (no-op if none is set)."""
        bus = self._event_bus
        if bus is None:
            return
        try:
            from enterprise.platform_kernel import Event

            bus.publish(
                Event.create(
                    topic,
                    source=self.name,
                    payload=payload,
                    priority=EventPriority.NORMAL,
                )
            )
        except Exception as exc:  # pragma: no cover - defensive
            _logger.warning("Failed to publish event %s: %s", topic, exc)

    def _require_memory(self) -> AgentMemory:
        """Return the memory facade, raising if the module is not initialized."""
        memory = self._memory
        if memory is None:
            msg = "Agent memory module is not initialized"
            raise RuntimeError(msg)
        return memory

    def _maybe_consolidate(self, memory: AgentMemory) -> None:
        """Run consolidation after writes when enabled."""
        if not self._consolidate_on_write:
            return
        memory.consolidate(
            max_per_type=self._max_per_type,
            similarity_threshold=self._similarity_threshold,
        )

    # -- public operations --------------------------------------------------

    def remember(
        self,
        user_id: str,
        content: str,
        memory_type: str = DEFAULT_MEMORY_TYPE,
        metadata: dict[str, Any] | None = None,
        importance: float = 0.5,
    ) -> MemoryEntry:
        """Store a memory for a user and return the created entry.

        Emits ``memory.added`` on the event bus when available.
        """
        memory = self._require_memory()
        entry = memory.remember(
            user_id=user_id,
            content=content,
            memory_type=memory_type,
            metadata=metadata,
            importance=importance,
        )
        self._maybe_consolidate(memory)
        self._publish(
            "memory.added",
            {
                "id": entry.id,
                "user_id": entry.user_id,
                "memory_type": entry.memory_type,
            },
        )
        return entry

    def add(
        self,
        user_id: str,
        content: str,
        memory_type: str = DEFAULT_MEMORY_TYPE,
        metadata: dict[str, Any] | None = None,
        importance: float = 0.5,
    ) -> MemoryEntry:
        """Alias for :meth:`remember`."""
        return self.remember(
            user_id=user_id,
            content=content,
            memory_type=memory_type,
            metadata=metadata,
            importance=importance,
        )

    def search(
        self,
        query: str,
        k: int | None = None,
        user_id: str | None = None,
        memory_type: str | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[ScoredMemory]:
        """Search memories, returning the top-k ranked results.

        Emits ``memory.searched`` on the event bus when available.
        """
        memory = self._require_memory()
        limit = k if k is not None else self._top_k
        results = memory.search(
            query=query,
            k=limit,
            user_id=user_id,
            memory_type=memory_type,
            metadata_filter=metadata_filter,
        )
        self._publish(
            "memory.searched",
            {
                "query": query,
                "k": limit,
                "count": len(results),
                "user_id": user_id,
            },
        )
        return results

    def update(
        self,
        memory_id: str,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
        importance: float | None = None,
        memory_type: str | None = None,
    ) -> MemoryEntry | None:
        """Update an existing memory by id. Emits ``memory.updated``."""
        memory = self._require_memory()
        entry = memory.update(
            memory_id=memory_id,
            content=content,
            metadata=metadata,
            importance=importance,
            memory_type=memory_type,
        )
        if entry is not None:
            self._publish(
                "memory.updated",
                {"id": entry.id, "user_id": entry.user_id},
            )
        return entry

    def delete(self, memory_id: str) -> bool:
        """Delete a single memory by id. Emits ``memory.deleted``."""
        memory = self._require_memory()
        removed = memory.delete(memory_id)
        if removed:
            self._publish("memory.deleted", {"id": memory_id})
        return removed

    def forget(
        self,
        user_id: str | None = None,
        memory_type: str | None = None,
    ) -> int:
        """Batch-forget memories matching the given filters.

        Emits ``memory.forgotten`` on the event bus when available.
        """
        memory = self._require_memory()
        count = memory.forget(user_id=user_id, memory_type=memory_type)
        self._publish(
            "memory.forgotten",
            {"count": count, "user_id": user_id, "memory_type": memory_type},
        )
        return count

    def get(self, memory_id: str) -> MemoryEntry | None:
        """Return a single memory by id."""
        memory = self._require_memory()
        return memory.get(memory_id)

    def get_memories(
        self,
        user_id: str | None = None,
        memory_type: str | None = None,
    ) -> list[MemoryEntry]:
        """List memories, optionally scoped by user and/or type."""
        memory = self._require_memory()
        return memory.get_memories(user_id=user_id, memory_type=memory_type)

    def search_all(
        self,
        query: str,
        k: int | None = None,
        user_id: str | None = None,
        memory_types: list[str] | None = None,
    ) -> MemoryContext:
        """Return a ranked memory context blob for prompt injection."""
        memory = self._require_memory()
        limit = k if k is not None else self._top_k
        return memory.search_all(
            query=query, k=limit, user_id=user_id, memory_types=memory_types
        )

    def consolidate(
        self,
        max_per_type: int | None = None,
        similarity_threshold: float | None = None,
        user_id: str | None = None,
    ) -> dict[str, int]:
        """Run consolidation explicitly. Emits ``memory.consolidated``."""
        memory = self._require_memory()
        summary = memory.consolidate(
            max_per_type=max_per_type or self._max_per_type,
            similarity_threshold=(
                similarity_threshold
                if similarity_threshold is not None
                else self._similarity_threshold
            ),
            user_id=user_id,
        )
        self._publish("memory.consolidated", dict(summary))
        return summary
