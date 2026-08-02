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
]

from .entities import Entity, EntityType, EntityRegistry, KGTestCaseEntity
from .relationships import Relationship, RelationshipType, RelationshipRegistry
from .ingestion import IngestionPipeline, IngestionSource, IngestionResult
from .provenance import Provenance, ProvenanceChain, SourceType, ConfidenceLevel
from .resolution import EntityResolver, ResolutionStrategy, ResolutionResult
from .contradiction import ContradictionManager, ContradictionRecord, ContradictionStatus
from .retrieval import GraphQueryEngine, QueryBuilder, QueryResult
from .security import GraphSecurityManager, AccessPolicy, AuditLogger