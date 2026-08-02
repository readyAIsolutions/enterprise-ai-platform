"""
Knowledge Graph Entity Resolution

Resolves duplicate entities through multi-strategy matching:
exact names, aliases, fuzzy similarity, renamed components,
forked repositories, replaced systems, and conflicting identifiers.

Design principles:
- Never merge without sufficient confidence.
- Preserve all identities; merging is a separate explicit step.
- Support multiple resolution strategies with configurable thresholds.
- Track resolution decisions with provenance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from .entities import Entity, EntityRegistry, EntityType


class ResolutionStrategy(str, Enum):
    """Strategies for resolving entity identity."""

    EXACT_NAME = "exact_name"               # Case-insensitive exact name match
    ALIAS_MATCH = "alias_match"             # One entity's name matches another's alias
    FUZZY_NAME = "fuzzy_name"               # Name similarity above threshold
    COMMON_IDENTIFIER = "common_identifier" # Shared external ID (email, CVE, etc.)
    RENAMED_COMPONENT = "renamed_component" # Detected rename via metadata
    FORKED_REPOSITORY = "forked_repository" # Fork relationship
    REPLACED_SYSTEM = "replaced_system"     # Explicit replacement/supersede
    TRANSITIVE = "transitive"               # A == B and B == C implies A == C
    SAME_STRUCTURE = "same_structure"       # Identical internal structure


@dataclass
class ResolutionCandidate:
    """
    A potential duplicate match between two entities.

    Attributes:
        entity_a: First entity.
        entity_b: Second entity.
        strategy: Which resolution strategy produced this match.
        confidence: How confident we are that these are the same entity (0.0-1.0).
        evidence: Why the strategy believes they match.
    """

    entity_a: Entity
    entity_b: Entity
    strategy: ResolutionStrategy
    confidence: float
    evidence: str = ""

    def __post_init__(self) -> None:
        self.confidence = max(0.0, min(1.0, self.confidence))

    @property
    def is_high_confidence(self) -> bool:
        return self.confidence >= 0.80

    def __repr__(self) -> str:
        return (
            f"ResolutionCandidate({self.entity_a.name} ~ {self.entity_b.name}, "
            f"strategy={self.strategy.value}, confidence={self.confidence:.2f})"
        )


@dataclass
class ResolutionResult:
    """
    Outcome of a resolution attempt between two entities.

    Attributes:
        candidate: The candidate match that was evaluated.
        merged: Whether the entities were actually merged.
        surviving_entity_id: ID of the entity that remains after merge.
        absorbed_entity_id: ID of the entity that was absorbed (if merged).
        reason: Explanation of the resolution decision.
    """

    candidate: ResolutionCandidate
    merged: bool = False
    surviving_entity_id: str = ""
    absorbed_entity_id: str = ""
    reason: str = ""

    def __repr__(self) -> str:
        status = "merged" if self.merged else "kept_separate"
        return f"ResolutionResult({status}: {self.reason})"


class EntityResolver:
    """
    Resolves duplicate entities through multiple strategies.

    The resolver identifies potential duplicates but does NOT merge
    without confidence. It generates ResolutionCandidates which can
    be reviewed and acted upon.

    Usage:
        resolver = EntityResolver(registry)
        candidates = resolver.find_duplicates(entity)
        for candidate in candidates:
            if candidate.is_high_confidence:
                result = resolver.resolve(candidate.entity_a, candidate.entity_b)
    """

    # Default confidence thresholds per strategy
    DEFAULT_THRESHOLDS: Dict[ResolutionStrategy, float] = {
        ResolutionStrategy.EXACT_NAME: 0.95,
        ResolutionStrategy.ALIAS_MATCH: 0.85,
        ResolutionStrategy.FUZZY_NAME: 0.70,
        ResolutionStrategy.COMMON_IDENTIFIER: 0.90,
        ResolutionStrategy.RENAMED_COMPONENT: 0.75,
        ResolutionStrategy.FORKED_REPOSITORY: 0.65,
        ResolutionStrategy.REPLACED_SYSTEM: 0.90,
        ResolutionStrategy.TRANSITIVE: 0.60,
        ResolutionStrategy.SAME_STRUCTURE: 0.70,
    }

    def __init__(
        self,
        registry: Optional[EntityRegistry] = None,
        thresholds: Optional[Dict[ResolutionStrategy, float]] = None,
        auto_merge_threshold: float = 0.95,
    ) -> None:
        self.registry = registry or EntityRegistry()
        self.thresholds = {**self.DEFAULT_THRESHOLDS, **(thresholds or {})}
        self.auto_merge_threshold = auto_merge_threshold

        # Track resolution history
        self._resolved_pairs: Set[Tuple[str, str]] = set()
        self._merge_history: List[ResolutionResult] = []

    def find_duplicates(
        self,
        entity: Entity,
        candidates: Optional[List[Entity]] = None,
    ) -> List[ResolutionCandidate]:
        """
        Find potential duplicates for an entity across all strategies.

        Args:
            entity: The entity to find duplicates for.
            candidates: Optional pool of entities to search (default: all in registry).

        Returns:
            List of ResolutionCandidates sorted by confidence descending.
        """
        if candidates is None:
            candidates = [
                e for e in self.registry
                if e.id != entity.id and e.tenant_id == entity.tenant_id
            ]

        results: List[ResolutionCandidate] = []

        for other in candidates:
            if other.id == entity.id:
                continue
            pair_key = self._pair_key(entity.id, other.id)
            if pair_key in self._resolved_pairs:
                continue

            # Try each strategy
            for strategy in ResolutionStrategy:
                match = self._try_strategy(strategy, entity, other)
                if match and match.confidence >= self.thresholds.get(strategy, 0.5):
                    results.append(match)

        results.sort(key=lambda r: -r.confidence)
        return results

    def resolve(self, entity_a: Entity, entity_b: Entity) -> ResolutionResult:
        """
        Attempt to resolve and merge two entities.

        Only merges if the highest-confidence strategy exceeds the
        auto-merge threshold. Otherwise, records the candidate but
        keeps entities separate.

        Returns:
            ResolutionResult describing the outcome.
        """
        candidates = self.find_duplicates(entity_a, [entity_b])
        if not candidates:
            result = ResolutionResult(
                candidate=ResolutionCandidate(
                    entity_a=entity_a,
                    entity_b=entity_b,
                    strategy=ResolutionStrategy.EXACT_NAME,
                    confidence=0.0,
                    evidence="No matching strategy found",
                ),
                merged=False,
                reason="No matching resolution strategy",
            )
            self._record_result(entity_a.id, entity_b.id, result)
            return result

        best = candidates[0]

        if best.confidence >= self.auto_merge_threshold:
            surviving, absorbed = self._merge(entity_a, entity_b, best)
            result = ResolutionResult(
                candidate=best,
                merged=True,
                surviving_entity_id=surviving.id,
                absorbed_entity_id=absorbed.id,
                reason=f"Auto-merged via {best.strategy.value} (confidence={best.confidence:.2f})",
            )
        else:
            result = ResolutionResult(
                candidate=best,
                merged=False,
                reason=f"Below auto-merge threshold ({best.confidence:.2f} < {self.auto_merge_threshold})",
            )

        self._record_result(entity_a.id, entity_b.id, result)
        return result

    def find_all_duplicates(
        self,
        entity_type: Optional[EntityType] = None,
    ) -> List[ResolutionCandidate]:
        """
        Scan the entire registry for duplicate entities.

        Compares all pairs within the same tenant of the same type.
        For large graphs, this is O(n^2) — use with care.
        """
        entities = list(self.registry)
        if entity_type is not None:
            entities = [e for e in entities if e.entity_type == entity_type]

        # Group by tenant for isolation
        by_tenant: Dict[str, List[Entity]] = {}
        for e in entities:
            by_tenant.setdefault(e.tenant_id, []).append(e)

        all_candidates: List[ResolutionCandidate] = []
        for tenant_entities in by_tenant.values():
            for i, entity in enumerate(tenant_entities):
                others = tenant_entities[i + 1:]
                if others:
                    candidates = self.find_duplicates(entity, others)
                    all_candidates.extend(candidates)

        all_candidates.sort(key=lambda r: -r.confidence)
        return all_candidates

    # ---- Strategy Implementations ----

    def _try_strategy(
        self,
        strategy: ResolutionStrategy,
        entity_a: Entity,
        entity_b: Entity,
    ) -> Optional[ResolutionCandidate]:
        """Dispatch to the appropriate strategy implementation."""
        if strategy == ResolutionStrategy.EXACT_NAME:
            return self._exact_name_match(entity_a, entity_b)
        elif strategy == ResolutionStrategy.ALIAS_MATCH:
            return self._alias_match(entity_a, entity_b)
        elif strategy == ResolutionStrategy.FUZZY_NAME:
            return self._fuzzy_name_match(entity_a, entity_b)
        elif strategy == ResolutionStrategy.COMMON_IDENTIFIER:
            return self._common_identifier_match(entity_a, entity_b)
        elif strategy == ResolutionStrategy.RENAMED_COMPONENT:
            return self._renamed_component_match(entity_a, entity_b)
        elif strategy == ResolutionStrategy.FORKED_REPOSITORY:
            return self._forked_repository_match(entity_a, entity_b)
        elif strategy == ResolutionStrategy.REPLACED_SYSTEM:
            return self._replaced_system_match(entity_a, entity_b)
        elif strategy == ResolutionStrategy.SAME_STRUCTURE:
            return self._same_structure_match(entity_a, entity_b)
        return None

    def _exact_name_match(self, a: Entity, b: Entity) -> Optional[ResolutionCandidate]:
        """Case-insensitive exact name match."""
        if a.name.lower() == b.name.lower() and a.entity_type == b.entity_type:
            return ResolutionCandidate(
                entity_a=a, entity_b=b,
                strategy=ResolutionStrategy.EXACT_NAME,
                confidence=0.95,
                evidence=f"Exact name match: '{a.name}'",
            )
        return None

    def _alias_match(self, a: Entity, b: Entity) -> Optional[ResolutionCandidate]:
        """One entity's name appears in the other's aliases."""
        a_name_lower = a.name.lower()
        b_name_lower = b.name.lower()

        if a_name_lower in [alias.lower() for alias in b.aliases]:
            return ResolutionCandidate(
                entity_a=a, entity_b=b,
                strategy=ResolutionStrategy.ALIAS_MATCH,
                confidence=0.85,
                evidence=f"'{a.name}' is an alias of '{b.name}'",
            )
        if b_name_lower in [alias.lower() for alias in a.aliases]:
            return ResolutionCandidate(
                entity_a=a, entity_b=b,
                strategy=ResolutionStrategy.ALIAS_MATCH,
                confidence=0.85,
                evidence=f"'{b.name}' is an alias of '{a.name}'",
            )
        return None

    def _fuzzy_name_match(self, a: Entity, b: Entity) -> Optional[ResolutionCandidate]:
        """Fuzzy name similarity using SequenceMatcher."""
        if a.entity_type != b.entity_type:
            return None

        similarity = SequenceMatcher(None, a.name.lower(), b.name.lower()).ratio()
        if similarity >= 0.85:
            return ResolutionCandidate(
                entity_a=a, entity_b=b,
                strategy=ResolutionStrategy.FUZZY_NAME,
                confidence=similarity,
                evidence=f"Name similarity {similarity:.2f}: '{a.name}' ~ '{b.name}'",
            )
        return None

    def _common_identifier_match(self, a: Entity, b: Entity) -> Optional[ResolutionCandidate]:
        """Shared external identifiers (email for users, CVE for vulns, etc.)."""
        common_keys = {"email", "cve_id", "domain", "repo_url", "api_path", "host"}
        for key in common_keys:
            val_a = a.metadata.get(key) or getattr(a, key, None)
            val_b = b.metadata.get(key) or getattr(b, key, None)
            if val_a and val_b and str(val_a).lower() == str(val_b).lower():
                return ResolutionCandidate(
                    entity_a=a, entity_b=b,
                    strategy=ResolutionStrategy.COMMON_IDENTIFIER,
                    confidence=0.90,
                    evidence=f"Shared {key}: '{val_a}'",
                )
        return None

    def _renamed_component_match(self, a: Entity, b: Entity) -> Optional[ResolutionCandidate]:
        """Detect renames via source_entity_id or metadata chain."""
        if a.source_entity_id == b.id or b.source_entity_id == a.id:
            return ResolutionCandidate(
                entity_a=a, entity_b=b,
                strategy=ResolutionStrategy.RENAMED_COMPONENT,
                confidence=0.80,
                evidence="Explicit source_entity_id reference",
            )

        # Check metadata for "renamed_from" / "renamed_to"
        if a.metadata.get("renamed_from") == b.name:
            return ResolutionCandidate(
                entity_a=a, entity_b=b,
                strategy=ResolutionStrategy.RENAMED_COMPONENT,
                confidence=0.75,
                evidence=f"'{a.name}' metadata indicates rename from '{b.name}'",
            )
        return None

    def _forked_repository_match(self, a: Entity, b: Entity) -> Optional[ResolutionCandidate]:
        """Detect forked repositories sharing a source."""
        if a.entity_type != EntityType.REPOSITORY or b.entity_type != EntityType.REPOSITORY:
            return None

        a_forked_from = a.metadata.get("forked_from")
        b_forked_from = b.metadata.get("forked_from")

        if a_forked_from and b_forked_from and a_forked_from == b_forked_from:
            return ResolutionCandidate(
                entity_a=a, entity_b=b,
                strategy=ResolutionStrategy.FORKED_REPOSITORY,
                confidence=0.65,
                evidence=f"Both forked from '{a_forked_from}'",
            )
        return None

    def _replaced_system_match(self, a: Entity, b: Entity) -> Optional[ResolutionCandidate]:
        """Detect system replacement via metadata flags."""
        if a.metadata.get("replaced_by") == b.name or b.metadata.get("replaced_by") == a.name:
            return ResolutionCandidate(
                entity_a=a, entity_b=b,
                strategy=ResolutionStrategy.REPLACED_SYSTEM,
                confidence=0.90,
                evidence="Explicit replaced_by reference",
            )
        if a.metadata.get("replaces") == b.name or b.metadata.get("replaces") == a.name:
            return ResolutionCandidate(
                entity_a=a, entity_b=b,
                strategy=ResolutionStrategy.REPLACED_SYSTEM,
                confidence=0.90,
                evidence="Explicit replaces reference",
            )
        return None

    def _same_structure_match(self, a: Entity, b: Entity) -> Optional[ResolutionCandidate]:
        """Match by identical internal structure (metadata keys/values)."""
        if a.entity_type != b.entity_type:
            return None

        # Compare significant metadata fields
        sig_keys = {"method", "path", "engine", "host", "port", "schema_version"}
        a_sig = {k: a.metadata.get(k) for k in sig_keys if k in a.metadata or hasattr(a, k)}
        b_sig = {k: b.metadata.get(k) for k in sig_keys if k in b.metadata or hasattr(b, k)}

        if a_sig and b_sig and a_sig == b_sig:
            return ResolutionCandidate(
                entity_a=a, entity_b=b,
                strategy=ResolutionStrategy.SAME_STRUCTURE,
                confidence=0.70,
                evidence=f"Identical structure: {a_sig}",
            )
        return None

    # ---- Merge Logic ----

    def _merge(
        self,
        entity_a: Entity,
        entity_b: Entity,
        candidate: ResolutionCandidate,
    ) -> Tuple[Entity, Entity]:
        """
        Merge two entities, preserving the older entity's ID.

        Absorbed entity's aliases, labels, and metadata are transferred
        to the surviving entity. The absorbed entity is removed from the
        registry.

        Returns:
            (surviving_entity, absorbed_entity)
        """
        # Prefer the entity with richer data as survivor
        survivor, absorbed = entity_a, entity_b
        if len(entity_b.description) > len(entity_a.description):
            survivor, absorbed = entity_b, entity_a

        # Transfer aliases
        for alias in absorbed.aliases:
            survivor.add_alias(alias)

        # Transfer labels
        survivor.labels.update(absorbed.labels)

        # Merge metadata (survivor wins on conflict)
        merged_metadata = {**absorbed.metadata, **survivor.metadata}
        merged_metadata["merged_from"] = absorbed.id
        merged_metadata["merge_strategy"] = candidate.strategy.value
        merged_metadata["merge_confidence"] = candidate.confidence
        survivor.metadata = merged_metadata

        # Remove absorbed from registry
        self.registry.remove(absorbed.id)

        survivor.touch()
        return survivor, absorbed

    # ---- State Management ----

    def _pair_key(self, id_a: str, id_b: str) -> Tuple[str, str]:
        """Create a canonical pair key (order-independent)."""
        return (min(id_a, id_b), max(id_a, id_b))

    def _record_result(self, id_a: str, id_b: str, result: ResolutionResult) -> None:
        """Record that this pair has been resolved."""
        self._resolved_pairs.add(self._pair_key(id_a, id_b))
        self._merge_history.append(result)

    def reset_resolved(self) -> None:
        """Clear resolved pair tracking (allows re-resolution)."""
        self._resolved_pairs.clear()

    def get_history(self, limit: int = 50) -> List[ResolutionResult]:
        """Get recent resolution history."""
        return self._merge_history[-limit:]

    def statistics(self) -> Dict[str, Any]:
        """Get resolution statistics."""
        total = len(self._merge_history)
        merged = sum(1 for r in self._merge_history if r.merged)
        by_strategy: Dict[str, int] = {}
        for r in self._merge_history:
            strategy = r.candidate.strategy.value
            by_strategy[strategy] = by_strategy.get(strategy, 0) + 1

        return {
            "total_candidates": total,
            "merged": merged,
            "kept_separate": total - merged,
            "merge_rate": merged / total if total > 0 else 0.0,
            "by_strategy": by_strategy,
        }

    def __repr__(self) -> str:
        stats = self.statistics()
        return (
            f"EntityResolver(merged={stats['merged']}/{stats['total_candidates']}, "
            f"auto_merge_threshold={self.auto_merge_threshold})"
        )