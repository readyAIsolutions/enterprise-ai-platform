"""
Knowledge Graph OS Module

Enterprise-grade knowledge graph for mapping and managing organizational
knowledge: entities, relationships, provenance, resolution, contradiction
management, and secure retrieval.

Version: 1.0.0
"""

__version__ = "1.0.0"
__all__ = [
    # Entities
    "Entity",
    "EntityType",
    "EntityRegistry",
    # Relationships
    "Relationship",
    "RelationshipType",
    "RelationshipRegistry",
    # Ingestion
    "IngestionPipeline",
    "IngestionSource",
    "IngestionResult",
    # Provenance
    "Provenance",
    "ProvenanceChain",
    "SourceType",
    "ConfidenceLevel",
    # Resolution
    "EntityResolver",
    "ResolutionStrategy",
    "ResolutionResult",
    # Contradiction
    "ContradictionManager",
    "ContradictionRecord",
    "ContradictionStatus",
    # Retrieval
    "GraphQueryEngine",
    "QueryBuilder",
    "QueryResult",
    # Security
    "GraphSecurityManager",
    "AccessPolicy",
    "AuditLogger",
    "KGTestCaseEntity",
    # Persistence
    "KGPersistence",
    "create_persistence",
]

# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# Kernel lifecycle registration -- makes this OS module discoverable by the
# ENI Platform Kernel for initialize/health_check/shutdown orchestration.
# --------------------------------------------------------------------------
import asyncio  # noqa: F401
import logging
import threading
from typing import Any, Dict, Optional  # noqa: F401

from enterprise.platform_kernel import HealthStatus, Module, module

from .contradiction import ContradictionManager, ContradictionRecord, ContradictionStatus
from .entities import Entity, EntityRegistry, EntityType, KGTestCaseEntity
from .ingestion import IngestionPipeline, IngestionResult, IngestionSource
from .persistence import KGPersistence, create_persistence
from .provenance import ConfidenceLevel, Provenance, ProvenanceChain, SourceType
from .relationships import Relationship, RelationshipRegistry, RelationshipType
from .resolution import EntityResolver, ResolutionResult, ResolutionStrategy
from .retrieval import GraphQueryEngine, QueryBuilder, QueryResult
from .security import AccessPolicy, AuditLogger, GraphSecurityManager

_KERNEL_VERSION = globals().get("__version__", "1.0.0")


_logger = logging.getLogger("enterprise.knowledge_graph")


@module(name="knowledge_graph", version=_KERNEL_VERSION)
class KnowledgeGraphModule(Module):
    """Kernel-managed wrapper around the knowledge_graph OS module.

    Wraps the most representative entrypoint (EntityRegistry) so the platform kernel
    can initialize it, probe its health, and shut it down as part of the ENI
    lifecycle. If the core component cannot be instantiated the module reports
    UNHEALTHY rather than crashing the platform.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        cfg = config or {}
        self._lock = threading.RLock()
        self._component = None
        self._init_error = None
        # Durable SQLite persistence. db_path=None => in-memory; a directory
        # or file path enables durable storage. Defaults to data/ under the
        # enterprise repo root.
        db_path = cfg.get("db_path", "data")
        self.persistence: KGPersistence | None = None
        try:
            self.persistence = create_persistence(None if db_path is None else db_path)
        except Exception as e:  # pragma: no cover - degrade gracefully
            _logger.warning("%s persistence init failed: %s", self.name, e)
            self.persistence = None

    async def initialize(self) -> None:
        with self._lock:
            self._status = HealthStatus.STARTING
            try:
                self._component = EntityRegistry()
                self._status = HealthStatus.HEALTHY
                _logger.info("%s module initialized", self.name)
            except Exception as e:  # pragma: no cover - degrade gracefully
                self._init_error = str(e)
                self._status = HealthStatus.UNHEALTHY
                _logger.warning("%s module failed to initialize: %s", self.name, e)

    async def health_check(self) -> HealthStatus:
        with self._lock:
            if self._component is None:
                return HealthStatus.UNHEALTHY if self._init_error else HealthStatus.DEGRADED
            try:
                if not hasattr(self._component, "_entities"):
                    return HealthStatus.DEGRADED
                return HealthStatus.HEALTHY
            except Exception as e:  # pragma: no cover
                _logger.warning("%s health probe failed: %s", self.name, e)
                return HealthStatus.DEGRADED

    async def shutdown(self) -> None:
        with self._lock:
            self._status = HealthStatus.STOPPING
            self._component = None
            self._init_error = None


def create_knowledge_graph_module(config: dict[str, Any] | None = None) -> KnowledgeGraphModule:
    """Factory: create a knowledge_graph module instance."""
    return KnowledgeGraphModule(config)
