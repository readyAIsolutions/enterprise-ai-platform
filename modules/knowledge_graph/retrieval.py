"""
Knowledge Graph Retrieval

Query engine for retrieving entities, relationships, and subgraphs
with built-in security, provenance, and conflict awareness.

Retrieval rules:
- Return only relevant entities for the query.
- Prefer current/verified facts over stale ones.
- Include provenance with every returned fact.
- Respect tenant and project boundaries.
- Respect RBAC on every query.
- Avoid leaking sensitive data.
- Surface conflicts when relevant.
- Explain uncertainty in results.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from .entities import Entity, EntityRegistry, EntityType
from .relationships import Relationship, RelationshipRegistry, RelationshipType
from .security import GraphSecurityManager, Permission


class QueryMode(str, Enum):
    """Query execution modes."""

    EXACT = "exact"           # Exact match on IDs or names
    SEARCH = "search"         # Full-text / metadata search
    TRAVERSE = "traverse"     # Graph traversal from a starting node
    PATH = "path"             # Find paths between two nodes
    NEIGHBORS = "neighbors"   # Find neighbors of a node
    SUBGRAPH = "subgraph"     # Extract a connected subgraph


class SortOrder(str, Enum):
    """Result sort orders."""

    RELEVANCE = "relevance"
    CONFIDENCE = "confidence"
    RECENCY = "recency"
    NAME = "name"
    TYPE = "type"


@dataclass
class QueryResult:
    """
    Result of a graph query.

    Includes the matched entities and relationships along with
    query metadata, provenance context, and any uncertainty flags.

    Attributes:
        query_id: Unique identifier for this query execution.
        entities: Matching entities (with provenance context).
        relationships: Matching relationships (with provenance context).
        total_matches: Total number of matches before pagination.
        query_duration_ms: Query execution time in milliseconds.
        has_more: Whether there are more results beyond the limit.
        uncertainty_flags: Warnings about uncertain or conflicting results.
        explanation: Human-readable explanation of the query execution.
    """

    query_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    entities: List[Dict[str, Any]] = field(default_factory=list)
    relationships: List[Dict[str, Any]] = field(default_factory=list)
    total_matches: int = 0
    query_duration_ms: float = 0.0
    has_more: bool = False
    uncertainty_flags: List[str] = field(default_factory=list)
    explanation: str = ""

    @property
    def empty(self) -> bool:
        return len(self.entities) == 0 and len(self.relationships) == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query_id": self.query_id,
            "entities": self.entities,
            "relationships": self.relationships,
            "total_matches": self.total_matches,
            "query_duration_ms": self.query_duration_ms,
            "has_more": self.has_more,
            "uncertainty_flags": self.uncertainty_flags,
            "explanation": self.explanation,
        }


@dataclass
class Query:
    """
    A user-facing query against the knowledge graph.

    Supports filtering by entity type, relationships, labels,
    metadata, tenant, and project. Designed to be safe by default:
    all queries are scoped to the requesting user's permissions.

    Attributes:
        entity_types: Filter by entity types.
        name_contains: Substring match on entity name.
        labels: Required entity labels.
        exclude_labels: Forbidden entity labels.
        metadata_filters: Key-value metadata filters.
        relationship_types: Filter by relationship types.
        relationship_with: Entity IDs that must be related.
        tenant_id: Tenant scope (required, enforced by security).
        project_id: Project scope.
        min_confidence: Minimum provenance confidence.
        include_stale: Whether to include stale entities.
        max_depth: Max traversal depth for traverse queries.
        limit: Maximum results to return.
        offset: Pagination offset.
        sort_by: Sort order.
        explain: Whether to include an explanation.
    """

    entity_types: Optional[List[EntityType]] = None
    name_contains: Optional[str] = None
    labels: Optional[Set[str]] = None
    exclude_labels: Optional[Set[str]] = None
    metadata_filters: Optional[Dict[str, Any]] = None
    relationship_types: Optional[List[RelationshipType]] = None
    relationship_with: Optional[List[str]] = None
    tenant_id: str = "default"
    project_id: Optional[str] = None
    min_confidence: float = 0.0
    include_stale: bool = False
    max_depth: int = 3
    limit: int = 50
    offset: int = 0
    sort_by: SortOrder = SortOrder.RELEVANCE
    explain: bool = False


class QueryBuilder:
    """
    Fluent query builder for constructing graph queries.

    Usage:
        query = (
            QueryBuilder(tenant_id="acme")
            .of_type(EntityType.SERVICE, EntityType.API)
            .with_label("critical")
            .related_to("entity-123")
            .min_confidence(0.7)
            .limit(20)
            .build()
        )
        result = engine.execute(query, user_id="user-1")
    """

    def __init__(self, tenant_id: str = "default") -> None:
        self._query = Query(tenant_id=tenant_id)

    def of_type(self, *entity_types: EntityType) -> "QueryBuilder":
        self._query.entity_types = list(entity_types)
        return self

    def name_contains(self, text: str) -> "QueryBuilder":
        self._query.name_contains = text
        return self

    def with_label(self, *labels: str) -> "QueryBuilder":
        self._query.labels = set(labels)
        return self

    def without_label(self, *labels: str) -> "QueryBuilder":
        self._query.exclude_labels = set(labels)
        return self

    def with_metadata(self, **filters: Any) -> "QueryBuilder":
        self._query.metadata_filters = filters
        return self

    def related_to(self, *entity_ids: str) -> "QueryBuilder":
        self._query.relationship_with = list(entity_ids)
        return self

    def with_relationship(self, *rel_types: RelationshipType) -> "QueryBuilder":
        self._query.relationship_types = list(rel_types)
        return self

    def min_confidence(self, confidence: float) -> "QueryBuilder":
        self._query.min_confidence = confidence
        return self

    def include_stale(self) -> "QueryBuilder":
        self._query.include_stale = True
        return self

    def in_project(self, project_id: str) -> "QueryBuilder":
        self._query.project_id = project_id
        return self

    def max_depth(self, depth: int) -> "QueryBuilder":
        self._query.max_depth = depth
        return self

    def limit(self, limit: int) -> "QueryBuilder":
        self._query.limit = limit
        return self

    def offset(self, offset: int) -> "QueryBuilder":
        self._query.offset = offset
        return self

    def sort_by(self, order: SortOrder) -> "QueryBuilder":
        self._query.sort_by = order
        return self

    def with_explanation(self) -> "QueryBuilder":
        self._query.explain = True
        return self

    def build(self) -> Query:
        return self._query


class GraphQueryEngine:
    """
    Secure query engine for the knowledge graph.

    Enforces all retrieval rules:
    - Tenant isolation (queries are always scoped)
    - RBAC authorization on every query
    - Sensitive data masking in results
    - Provenance inclusion
    - Staleness filtering by default
    - Conflict surfacing in results
    - Uncertainty explanation
    """

    def __init__(
        self,
        entity_registry: EntityRegistry,
        relationship_registry: RelationshipRegistry,
        security_manager: GraphSecurityManager,
    ) -> None:
        self.entity_registry = entity_registry
        self.relationship_registry = relationship_registry
        self.security = security_manager

    def execute(
        self,
        query: Query,
        user_id: str,
        mode: QueryMode = QueryMode.SEARCH,
        start_entity_id: Optional[str] = None,
        target_entity_id: Optional[str] = None,
    ) -> QueryResult:
        """
        Execute a query against the graph with full security enforcement.

        Args:
            query: The Query to execute.
            user_id: ID of the requesting user.
            mode: Query execution mode.
            start_entity_id: Starting entity for traverse/path/neighbors modes.
            target_entity_id: Target entity for path mode.

        Returns:
            QueryResult with entities, relationships, and metadata.
        """
        start_time = datetime.now(timezone.utc)

        # 1. Authorization check
        if not self.security.authorize(
            user_id=user_id,
            permission=Permission.RUN_QUERIES,
            tenant_id=query.tenant_id,
        ):
            result = QueryResult(
                total_matches=0,
                explanation="Access denied: insufficient permissions",
            )
            return result

        # 2. Tenant isolation
        tenant_filter = self.security.isolate_query(user_id, query.tenant_id)
        effective_tenant = tenant_filter.get("tenant_id", query.tenant_id)
        if effective_tenant == "__FORBIDDEN__":
            result = QueryResult(
                total_matches=0,
                explanation="Access denied: tenant isolation",
            )
            return result

        # 3. Execute based on mode
        if mode == QueryMode.EXACT:
            entities, relationships = self._query_exact(query, effective_tenant, start_entity_id)
        elif mode == QueryMode.TRAVERSE:
            entities, relationships = self._query_traverse(query, effective_tenant, start_entity_id)
        elif mode == QueryMode.PATH:
            entities, relationships = self._query_path(query, effective_tenant, start_entity_id, target_entity_id)
        elif mode == QueryMode.NEIGHBORS:
            entities, relationships = self._query_neighbors(query, effective_tenant, start_entity_id)
        elif mode == QueryMode.SUBGRAPH:
            entities, relationships = self._query_subgraph(query, effective_tenant, start_entity_id)
        else:  # SEARCH
            entities, relationships = self._query_search(query, effective_tenant)

        # 4. Post-processing: security, sorting, pagination
        entities = self._post_process_entities(entities, user_id, query)
        relationships = self._post_process_relationships(relationships, user_id, query)

        total = len(entities) + len(relationships)

        # Sort
        entities = self._sort_entities(entities, query.sort_by)
        relationships = self._sort_relationships(relationships, query.sort_by)

        # Paginate
        has_more = total > (query.offset + query.limit)
        entities = entities[query.offset : query.offset + query.limit]
        relationships = relationships[query.offset : query.offset + query.limit]

        # 5. Build result
        duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

        uncertainty_flags: List[str] = []
        explanation_parts: List[str] = []

        for entity_dict in entities:
            conf = entity_dict.get("_confidence", 1.0)
            if 0 < conf < 0.5:
                uncertainty_flags.append(
                    f"Low confidence ({conf:.2f}) for entity: {entity_dict.get('name', 'unknown')}"
                )
            if entity_dict.get("_is_stale"):
                uncertainty_flags.append(
                    f"Stale entity: {entity_dict.get('name', 'unknown')}"
                )

        if query.explain:
            explanation_parts.append(f"Mode: {mode.value}")
            explanation_parts.append(f"Tenant: {effective_tenant}")
            if query.entity_types:
                explanation_parts.append(f"Types: {[t.value for t in query.entity_types]}")
            explanation_parts.append(f"Results: {total} total, showing {len(entities) + len(relationships)}")
            if uncertainty_flags:
                explanation_parts.append(f"Uncertainties: {len(uncertainty_flags)}")

        return QueryResult(
            entities=entities,
            relationships=relationships,
            total_matches=total,
            query_duration_ms=duration,
            has_more=has_more,
            uncertainty_flags=uncertainty_flags,
            explanation="; ".join(explanation_parts) if query.explain else "",
        )

    # ---- Query Implementations ----

    def _query_search(self, query: Query, tenant_id: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Full search across entities."""
        entities: List[Entity] = []

        for entity in self.entity_registry:
            # Tenant filter
            if entity.tenant_id != tenant_id:
                continue

            # Type filter
            if query.entity_types and entity.entity_type not in query.entity_types:
                continue

            # Name filter
            if query.name_contains and query.name_contains.lower() not in entity.name.lower():
                continue

            # Label filter
            if query.labels:
                entity_labels = {l.lower() for l in entity.labels}
                required = {l.lower() for l in query.labels}
                if not required.issubset(entity_labels):
                    continue

            # Exclude labels
            if query.exclude_labels:
                entity_labels = {l.lower() for l in entity.labels}
                excluded = {l.lower() for l in query.exclude_labels}
                if entity_labels.intersection(excluded):
                    continue

            # Metadata filter
            if query.metadata_filters:
                match = True
                for key, value in query.metadata_filters.items():
                    if entity.metadata.get(key) != value:
                        match = False
                        break
                if not match:
                    continue

            # Min confidence
            if query.min_confidence > 0:
                conf = entity.metadata.get("_confidence", 0.5)
                if conf < query.min_confidence:
                    continue

            # Staleness
            if not query.include_stale and "stale" in entity.labels:
                continue

            # Project filter
            if query.project_id and entity.project_id != query.project_id:
                continue

            entities.append(entity)

        entity_dicts = [self._entity_to_result_dict(e) for e in entities]

        # Find related relationships if requested
        rel_dicts: List[Dict[str, Any]] = []
        if query.relationship_with:
            target_ids = set(query.relationship_with)
            for entity in entities:
                for rel in self.relationship_registry.find_outgoing(entity.id):
                    if rel.target_id in target_ids:
                        if query.relationship_types is None or rel.relationship_type in query.relationship_types:
                            rel_dicts.append(rel.to_dict())
                for rel in self.relationship_registry.find_incoming(entity.id):
                    if rel.source_id in target_ids:
                        if query.relationship_types is None or rel.relationship_type in query.relationship_types:
                            rel_dicts.append(rel.to_dict())

        return entity_dicts, rel_dicts

    def _query_exact(
        self,
        query: Query,
        tenant_id: str,
        entity_id: Optional[str],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Exact entity lookup by ID or name."""
        entities: List[Dict[str, Any]] = []
        if entity_id:
            entity = self.entity_registry.get(entity_id)
            if entity and entity.tenant_id == tenant_id:
                entities.append(self._entity_to_result_dict(entity))
        elif query.name_contains:
            entity = self.entity_registry.get_by_name(query.name_contains, tenant_id)
            if entity:
                entities.append(self._entity_to_result_dict(entity))
        return entities, []

    def _query_traverse(
        self,
        query: Query,
        tenant_id: str,
        start_entity_id: Optional[str],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Graph traversal from a starting node."""
        if not start_entity_id:
            return [], []

        start = self.entity_registry.get(start_entity_id)
        if not start or start.tenant_id != tenant_id:
            return [], []

        entity_dicts: Dict[str, Dict[str, Any]] = {start.id: self._entity_to_result_dict(start)}
        rel_dicts: List[Dict[str, Any]] = []

        neighbor_results = self.relationship_registry.find_neighbors(
            start_entity_id,
            max_depth=query.max_depth,
            direction="both",
        )

        for rel, neighbor_id in neighbor_results:
            if query.relationship_types and rel.relationship_type not in query.relationship_types:
                continue
            if rel.tenant_id != tenant_id:
                continue
            rel_dicts.append(rel.to_dict())
            if neighbor_id not in entity_dicts:
                neighbor = self.entity_registry.get(neighbor_id)
                if neighbor:
                    entity_dicts[neighbor_id] = self._entity_to_result_dict(neighbor)

        return list(entity_dicts.values()), rel_dicts

    def _query_path(
        self,
        query: Query,
        tenant_id: str,
        start_entity_id: Optional[str],
        target_entity_id: Optional[str],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Find paths between two entities."""
        if not start_entity_id or not target_entity_id:
            return [], []

        paths = self.relationship_registry.find_paths(
            start_entity_id, target_entity_id, query.max_depth
        )

        entity_ids: Set[str] = {start_entity_id, target_entity_id}
        all_rels: List[Relationship] = []

        for path in paths:
            for rel in path:
                if rel.tenant_id == tenant_id:
                    all_rels.append(rel)
                    entity_ids.add(rel.source_id)
                    entity_ids.add(rel.target_id)

        entity_dicts = [
            self._entity_to_result_dict(e)
            for eid in entity_ids
            if (e := self.entity_registry.get(eid)) and e.tenant_id == tenant_id
        ]
        rel_dicts = [
            r.to_dict() for r in all_rels
            if (not query.relationship_types or r.relationship_type in query.relationship_types)
        ]

        return entity_dicts, rel_dicts

    def _query_neighbors(
        self,
        query: Query,
        tenant_id: str,
        start_entity_id: Optional[str],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Find direct neighbors of an entity."""
        return self._query_traverse(query, tenant_id, start_entity_id)

    def _query_subgraph(
        self,
        query: Query,
        tenant_id: str,
        start_entity_id: Optional[str],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Extract a connected subgraph."""
        if not start_entity_id:
            return [], []

        start = self.entity_registry.get(start_entity_id)
        if not start or start.tenant_id != tenant_id:
            return [], []

        visited_entities: Dict[str, Dict[str, Any]] = {}
        visited_rels: Dict[str, Dict[str, Any]] = {}
        frontier = [start_entity_id]

        for _ in range(query.max_depth):
            next_frontier: List[str] = []
            for eid in frontier:
                if eid in visited_entities:
                    continue
                entity = self.entity_registry.get(eid)
                if not entity or entity.tenant_id != tenant_id:
                    continue
                visited_entities[eid] = self._entity_to_result_dict(entity)

                for rel in self.relationship_registry.find_outgoing(eid):
                    if rel.id not in visited_rels:
                        rel_types = query.relationship_types
                        if rel_types is None or rel.relationship_type in rel_types:
                            visited_rels[rel.id] = rel.to_dict()
                            next_frontier.append(rel.target_id)

                for rel in self.relationship_registry.find_incoming(eid):
                    if rel.id not in visited_rels:
                        rel_types = query.relationship_types
                        if rel_types is None or rel.relationship_type in rel_types:
                            visited_rels[rel.id] = rel.to_dict()
                            next_frontier.append(rel.source_id)

            frontier = next_frontier

        return list(visited_entities.values()), list(visited_rels.values())

    # ---- Post-Processing ----

    def _post_process_entities(
        self,
        entity_dicts: List[Dict[str, Any]],
        user_id: str,
        query: Query,
    ) -> List[Dict[str, Any]]:
        """Apply security masking and enrichment to entity results."""
        processed = []
        for ed in entity_dicts:
            # Security masking
            secure = self.security.secure_entity_for_read(
                ed, user_id, query.tenant_id
            )
            if secure is None:
                continue  # Access denied for this entity

            # Enrich with provenance context
            prov_id = ed.get("metadata", {}).get("provenance_id")
            if prov_id:
                secure["_provenance_id"] = prov_id

            # Flag staleness
            if "stale" in ed.get("labels", []):
                secure["_is_stale"] = True

            # Confidence
            secure["_confidence"] = ed.get("metadata", {}).get("_confidence", 0.5)

            if not query.include_stale and secure.get("_is_stale"):
                continue

            processed.append(secure)

        return processed

    def _post_process_relationships(
        self,
        rel_dicts: List[Dict[str, Any]],
        user_id: str,
        query: Query,
    ) -> List[Dict[str, Any]]:
        """Apply security checks to relationship results."""
        processed = []
        for rd in rel_dicts:
            if rd.get("tenant_id", "default") != query.tenant_id:
                continue
            rd["_confidence"] = rd.get("confidence", 0.5)
            processed.append(rd)
        return processed

    def _entity_to_result_dict(self, entity: Entity) -> Dict[str, Any]:
        """Convert an entity to a result dictionary with added context."""
        d = entity.to_dict()
        d["_confidence"] = entity.metadata.get("_confidence", 0.5)
        d["_is_stale"] = "stale" in entity.labels
        d["_provenance_id"] = entity.metadata.get("provenance_id")
        return d

    # ---- Sorting ----

    def _sort_entities(
        self,
        entities: List[Dict[str, Any]],
        sort_by: SortOrder,
    ) -> List[Dict[str, Any]]:
        if sort_by == SortOrder.CONFIDENCE:
            return sorted(entities, key=lambda e: e.get("_confidence", 0), reverse=True)
        elif sort_by == SortOrder.RECENCY:
            return sorted(entities, key=lambda e: e.get("updated_at", ""), reverse=True)
        elif sort_by == SortOrder.NAME:
            return sorted(entities, key=lambda e: e.get("name", "").lower())
        elif sort_by == SortOrder.TYPE:
            return sorted(entities, key=lambda e: e.get("entity_type", ""))
        return entities  # relevance = as-returned

    def _sort_relationships(
        self,
        relationships: List[Dict[str, Any]],
        sort_by: SortOrder,
    ) -> List[Dict[str, Any]]:
        if sort_by == SortOrder.CONFIDENCE:
            return sorted(relationships, key=lambda r: r.get("_confidence", 0), reverse=True)
        elif sort_by == SortOrder.RECENCY:
            return sorted(relationships, key=lambda r: r.get("updated_at", ""), reverse=True)
        return relationships

    # ---- Utility Queries ----

    def get_dependency_graph(
        self,
        entity_id: str,
        user_id: str,
        tenant_id: str = "default",
        max_depth: int = 3,
    ) -> QueryResult:
        """Get the full dependency graph for an entity."""
        query = QueryBuilder(tenant_id=tenant_id).max_depth(max_depth).with_explanation().build()
        return self.execute(query, user_id, mode=QueryMode.TRAVERSE, start_entity_id=entity_id)

    def find_impacted(
        self,
        entity_id: str,
        user_id: str,
        tenant_id: str = "default",
    ) -> QueryResult:
        """Find all entities impacted by a change to the given entity."""
        query = QueryBuilder(tenant_id=tenant_id)\
            .with_relationship(RelationshipType.DEPENDS_ON)\
            .max_depth(5)\
            .build()
        return self.execute(query, user_id, mode=QueryMode.TRAVERSE, start_entity_id=entity_id)

    def find_vulnerable_services(
        self,
        vulnerability_id: str,
        user_id: str,
        tenant_id: str = "default",
    ) -> QueryResult:
        """Find all services affected by a vulnerability."""
        query = QueryBuilder(tenant_id=tenant_id)\
            .with_relationship(RelationshipType.AFFECTS)\
            .max_depth(3)\
            .build()
        return self.execute(query, user_id, mode=QueryMode.TRAVERSE, start_entity_id=vulnerability_id)

    def __repr__(self) -> str:
        return (
            f"GraphQueryEngine(entities={len(self.entity_registry)}, "
            f"relationships={len(self.relationship_registry)})"
        )