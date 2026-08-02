"""
Knowledge Graph Ingestion Pipeline

End-to-end ingestion workflow for discovering, extracting, resolving,
and integrating entities and relationships into the knowledge graph.

The pipeline comprises 14 stages, each independently configurable
and instrumented for observability and quality measurement.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .entities import Entity, EntityRegistry, EntityType
from .relationships import Relationship, RelationshipRegistry, RelationshipType
from .provenance import Provenance, ProvenanceChain, SourceType
from .resolution import EntityResolver
from .contradiction import ContradictionManager
from .security import GraphSecurityManager


class PipelineStage(str, Enum):
    """All stages of the ingestion pipeline, in order."""

    DISCOVER = "discover"
    EXTRACT_CANDIDATES = "extract_candidates"
    RESOLVE_DUPLICATES = "resolve_duplicates"
    CLASSIFY = "classify"
    EXTRACT_RELATIONSHIPS = "extract_relationships"
    VALIDATE = "validate"
    ATTACH_PROVENANCE = "attach_provenance"
    APPLY_ACCESS_CONTROLS = "apply_access_controls"
    VERSION_GRAPH = "version_graph"
    DETECT_CONTRADICTIONS = "detect_contradictions"
    FLAG_STALE = "flag_stale"
    MAKE_RETRIEVABLE = "make_retrievable"
    MEASURE_QUALITY = "measure_quality"
    IMPROVE = "improve"


@dataclass
class IngestionSource:
    """
    Describes an external source of graph data.

    Attributes:
        id: Unique source identifier.
        name: Human-readable source name.
        source_type: Classification from SourceType enum.
        location: URI, file path, or connection string.
        credentials: Optional authentication details.
        config: Source-specific configuration.
        enabled: Whether this source is active.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    source_type: SourceType = SourceType.USER_INPUT
    location: str = ""
    credentials: Dict[str, Any] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


@dataclass
class IngestionResult:
    """
    Result of an ingestion pipeline run.

    Captures counts, quality metrics, and any issues encountered.
    """

    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    sources_processed: int = 0
    entities_discovered: int = 0
    entities_created: int = 0
    entities_updated: int = 0
    entities_merged: int = 0
    relationships_created: int = 0
    duplicates_resolved: int = 0
    contradictions_detected: int = 0
    staleness_flags: int = 0
    quality_score: float = 0.0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    stage_durations: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    @property
    def duration_seconds(self) -> float:
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0

    def summary(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "success": self.success,
            "duration_seconds": self.duration_seconds,
            "entities_discovered": self.entities_discovered,
            "entities_created": self.entities_created,
            "entities_updated": self.entities_updated,
            "relationships_created": self.relationships_created,
            "duplicates_resolved": self.duplicates_resolved,
            "contradictions_detected": self.contradictions_detected,
            "quality_score": self.quality_score,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
        }


# Type aliases for pipeline hooks
EntityExtractor = Callable[[IngestionSource], List[Dict[str, Any]]]
RelationshipExtractor = Callable[[List[Entity]], List[Tuple[str, str, RelationshipType, Dict[str, Any]]]]
Validator = Callable[[Entity], List[str]]  # Returns list of validation issues
Classifier = Callable[[Dict[str, Any]], EntityType]


class IngestionPipeline:
    """
    End-to-end knowledge graph ingestion pipeline.

    Stages (in order):
    1.  Discover sources — locate and connect to data sources
    2.  Extract candidate entities — parse raw data into entity dicts
    3.  Resolve duplicates — deduplicate within and across sources
    4.  Classify — assign entity types
    5.  Extract relationships — detect connections between entities
    6.  Validate — check data quality and integrity
    7.  Attach provenance — record origin for every fact
    8.  Apply access controls — enforce RBAC/ABAC
    9.  Version graph — snapshot and version the graph state
    10. Detect contradictions — find conflicting claims
    11. Flag stale — mark expired or unverified facts
    12. Make retrievable — index and optimize for queries
    13. Measure quality — compute quality metrics
    14. Improve — learn and tune from quality feedback

    Hooks can be registered for each stage to customize behavior.
    """

    def __init__(
        self,
        entity_registry: Optional[EntityRegistry] = None,
        relationship_registry: Optional[RelationshipRegistry] = None,
        resolver: Optional[EntityResolver] = None,
        contradiction_manager: Optional[ContradictionManager] = None,
        security_manager: Optional[GraphSecurityManager] = None,
    ) -> None:
        self.entity_registry = entity_registry or EntityRegistry()
        self.relationship_registry = relationship_registry or RelationshipRegistry()
        self.resolver = resolver or EntityResolver(self.entity_registry)
        self.contradiction_manager = contradiction_manager or ContradictionManager()
        self.security_manager = security_manager or GraphSecurityManager()

        # Registered hooks per stage
        self._entity_extractors: Dict[str, EntityExtractor] = {}
        self._relationship_extractors: Dict[str, RelationshipExtractor] = {}
        self._validators: List[Validator] = []
        self._classifiers: List[Classifier] = []

        # Source list
        self._sources: Dict[str, IngestionSource] = {}

        # Quality thresholds
        self.min_confidence: float = 0.3
        self.min_quality_score: float = 0.7
        self.staleness_days: int = 90

    # ---- Source Management ----

    def register_source(self, source: IngestionSource) -> None:
        """Register an ingestion source."""
        self._sources[source.id] = source

    def register_entity_extractor(self, source_type: SourceType, extractor: EntityExtractor) -> None:
        """Register a custom entity extractor for a source type."""
        self._entity_extractors[source_type.value] = extractor

    def register_relationship_extractor(self, source_type: SourceType, extractor: RelationshipExtractor) -> None:
        """Register a custom relationship extractor for a source type."""
        self._relationship_extractors[source_type.value] = extractor

    def register_validator(self, validator: Validator) -> None:
        """Register an entity validator."""
        self._validators.append(validator)

    def register_classifier(self, classifier: Classifier) -> None:
        """Register an entity type classifier."""
        self._classifiers.append(classifier)

    # ---- Pipeline Execution ----

    def run(
        self,
        source_ids: Optional[List[str]] = None,
        stages: Optional[List[PipelineStage]] = None,
        dry_run: bool = False,
    ) -> IngestionResult:
        """
        Execute the full ingestion pipeline.

        Args:
            source_ids: Specific sources to process (None = all).
            stages: Specific stages to run (None = all).
            dry_run: If True, don't persist changes.

        Returns:
            IngestionResult with metrics and issues.
        """
        result = IngestionResult()
        stages_to_run = stages or list(PipelineStage)

        sources = [
            s for s in self._sources.values()
            if s.enabled and (source_ids is None or s.id in source_ids)
        ]
        result.sources_processed = len(sources)

        if not sources:
            result.warnings.append("No enabled sources found")
            result.completed_at = datetime.now(timezone.utc)
            return result

        extracted_entities: List[Dict[str, Any]] = []

        for stage in stages_to_run:
            stage_start = datetime.now(timezone.utc)
            try:
                if stage == PipelineStage.DISCOVER:
                    self._stage_discover(sources, result)
                elif stage == PipelineStage.EXTRACT_CANDIDATES:
                    extracted_entities = self._stage_extract_candidates(sources, result)
                elif stage == PipelineStage.RESOLVE_DUPLICATES:
                    self._stage_resolve_duplicates(extracted_entities, result)
                elif stage == PipelineStage.CLASSIFY:
                    self._stage_classify(extracted_entities, result)
                elif stage == PipelineStage.EXTRACT_RELATIONSHIPS:
                    self._stage_extract_relationships(sources, result)
                elif stage == PipelineStage.VALIDATE:
                    self._stage_validate(result)
                elif stage == PipelineStage.ATTACH_PROVENANCE:
                    self._stage_attach_provenance(sources, result)
                elif stage == PipelineStage.APPLY_ACCESS_CONTROLS:
                    self._stage_apply_access_controls(result)
                elif stage == PipelineStage.VERSION_GRAPH:
                    self._stage_version_graph(result)
                elif stage == PipelineStage.DETECT_CONTRADICTIONS:
                    self._stage_detect_contradictions(result)
                elif stage == PipelineStage.FLAG_STALE:
                    self._stage_flag_stale(result)
                elif stage == PipelineStage.MAKE_RETRIEVABLE:
                    self._stage_make_retrievable(result)
                elif stage == PipelineStage.MEASURE_QUALITY:
                    self._stage_measure_quality(result)
                elif stage == PipelineStage.IMPROVE:
                    self._stage_improve(result)
            except Exception as e:
                result.errors.append(f"Stage {stage.value} failed: {str(e)}")

            duration = (datetime.now(timezone.utc) - stage_start).total_seconds()
            result.stage_durations[stage.value] = duration

        result.completed_at = datetime.now(timezone.utc)
        return result

    # ---- Stage Implementations ----

    def _stage_discover(self, sources: List[IngestionSource], result: IngestionResult) -> None:
        """Stage 1: Discover and validate connectivity to sources."""
        for source in sources:
            if not source.location:
                result.warnings.append(f"Source '{source.name}' has no location")
            # In production, this would test connectivity

    def _stage_extract_candidates(
        self,
        sources: List[IngestionSource],
        result: IngestionResult,
    ) -> List[Dict[str, Any]]:
        """Stage 2: Extract candidate entities from all sources."""
        all_candidates: List[Dict[str, Any]] = []
        for source in sources:
            extractor = self._entity_extractors.get(source.source_type.value)
            if extractor:
                try:
                    candidates = extractor(source)
                    result.entities_discovered += len(candidates)
                    all_candidates.extend(candidates)
                except Exception as e:
                    result.errors.append(
                        f"Extraction failed for source '{source.name}': {str(e)}"
                    )
            else:
                result.warnings.append(
                    f"No extractor registered for source type {source.source_type.value}"
                )
        return all_candidates

    def _stage_resolve_duplicates(
        self,
        candidates: List[Dict[str, Any]],
        result: IngestionResult,
    ) -> None:
        """Stage 3: Resolve duplicate entities using the EntityResolver."""
        # Convert candidate dicts to entities and let the resolver merge
        for candidate in candidates:
            entity = Entity.from_dict(candidate)
            existing = self.entity_registry.get_by_name(
                entity.name,
                tenant_id=entity.tenant_id,
                project_id=entity.project_id,
            )
            if existing:
                merged = self.resolver.resolve(existing, entity)
                if merged:
                    result.entities_merged += 1
                    result.duplicates_resolved += 1
            else:
                if not result.entities_created:  # Track first creation
                    pass
                result.entities_created += 1

    def _stage_classify(
        self,
        candidates: List[Dict[str, Any]],
        result: IngestionResult,
    ) -> None:
        """Stage 4: Classify entities into their appropriate types."""
        unclassified = 0
        for candidate in candidates:
            entity_type = candidate.get("entity_type")
            if entity_type:
                continue  # Already classified
            # Try registered classifiers
            for classifier in self._classifiers:
                try:
                    classified_type = classifier(candidate)
                    if classified_type:
                        candidate["entity_type"] = classified_type.value
                        break
                except Exception:
                    continue
            if not candidate.get("entity_type"):
                unclassified += 1
        if unclassified:
            result.warnings.append(f"{unclassified} entities could not be classified")

    def _stage_extract_relationships(
        self,
        sources: List[IngestionSource],
        result: IngestionResult,
    ) -> None:
        """Stage 5: Extract relationships between entities."""
        entities = list(self.entity_registry)
        for source in sources:
            extractor = self._relationship_extractors.get(source.source_type.value)
            if extractor:
                try:
                    rels = extractor(entities)
                    for source_id, target_id, rel_type, metadata in rels:
                        rel = self.relationship_registry.create(
                            source_id=source_id,
                            target_id=target_id,
                            relationship_type=rel_type,
                            metadata=metadata,
                        )
                        result.relationships_created += 1
                except Exception as e:
                    result.errors.append(
                        f"Relationship extraction failed for '{source.name}': {str(e)}"
                    )

    def _stage_validate(self, result: IngestionResult) -> None:
        """Stage 6: Validate all entities for quality and integrity."""
        for entity in self.entity_registry:
            for validator in self._validators:
                try:
                    issues = validator(entity)
                    for issue in issues:
                        result.warnings.append(
                            f"Validation issue on {entity.name}: {issue}"
                        )
                except Exception as e:
                    result.errors.append(f"Validator failed on {entity.name}: {str(e)}")

    def _stage_attach_provenance(
        self,
        sources: List[IngestionSource],
        result: IngestionResult,
    ) -> None:
        """Stage 7: Attach provenance records to all ingested facts."""
        # In a full implementation, each entity and relationship would
        # have a provenance record linking back to its source.
        # This stage attaches any missing provenance.
        for entity in self.entity_registry:
            prov_id = entity.metadata.get("provenance_id")
            if not prov_id:
                # Create default provenance
                prov = Provenance(
                    source=f"Ingestion run {result.run_id}",
                    source_type=SourceType.USER_INPUT,
                    confidence=0.5,
                )
                entity.metadata["provenance_id"] = prov.id
                entity.touch()

    def _stage_apply_access_controls(self, result: IngestionResult) -> None:
        """Stage 8: Apply access controls to all entities."""
        for entity in self.entity_registry:
            # Ensure tenant isolation
            if not entity.tenant_id:
                entity.tenant_id = "default"
            # Classify sensitivity
            if "pii" in entity.labels or "sensitive" in entity.labels:
                entity.labels.add("restricted")

    def _stage_version_graph(self, result: IngestionResult) -> None:
        """Stage 9: Version the graph state."""
        # In production, this would snapshot the graph and assign
        # a version number for rollback capability.
        result.metadata["graph_version"] = str(uuid.uuid4())

    def _stage_detect_contradictions(self, result: IngestionResult) -> None:
        """Stage 10: Detect contradictory claims in the graph."""
        contradictions = self.contradiction_manager.scan(
            list(self.entity_registry),
            list(self.relationship_registry),
        )
        result.contradictions_detected = len(contradictions)

    def _stage_flag_stale(self, result: IngestionResult) -> None:
        """Stage 11: Flag stale entities and relationships."""
        cutoff = datetime.now(timezone.utc)
        for entity in self.entity_registry:
            age_days = (cutoff - entity.updated_at).days
            if age_days > self.staleness_days:
                entity.labels.add("stale")
                entity.touch()
                result.staleness_flags += 1

    def _stage_make_retrievable(self, result: IngestionResult) -> None:
        """Stage 12: Index and optimize for retrieval."""
        # Indices are maintained by EntityRegistry and RelationshipRegistry
        # during insertion. This stage could trigger additional indexing
        # like full-text search or vector embeddings.
        pass

    def _stage_measure_quality(self, result: IngestionResult) -> float:
        """Stage 13: Measure graph quality metrics."""
        metrics = self._compute_quality_metrics()
        result.quality_score = metrics.get("overall", 0.0)
        result.metadata["quality_metrics"] = metrics
        return result.quality_score

    def _stage_improve(self, result: IngestionResult) -> None:
        """Stage 14: Learn from quality feedback and tune parameters."""
        if result.quality_score < self.min_quality_score:
            result.warnings.append(
                f"Quality score {result.quality_score:.2f} below threshold "
                f"{self.min_quality_score}. Consider tuning extraction."
            )

    # ---- Quality Metrics ----

    def _compute_quality_metrics(self) -> Dict[str, float]:
        """Compute graph quality metrics."""
        entity_count = len(self.entity_registry)
        rel_count = len(self.relationship_registry)

        if entity_count == 0:
            return {"overall": 0.0, "completeness": 0.0, "freshness": 0.0, "connectivity": 0.0}

        # Completeness: entities with descriptions
        with_desc = sum(1 for e in self.entity_registry if e.description)
        completeness = with_desc / entity_count

        # Freshness: entities updated recently
        cutoff = datetime.now(timezone.utc)
        fresh = sum(1 for e in self.entity_registry if (cutoff - e.updated_at).days < 30)
        freshness = fresh / entity_count

        # Connectivity: average relationships per entity
        connectivity = min(1.0, rel_count / (entity_count * 5))  # Normalized

        # Provenance coverage
        with_prov = sum(1 for e in self.entity_registry if e.metadata.get("provenance_id"))
        provenance_coverage = with_prov / entity_count

        overall = (completeness + freshness + connectivity + provenance_coverage) / 4
        return {
            "overall": round(overall, 3),
            "completeness": round(completeness, 3),
            "freshness": round(freshness, 3),
            "connectivity": round(connectivity, 3),
            "provenance_coverage": round(provenance_coverage, 3),
        }

    # ---- Utility ----

    def ingest_entity(
        self,
        entity_type: EntityType,
        name: str,
        source: IngestionSource,
        **kwargs: Any,
    ) -> Entity:
        """
        Convenience method: ingest a single entity with full provenance.

        This is the primary API for programmatic entity ingestion.
        """
        # Create provenance
        provenance = Provenance(
            source=source.name,
            source_type=source.source_type,
            confidence=0.8,
            metadata={"source_id": source.id},
        )

        # Check for duplicates
        existing = self.entity_registry.get_by_name(
            name, kwargs.get("tenant_id", "default"), kwargs.get("project_id", "")
        )
        if existing:
            existing.metadata["provenance_id"] = provenance.id
            existing.touch()
            return existing

        # Create and register
        entity = self.entity_registry.create(
            entity_type=entity_type,
            name=name,
            metadata={"provenance_id": provenance.id, **kwargs.pop("metadata", {})},
            **kwargs,
        )
        return entity

    def __repr__(self) -> str:
        return (
            f"IngestionPipeline(sources={len(self._sources)}, "
            f"entities={len(self.entity_registry)}, "
            f"relationships={len(self.relationship_registry)})"
        )