"""
Knowledge Graph Relationships

Relationship model connecting entities with typed, versioned edges.
Every relationship carries provenance, direction, and optional
cardinality constraints for graph integrity.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


class RelationshipType(str, Enum):
    """All supported relationship types in the knowledge graph."""

    # Dependency & Implementation
    DEPENDS_ON = "DependsOn"
    IMPLEMENTS = "Implements"
    SUPERSEDES = "Supersedes"
    DERIVED_FROM = "DerivedFrom"
    BLOCKS = "Blocks"
    REQUIRES = "Requires"

    # Ownership & Responsibility
    OWNS = "Owns"
    CREATED_BY = "CreatedBy"
    UPDATED_BY = "UpdatedBy"
    APPROVED_BY = "ApprovedBy"

    # Usage & Interaction
    USES = "Uses"
    CALLS = "Calls"
    READS_FROM = "ReadsFrom"
    WRITES_TO = "WritesTo"
    EXPOSES = "Exposes"

    # Validation & Quality
    VALIDATES = "Validates"
    TESTED_BY = "TestedBy"
    MONITORED_BY = "MonitoredBy"
    AFFECTS = "Affects"

    # Security & Compliance
    PROTECTS = "Protects"
    VIOLATES = "Violates"
    CONFLICTS_WITH = "ConflictsWith"

    # Deployment & Operations
    DEPLOYED_TO = "DeployedTo"

    # Reference
    REFERENCES = "References"


# Inverse relationship mapping for bidirectional traversal
INVERSE_RELATIONSHIPS: Dict[RelationshipType, RelationshipType] = {
    RelationshipType.DEPENDS_ON: RelationshipType.REQUIRES,
    RelationshipType.REQUIRES: RelationshipType.DEPENDS_ON,
    RelationshipType.IMPLEMENTS: RelationshipType.VALIDATES,
    RelationshipType.SUPERSEDES: RelationshipType.SUPERSEDES,
    RelationshipType.OWNS: RelationshipType.CREATED_BY,
    RelationshipType.CREATED_BY: RelationshipType.OWNS,
    RelationshipType.USES: RelationshipType.EXPOSES,
    RelationshipType.EXPOSES: RelationshipType.USES,
    RelationshipType.READS_FROM: RelationshipType.WRITES_TO,
    RelationshipType.WRITES_TO: RelationshipType.READS_FROM,
    RelationshipType.DERIVED_FROM: RelationshipType.DERIVED_FROM,
    RelationshipType.CONFLICTS_WITH: RelationshipType.CONFLICTS_WITH,
    RelationshipType.CALLS: RelationshipType.EXPOSES,
    RelationshipType.UPDATED_BY: RelationshipType.CREATED_BY,
    RelationshipType.PROTECTS: RelationshipType.EXPOSES,
    RelationshipType.BLOCKS: RelationshipType.DEPENDS_ON,
    RelationshipType.VALIDATES: RelationshipType.TESTED_BY,
    RelationshipType.TESTED_BY: RelationshipType.VALIDATES,
    RelationshipType.APPROVED_BY: RelationshipType.OWNS,
    RelationshipType.VIOLATES: RelationshipType.VALIDATES,
    RelationshipType.DEPLOYED_TO: RelationshipType.OWNS,
    RelationshipType.REFERENCES: RelationshipType.REFERENCES,
    RelationshipType.MONITORED_BY: RelationshipType.EXPOSES,
    RelationshipType.AFFECTS: RelationshipType.AFFECTS,
}

# Valid source->target entity type pairs for each relationship type
# Format: (source_entity_types, target_entity_types)
RELATIONSHIP_CONSTRAINTS: Dict[RelationshipType, Tuple[Set[str], Set[str]]] = {
    RelationshipType.DEPENDS_ON: (
        {"Service", "API", "Project", "Feature", "Function", "Class", "Model", "Agent", "Tool"},
        {"Service", "API", "Database", "Infrastructure", "Repository", "Model", "Tool"},
    ),
    RelationshipType.IMPLEMENTS: (
        {"Service", "API", "Class", "Function", "Repository", "Model", "Tool"},
        {"Requirement", "UserStory", "Feature", "Policy", "Standard"},
    ),
    RelationshipType.OWNS: (
        {"User", "Organization", "Project", "Team"},
        {"*"},
    ),
    RelationshipType.USES: (
        {"*"},
        {"Service", "API", "Tool", "Model", "Agent", "Database", "Repository"},
    ),
    RelationshipType.CALLS: (
        {"Service", "API", "Function", "Agent", "Tool"},
        {"API", "Function", "Service"},
    ),
    RelationshipType.READS_FROM: (
        {"Service", "Function", "API", "Agent"},
        {"Database", "Table", "Field", "File", "Repository"},
    ),
    RelationshipType.WRITES_TO: (
        {"Service", "Function", "API", "Agent"},
        {"Database", "Table", "Field", "File", "Repository"},
    ),
    RelationshipType.SUPERSEDES: (
        {"*"},
        {"*"},
    ),
    RelationshipType.CONFLICTS_WITH: (
        {"*"},
        {"*"},
    ),
    RelationshipType.VALIDATES: (
        {"Test", "SecurityControl", "Policy", "Standard"},
        {"Service", "API", "Feature", "Requirement", "Infrastructure"},
    ),
    RelationshipType.VIOLATES: (
        {"Vulnerability", "Incident", "Risk"},
        {"Policy", "Standard", "SecurityControl"},
    ),
    RelationshipType.PROTECTS: (
        {"SecurityControl", "Policy"},
        {"Service", "API", "Database", "Infrastructure", "User"},
    ),
    RelationshipType.EXPOSES: (
        {"Service", "API", "Infrastructure"},
        {"API", "Service", "Database"},
    ),
    RelationshipType.REQUIRES: (
        {"*"},
        {"*"},
    ),
    RelationshipType.BLOCKS: (
        {"Risk", "Vulnerability", "Incident"},
        {"Project", "Feature", "Deployment", "Service"},
    ),
    RelationshipType.REFERENCES: (
        {"*"},
        {"Document", "ResearchSource", "Standard", "Policy"},
    ),
    RelationshipType.DERIVED_FROM: (
        {"*"},
        {"*"},
    ),
    RelationshipType.APPROVED_BY: (
        {"Decision", "Policy", "Standard", "Contract", "Deployment", "Requirement"},
        {"User", "Organization"},
    ),
    RelationshipType.DEPLOYED_TO: (
        {"Service", "Agent", "Model"},
        {"Infrastructure", "Deployment"},
    ),
    RelationshipType.MONITORED_BY: (
        {"Service", "API", "Infrastructure", "Database"},
        {"Service", "Tool", "Metric"},
    ),
    RelationshipType.TESTED_BY: (
        {"Service", "API", "Function", "Class", "Feature"},
        {"Test"},
    ),
    RelationshipType.AFFECTS: (
        {"Vulnerability", "Incident", "Risk", "Decision"},
        {"Service", "Project", "Product", "Customer", "User"},
    ),
    RelationshipType.CREATED_BY: (
        {"*"},
        {"User", "Organization", "Agent"},
    ),
    RelationshipType.UPDATED_BY: (
        {"*"},
        {"User", "Organization", "Agent"},
    ),
}


@dataclass
class Relationship:
    """
    A directed, typed edge between two entities in the knowledge graph.

    Attributes:
        id: Unique identifier for this relationship instance.
        source_id: Entity ID of the source (tail) node.
        target_id: Entity ID of the target (head) node.
        relationship_type: Type discriminator from RelationshipType.
        direction: 'forward' (source->target) or 'bidirectional'.
        weight: Edge weight for ranking/scoring (0.0-1.0).
        labels: Classification labels (same vocabulary as entity labels).
        metadata: Arbitrary key-value extensions.
        created_at: Timestamp of edge creation.
        updated_at: Timestamp of last modification.
        version: Monotonic version counter.
        tenant_id: Multi-tenant isolation key.
        provenance_id: Link to the provenance record for this relationship.
        confidence: Confidence score (0.0-1.0) from the provenance system.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_id: str = ""
    target_id: str = ""
    relationship_type: RelationshipType = RelationshipType.REFERENCES
    direction: str = "forward"  # forward, bidirectional
    weight: float = 0.5
    labels: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1
    tenant_id: str = "default"
    provenance_id: Optional[str] = None
    confidence: float = 0.5

    def __post_init__(self) -> None:
        """Validate and clamp values."""
        self.weight = max(0.0, min(1.0, self.weight))
        self.confidence = max(0.0, min(1.0, self.confidence))

    def touch(self) -> None:
        """Bump version and update timestamp."""
        self.updated_at = datetime.now(timezone.utc)
        self.version += 1

    def inverse(self) -> Relationship:
        """Return a new Relationship representing the inverse edge."""
        inv_type = INVERSE_RELATIONSHIPS.get(self.relationship_type, self.relationship_type)
        return Relationship(
            source_id=self.target_id,
            target_id=self.source_id,
            relationship_type=inv_type,
            direction=self.direction,
            weight=self.weight,
            labels=self.labels.copy(),
            metadata=self.metadata.copy(),
            tenant_id=self.tenant_id,
            provenance_id=self.provenance_id,
            confidence=self.confidence,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relationship_type": self.relationship_type.value,
            "direction": self.direction,
            "weight": self.weight,
            "labels": sorted(self.labels),
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "version": self.version,
            "tenant_id": self.tenant_id,
            "provenance_id": self.provenance_id,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Relationship":
        """Deserialize from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            source_id=data.get("source_id", ""),
            target_id=data.get("target_id", ""),
            relationship_type=RelationshipType(data["relationship_type"]),
            direction=data.get("direction", "forward"),
            weight=data.get("weight", 0.5),
            labels=set(data.get("labels", [])),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(timezone.utc),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(timezone.utc),
            version=data.get("version", 1),
            tenant_id=data.get("tenant_id", "default"),
            provenance_id=data.get("provenance_id"),
            confidence=data.get("confidence", 0.5),
        )

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Relationship):
            return NotImplemented
        return self.id == other.id

    def __repr__(self) -> str:
        return (
            f"Relationship(id={self.id!r}, "
            f"{self.source_id} -[{self.relationship_type.value}]-> {self.target_id})"
        )


class RelationshipRegistry:
    """
    Manages relationships with indexing for efficient graph traversal.

    Maintains forward (source->targets), reverse (target->sources), and
    type-based indices for O(1) lookups along common query paths.
    """

    def __init__(self) -> None:
        self._relationships: Dict[str, Relationship] = {}
        # source_id -> set of relationship ids
        self._by_source: Dict[str, Set[str]] = {}
        # target_id -> set of relationship ids
        self._by_target: Dict[str, Set[str]] = {}
        # (source_id, target_id, relationship_type) -> relationship_id
        self._by_triple: Dict[Tuple[str, str, str], str] = {}
        # relationship_type -> set of relationship ids
        self._by_type: Dict[RelationshipType, Set[str]] = {}

    def add(self, relationship: Relationship) -> Relationship:
        """Register a relationship and update all indices."""
        self._relationships[relationship.id] = relationship

        self._by_source.setdefault(relationship.source_id, set()).add(relationship.id)
        self._by_target.setdefault(relationship.target_id, set()).add(relationship.id)

        triple = (relationship.source_id, relationship.target_id, relationship.relationship_type.value)
        self._by_triple[triple] = relationship.id

        self._by_type.setdefault(relationship.relationship_type, set()).add(relationship.id)

        return relationship

    def create(
        self,
        source_id: str,
        target_id: str,
        relationship_type: RelationshipType,
        **kwargs: Any,
    ) -> Relationship:
        """Factory: create and register a relationship."""
        rel = Relationship(
            source_id=source_id,
            target_id=target_id,
            relationship_type=relationship_type,
            **kwargs,
        )
        return self.add(rel)

    def get(self, rel_id: str) -> Optional[Relationship]:
        """Retrieve a relationship by ID."""
        return self._relationships.get(rel_id)

    def get_by_triple(
        self,
        source_id: str,
        target_id: str,
        relationship_type: RelationshipType,
    ) -> Optional[Relationship]:
        """Find a relationship by source, target, and type."""
        triple = (source_id, target_id, relationship_type.value)
        rel_id = self._by_triple.get(triple)
        if rel_id:
            return self._relationships.get(rel_id)
        return None

    def find_outgoing(
        self,
        source_id: str,
        relationship_type: Optional[RelationshipType] = None,
    ) -> List[Relationship]:
        """Get all relationships originating from a source entity."""
        rel_ids = self._by_source.get(source_id, set())
        rels = [self._relationships[rid] for rid in rel_ids if rid in self._relationships]
        if relationship_type is not None:
            rels = [r for r in rels if r.relationship_type == relationship_type]
        return rels

    def find_incoming(
        self,
        target_id: str,
        relationship_type: Optional[RelationshipType] = None,
    ) -> List[Relationship]:
        """Get all relationships pointing to a target entity."""
        rel_ids = self._by_target.get(target_id, set())
        rels = [self._relationships[rid] for rid in rel_ids if rid in self._relationships]
        if relationship_type is not None:
            rels = [r for r in rels if r.relationship_type == relationship_type]
        return rels

    def find_neighbors(
        self,
        entity_id: str,
        relationship_type: Optional[RelationshipType] = None,
        max_depth: int = 1,
        direction: str = "both",  # outgoing, incoming, both
    ) -> List[Tuple[Relationship, str]]:
        """
        Find all neighboring relationships up to max_depth.

        Returns list of (relationship, neighbor_entity_id) tuples.
        """
        visited: Set[str] = {entity_id}
        frontier: Set[str] = {entity_id}
        results: List[Tuple[Relationship, str]] = []

        for _ in range(max_depth):
            next_frontier: Set[str] = set()
            for current_id in frontier:
                if direction in ("outgoing", "both"):
                    for rel in self.find_outgoing(current_id, relationship_type):
                        if rel.target_id not in visited:
                            results.append((rel, rel.target_id))
                            visited.add(rel.target_id)
                            next_frontier.add(rel.target_id)
                if direction in ("incoming", "both"):
                    for rel in self.find_incoming(current_id, relationship_type):
                        if rel.source_id not in visited:
                            results.append((rel, rel.source_id))
                            visited.add(rel.source_id)
                            next_frontier.add(rel.source_id)
            frontier = next_frontier
            if not frontier:
                break

        return results

    def find_paths(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 5,
    ) -> List[List[Relationship]]:
        """
        BFS pathfinding between two entities.

        Returns all paths (as lists of relationships) up to max_depth.
        """
        if source_id == target_id:
            return [[]]

        # BFS with path tracking
        queue: List[Tuple[str, List[Relationship]]] = [(source_id, [])]
        visited_paths: Set[str] = {source_id}
        all_paths: List[List[Relationship]] = []

        while queue:
            current, path = queue.pop(0)
            if len(path) >= max_depth:
                continue

            for rel in self.find_outgoing(current):
                if rel.id in {r.id for r in path}:
                    continue  # avoid cycles
                new_path = path + [rel]
                if rel.target_id == target_id:
                    all_paths.append(new_path)
                elif rel.target_id not in visited_paths or len(new_path) < max_depth:
                    visited_paths.add(rel.target_id)
                    queue.append((rel.target_id, new_path))

        return all_paths

    def remove(self, rel_id: str) -> bool:
        """Remove a relationship and clean up indices."""
        rel = self._relationships.pop(rel_id, None)
        if rel is None:
            return False
        self._by_source.get(rel.source_id, set()).discard(rel_id)
        self._by_target.get(rel.target_id, set()).discard(rel_id)
        triple = (rel.source_id, rel.target_id, rel.relationship_type.value)
        self._by_triple.pop(triple, None)
        self._by_type.get(rel.relationship_type, set()).discard(rel_id)
        return True

    def remove_by_entity(self, entity_id: str) -> int:
        """Remove all relationships involving an entity. Returns count removed."""
        outgoing_ids = list(self._by_source.get(entity_id, set()))
        incoming_ids = list(self._by_target.get(entity_id, set()))
        all_ids = set(outgoing_ids + incoming_ids)
        count = 0
        for rel_id in all_ids:
            if self.remove(rel_id):
                count += 1
        return count

    def __len__(self) -> int:
        return len(self._relationships)

    def __iter__(self):
        return iter(self._relationships.values())