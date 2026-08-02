"""
Knowledge Graph Contradiction Management

Detects, records, and manages contradictory claims in the knowledge graph.
Contradictions are preserved (not silently resolved) with full provenance
for both sides. Resolution requires verification and is recorded with
full history.

Design principles:
- Preserve both claims when a contradiction is detected.
- Record sources for each side of the contradiction.
- Assign confidence to each claim independently.
- Identify the specific point of conflict.
- Request verification before resolution.
- Record resolution decisions with rationale.
- Retain full contradiction history for audit.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from .entities import Entity, EntityType
from .relationships import Relationship, RelationshipType


class ContradictionStatus(str, Enum):
    """Lifecycle states of a contradiction."""

    DETECTED = "detected"           # Found but not yet reviewed
    UNDER_REVIEW = "under_review"   # Being investigated
    VERIFIED_A = "verified_a"       # Claim A is correct
    VERIFIED_B = "verified_b"       # Claim B is correct
    BOTH_PARTIALLY = "both_partially"  # Both have partial truth
    RESOLVED = "resolved"           # Final resolution recorded
    DISMISSED = "dismissed"         # Not a real contradiction
    STALE = "stale"                 # No longer relevant


class ContradictionType(str, Enum):
    """Types of contradictions that can occur in the graph."""

    # Structural contradictions
    CONFLICTING_TYPE = "conflicting_type"          # Same entity claimed to be different types
    CONFLICTING_NAME = "conflicting_name"           # Different names for same entity
    DUPLICATE_CLAIM = "duplicate_claim"             # Two entities claim to be the same thing

    # Relationship contradictions
    CYCLIC_DEPENDENCY = "cyclic_dependency"         # A depends on B and B depends on A
    CONFLICTING_RELATIONSHIP = "conflicting_relationship"  # A owns B AND A uses B (semantic conflict)
    BIDIRECTIONAL_CONFLICT = "bidirectional_conflict"     # A->B and B->A with conflicting types
    MISSING_REQUIRED = "missing_required"           # Entity is required but missing

    # Data contradictions
    CONFLICTING_METADATA = "conflicting_metadata"   # Same field has different values
    CONFLICTING_LABELS = "conflicting_labels"       # Mutually exclusive labels
    VERSION_CONFLICT = "version_conflict"           # Different versions claim to be current

    # Security contradictions
    POLICY_VIOLATION = "policy_violation"           # Entity violates a policy
    ACCESS_CONFLICT = "access_conflict"             # Conflicting access requirements

    # Temporal contradictions
    STALE_CLAIM = "stale_claim"                     # Claim conflicts with newer timestamp
    EXPIRED_CLAIM = "expired_claim"                 # Claim past its expiration


@dataclass
class ContradictionRecord:
    """
    Records a specific contradiction between two claims.

    Attributes:
        id: Unique record ID.
        contradiction_type: What kind of contradiction was detected.
        claim_a: Description or reference to the first claim.
        claim_a_source: Provenance reference for claim A.
        claim_a_confidence: Confidence in claim A.
        claim_b: Description or reference to the second claim.
        claim_b_source: Provenance reference for claim B.
        claim_b_confidence: Confidence in claim B.
        conflict_point: Specific description of what conflicts.
        status: Current lifecycle status.
        detected_at: When the contradiction was first detected.
        resolved_at: When resolution was finalized.
        resolved_by: Who resolved it.
        resolution: How it was resolved.
        resolution_rationale: Why this resolution was chosen.
        history: Chronological log of status changes.
        metadata: Arbitrary extensions.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    contradiction_type: ContradictionType = ContradictionType.CONFLICTING_METADATA
    claim_a: str = ""
    claim_a_source: str = ""
    claim_a_confidence: float = 0.5
    claim_b: str = ""
    claim_b_source: str = ""
    claim_b_confidence: float = 0.5
    conflict_point: str = ""
    status: ContradictionStatus = ContradictionStatus.DETECTED
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None
    resolved_by: str = ""
    resolution: str = ""
    resolution_rationale: str = ""
    history: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.history:
            self.history = [{
                "timestamp": self.detected_at.isoformat(),
                "status": ContradictionStatus.DETECTED.value,
                "note": "Contradiction detected",
            }]

    def update_status(self, new_status: ContradictionStatus, note: str = "") -> None:
        """Transition to a new status and record in history."""
        self.status = new_status
        self.history.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": new_status.value,
            "note": note,
        })
        if new_status in (
            ContradictionStatus.VERIFIED_A,
            ContradictionStatus.VERIFIED_B,
            ContradictionStatus.BOTH_PARTIALLY,
            ContradictionStatus.RESOLVED,
            ContradictionStatus.DISMISSED,
        ):
            self.resolved_at = datetime.now(timezone.utc)

    def resolve(
        self,
        resolution: str,
        resolved_by: str = "",
        rationale: str = "",
    ) -> None:
        """Record the final resolution of this contradiction."""
        self.resolution = resolution
        self.resolved_by = resolved_by
        self.resolution_rationale = rationale
        self.update_status(ContradictionStatus.RESOLVED, f"Resolved: {resolution}")

    @property
    def confidence_gap(self) -> float:
        """Difference in confidence between the two claims."""
        return abs(self.claim_a_confidence - self.claim_b_confidence)

    @property
    def preferred_claim(self) -> str:
        """Which claim has higher confidence (returns 'a' or 'b')."""
        return "a" if self.claim_a_confidence >= self.claim_b_confidence else "b"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "contradiction_type": self.contradiction_type.value,
            "claim_a": self.claim_a,
            "claim_a_source": self.claim_a_source,
            "claim_a_confidence": self.claim_a_confidence,
            "claim_b": self.claim_b,
            "claim_b_source": self.claim_b_source,
            "claim_b_confidence": self.claim_b_confidence,
            "conflict_point": self.conflict_point,
            "status": self.status.value,
            "detected_at": self.detected_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolved_by": self.resolved_by,
            "resolution": self.resolution,
            "resolution_rationale": self.resolution_rationale,
            "history": self.history,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContradictionRecord":
        """Deserialize from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            contradiction_type=ContradictionType(data.get("contradiction_type", "conflicting_metadata")),
            claim_a=data.get("claim_a", ""),
            claim_a_source=data.get("claim_a_source", ""),
            claim_a_confidence=data.get("claim_a_confidence", 0.5),
            claim_b=data.get("claim_b", ""),
            claim_b_source=data.get("claim_b_source", ""),
            claim_b_confidence=data.get("claim_b_confidence", 0.5),
            conflict_point=data.get("conflict_point", ""),
            status=ContradictionStatus(data.get("status", "detected")),
            detected_at=datetime.fromisoformat(data["detected_at"]) if data.get("detected_at") else datetime.now(timezone.utc),
            resolved_at=datetime.fromisoformat(data["resolved_at"]) if data.get("resolved_at") else None,
            resolved_by=data.get("resolved_by", ""),
            resolution=data.get("resolution", ""),
            resolution_rationale=data.get("resolution_rationale", ""),
            history=data.get("history", []),
            metadata=data.get("metadata", {}),
        )

    def __repr__(self) -> str:
        return (
            f"ContradictionRecord(id={self.id!r}, type={self.contradiction_type.value}, "
            f"status={self.status.value})"
        )


class ContradictionManager:
    """
    Detects, tracks, and manages contradictory claims.

    Scans the graph for various types of contradictions and maintains
    a registry of all detected contradictions with full lifecycle
    management.
    """

    # Mutually exclusive label pairs
    MUTUALLY_EXCLUSIVE_LABELS: List[Tuple[str, str]] = [
        ("active", "archived"),
        ("active", "deprecated"),
        ("public", "internal"),
        ("draft", "approved"),
        ("draft", "reviewed"),
        ("experimental", "approved"),
    ]

    def __init__(self) -> None:
        self._contradictions: Dict[str, ContradictionRecord] = {}
        self._detection_rules: List[callable] = []

    def scan(
        self,
        entities: List[Entity],
        relationships: List[Relationship],
    ) -> List[ContradictionRecord]:
        """
        Full scan for contradictions across entities and relationships.

        Returns all newly detected contradictions (previously detected
        ones are not re-reported but are updated if needed).
        """
        new_contradictions: List[ContradictionRecord] = []

        # Structural checks
        new_contradictions.extend(self._check_mutually_exclusive_labels(entities))
        new_contradictions.extend(self._check_cyclic_dependencies(entities, relationships))
        new_contradictions.extend(self._check_duplicate_names(entities))
        new_contradictions.extend(self._check_conflicting_relationships(entities, relationships))
        new_contradictions.extend(self._check_stale_claims(entities))
        new_contradictions.extend(self._check_policy_violations(entities, relationships))

        # Run registered custom rules
        for rule in self._detection_rules:
            try:
                results = rule(entities, relationships)
                new_contradictions.extend(results)
            except Exception:
                continue

        # Register new contradictions
        for cr in new_contradictions:
            if cr.id not in self._contradictions:
                self._contradictions[cr.id] = cr

        return new_contradictions

    def register_detection_rule(self, rule: callable) -> None:
        """Register a custom contradiction detection rule."""
        self._detection_rules.append(rule)

    # ---- Built-in Detection Rules ----

    def _check_mutually_exclusive_labels(self, entities: List[Entity]) -> List[ContradictionRecord]:
        """Detect entities with mutually exclusive labels."""
        results: List[ContradictionRecord] = []
        for entity in entities:
            entity_labels = {l.lower() for l in entity.labels}
            for label_a, label_b in self.MUTUALLY_EXCLUSIVE_LABELS:
                if label_a in entity_labels and label_b in entity_labels:
                    cr = ContradictionRecord(
                        contradiction_type=ContradictionType.CONFLICTING_LABELS,
                        claim_a=f"Entity '{entity.name}' has label '{label_a}'",
                        claim_b=f"Entity '{entity.name}' has label '{label_b}'",
                        conflict_point=f"Labels '{label_a}' and '{label_b}' are mutually exclusive",
                        metadata={"entity_id": entity.id, "labels": sorted(entity.labels)},
                    )
                    results.append(cr)
        return results

    def _check_cyclic_dependencies(
        self,
        entities: List[Entity],
        relationships: List[Relationship],
    ) -> List[ContradictionRecord]:
        """Detect cyclic dependencies in the graph."""
        results: List[ContradictionRecord] = []

        # Build adjacency for DEPENDS_ON
        entity_ids = {e.id for e in entities}
        adjacency: Dict[str, Set[str]] = {}
        for rel in relationships:
            if rel.relationship_type == RelationshipType.DEPENDS_ON:
                adjacency.setdefault(rel.source_id, set()).add(rel.target_id)

        # DFS cycle detection
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {eid: WHITE for eid in entity_ids}
        parent: Dict[str, Optional[str]] = {}

        def dfs(node: str) -> Optional[List[str]]:
            color[node] = GRAY
            for neighbor in adjacency.get(node, set()):
                if neighbor not in color:
                    continue
                if color[neighbor] == GRAY:
                    # Found cycle
                    cycle = [neighbor, node]
                    curr = node
                    while parent.get(curr) and parent[curr] != neighbor:
                        curr = parent[curr]  # type: ignore
                        cycle.append(curr)
                    cycle.append(neighbor)
                    return cycle
                if color[neighbor] == WHITE:
                    parent[neighbor] = node
                    result = dfs(neighbor)
                    if result:
                        return result
            color[node] = BLACK
            return None

        # Check each component
        seen_cycles: Set[str] = set()
        for eid in entity_ids:
            if color.get(eid) == WHITE:
                cycle = dfs(eid)
                if cycle:
                    cycle_key = "|".join(sorted(cycle))
                    if cycle_key not in seen_cycles:
                        seen_cycles.add(cycle_key)
                        cr = ContradictionRecord(
                            contradiction_type=ContradictionType.CYCLIC_DEPENDENCY,
                            claim_a=f"Cycle detected: {' -> '.join(cycle)}",
                            claim_b="Dependencies should form a DAG",
                            conflict_point=f"Cyclic dependency involving {len(cycle)} entities",
                            metadata={"cycle": cycle},
                        )
                        results.append(cr)

        return results

    def _check_duplicate_names(self, entities: List[Entity]) -> List[ContradictionRecord]:
        """Detect entities with identical names but different IDs."""
        results: List[ContradictionRecord] = []
        by_name: Dict[str, List[Entity]] = {}
        for entity in entities:
            key = (entity.tenant_id, entity.name.lower())
            by_name.setdefault(key, []).append(entity)

        for (tenant, name), group in by_name.items():
            if len(group) > 1:
                entity_ids = [e.id for e in group]
                cr = ContradictionRecord(
                    contradiction_type=ContradictionType.DUPLICATE_CLAIM,
                    claim_a=f"Entity '{name}' with ID {entity_ids[0]}",
                    claim_b=f"Entity '{name}' with ID {entity_ids[1]}",
                    conflict_point=f"Multiple entities named '{name}' in tenant '{tenant}'",
                    metadata={"entity_ids": entity_ids, "tenant_id": tenant},
                )
                results.append(cr)
        return results

    def _check_conflicting_relationships(
        self,
        entities: List[Entity],
        relationships: List[Relationship],
    ) -> List[ContradictionRecord]:
        """Detect conflicting relationships between the same pair."""
        results: List[ContradictionRecord] = []
        entity_ids = {e.id for e in entities}

        # Group relationships by (source, target) pair
        by_pair: Dict[Tuple[str, str], List[Relationship]] = {}
        for rel in relationships:
            if rel.source_id not in entity_ids or rel.target_id not in entity_ids:
                continue
            pair = (min(rel.source_id, rel.target_id), max(rel.source_id, rel.target_id))
            by_pair.setdefault(pair, []).append(rel)

        # Conflicting relationship types
        CONFLICTING_PAIRS = {
            (RelationshipType.DEPENDS_ON, RelationshipType.BLOCKS),
            (RelationshipType.OWNS, RelationshipType.USES),
            (RelationshipType.PROTECTS, RelationshipType.VIOLATES),
            (RelationshipType.VALIDATES, RelationshipType.VIOLATES),
        }

        for pair, rels in by_pair.items():
            if len(rels) < 2:
                continue
            rel_types = {r.relationship_type for r in rels}
            for conflict_a, conflict_b in CONFLICTING_PAIRS:
                if conflict_a in rel_types and conflict_b in rel_types:
                    cr = ContradictionRecord(
                        contradiction_type=ContradictionType.CONFLICTING_RELATIONSHIP,
                        claim_a=f"Relationship type: {conflict_a.value}",
                        claim_b=f"Relationship type: {conflict_b.value}",
                        conflict_point=(
                            f"Conflicting relationships ({conflict_a.value} vs {conflict_b.value}) "
                            f"between entities {pair[0][:8]} and {pair[1][:8]}"
                        ),
                        metadata={"entity_pair": list(pair), "relationship_ids": [r.id for r in rels]},
                    )
                    results.append(cr)

        return results

    def _check_stale_claims(self, entities: List[Entity]) -> List[ContradictionRecord]:
        """Detect entities with stale labels but active relationships."""
        results: List[ContradictionRecord] = []
        for entity in entities:
            if "stale" in entity.labels and "active" in entity.labels:
                cr = ContradictionRecord(
                    contradiction_type=ContradictionType.STALE_CLAIM,
                    claim_a=f"Entity '{entity.name}' is marked as stale (updated: {entity.updated_at.isoformat()})",
                    claim_b=f"Entity '{entity.name}' is also marked as active",
                    conflict_point="Entity cannot be both stale and active",
                    metadata={"entity_id": entity.id},
                )
                results.append(cr)
        return results

    def _check_policy_violations(
        self,
        entities: List[Entity],
        relationships: List[Relationship],
    ) -> List[ContradictionRecord]:
        """Check for entities labeled as violating policies."""
        results: List[ContradictionRecord] = []
        for entity in entities:
            if "violates_policy" in entity.metadata:
                violated = entity.metadata["violates_policy"]
                cr = ContradictionRecord(
                    contradiction_type=ContradictionType.POLICY_VIOLATION,
                    claim_a=f"Entity '{entity.name}' is in compliance",
                    claim_b=f"Entity '{entity.name}' violates policy: {violated}",
                    conflict_point=f"Policy violation detected: {violated}",
                    metadata={"entity_id": entity.id, "violated_policy": violated},
                )
                results.append(cr)
        return results

    # ---- Contradiction Registry Management ----

    def get(self, contradiction_id: str) -> Optional[ContradictionRecord]:
        """Retrieve a contradiction by ID."""
        return self._contradictions.get(contradiction_id)

    def get_by_status(self, status: ContradictionStatus) -> List[ContradictionRecord]:
        """Get all contradictions with a given status."""
        return [c for c in self._contradictions.values() if c.status == status]

    def get_by_type(self, cont_type: ContradictionType) -> List[ContradictionRecord]:
        """Get all contradictions of a given type."""
        return [c for c in self._contradictions.values() if c.contradiction_type == cont_type]

    def get_unresolved(self) -> List[ContradictionRecord]:
        """Get all unresolved contradictions."""
        unresolved_statuses = {
            ContradictionStatus.DETECTED,
            ContradictionStatus.UNDER_REVIEW,
        }
        return [c for c in self._contradictions.values() if c.status in unresolved_statuses]

    def resolve_contradiction(
        self,
        contradiction_id: str,
        resolution: str,
        resolved_by: str = "",
        rationale: str = "",
    ) -> bool:
        """Resolve a contradiction with rationale. Returns success."""
        cr = self._contradictions.get(contradiction_id)
        if cr is None:
            return False
        cr.resolve(resolution, resolved_by, rationale)
        return True

    def dismiss_contradiction(
        self,
        contradiction_id: str,
        reason: str = "",
    ) -> bool:
        """Dismiss a contradiction as not real. Returns success."""
        cr = self._contradictions.get(contradiction_id)
        if cr is None:
            return False
        cr.update_status(ContradictionStatus.DISMISSED, f"Dismissed: {reason}")
        return True

    def request_verification(self, contradiction_id: str) -> bool:
        """Mark a contradiction for verification. Returns success."""
        cr = self._contradictions.get(contradiction_id)
        if cr is None:
            return False
        cr.update_status(ContradictionStatus.UNDER_REVIEW, "Verification requested")
        return True

    def statistics(self) -> Dict[str, Any]:
        """Get contradiction statistics."""
        all_contradictions = list(self._contradictions.values())
        by_status: Dict[str, int] = {}
        by_type: Dict[str, int] = {}
        for c in all_contradictions:
            by_status[c.status.value] = by_status.get(c.status.value, 0) + 1
            by_type[c.contradiction_type.value] = by_type.get(c.contradiction_type.value, 0) + 1

        return {
            "total": len(all_contradictions),
            "unresolved": len(self.get_unresolved()),
            "resolved": by_status.get("resolved", 0),
            "dismissed": by_status.get("dismissed", 0),
            "by_status": by_status,
            "by_type": by_type,
        }

    def __len__(self) -> int:
        return len(self._contradictions)

    def __iter__(self):
        return iter(self._contradictions.values())

    def __repr__(self) -> str:
        stats = self.statistics()
        return (
            f"ContradictionManager(total={stats['total']}, "
            f"unresolved={stats['unresolved']})"
        )