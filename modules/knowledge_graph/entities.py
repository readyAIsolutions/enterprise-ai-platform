"""
Knowledge Graph Entities

Core entity model for the Knowledge Graph OS. Supports 40+ entity types
spanning users, projects, infrastructure, security, governance, and more.

Every entity carries identity, classification, versioning, and extensible
metadata for enterprise traceability.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, ClassVar, Dict, List, Optional, Set, Type


class EntityType(str, Enum):
    """All supported entity types in the knowledge graph."""

    # People & Organizations
    USER = "User"
    ORGANIZATION = "Organization"
    CUSTOMER = "Customer"
    VENDOR = "Vendor"

    # Projects & Planning
    PROJECT = "Project"
    PRODUCT = "Product"
    FEATURE = "Feature"
    REQUIREMENT = "Requirement"
    USER_STORY = "UserStory"
    DECISION = "Decision"
    POLICY = "Policy"
    STANDARD = "Standard"

    # Services & Infrastructure
    SERVICE = "Service"
    INFRASTRUCTURE = "Infrastructure"
    DEPLOYMENT = "Deployment"
    REPOSITORY = "Repository"

    # Code & Data
    FILE = "File"
    FUNCTION = "Function"
    CLASS = "Class"
    API = "API"
    DATABASE = "Database"
    TABLE = "Table"
    FIELD = "Field"
    MODEL = "Model"

    # AI & Automation
    AGENT = "Agent"
    PROMPT = "Prompt"
    TOOL = "Tool"

    # Security & Risk
    SECURITY_CONTROL = "SecurityControl"
    VULNERABILITY = "Vulnerability"
    RISK = "Risk"
    INCIDENT = "Incident"

    # Contracts & Documents
    CONTRACT = "Contract"
    DOCUMENT = "Document"
    RESEARCH_SOURCE = "ResearchSource"

    # Quality & Operations
    TEST = "Test"
    METRIC = "Metric"


# Labels that can be applied to any entity for cross-cutting concerns
ENTITY_LABELS: Set[str] = {
    "critical", "deprecated", "experimental", "internal", "public",
    "pii", "sensitive", "regulated", "third_party", "legacy",
    "active", "archived", "draft", "reviewed", "approved",
    "stale", "restricted",
}

@dataclass
class Entity:
    """
    Core entity in the knowledge graph.

    Every entity has a unique ID, a type from the EntityType enum, and
    carries classification, versioning, and extensible metadata.

    Attributes:
        id: Globally unique identifier (UUID v7 by default).
        entity_type: Discriminator from EntityType enum.
        name: Human-readable display name.
        description: Optional longer description.
        labels: Set of classification labels (see ENTITY_LABELS).
        aliases: Alternative names or identifiers for this entity.
        metadata: Arbitrary key-value extensions.
        created_at: Timestamp of first creation in the graph.
        updated_at: Timestamp of last modification.
        version: Monotonic version counter.
        tenant_id: Multi-tenant isolation key.
        project_id: Scope / project context.
        source_entity_id: If this entity was derived from another.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    entity_type: EntityType = EntityType.USER
    name: str = ""
    description: str = ""
    labels: Set[str] = field(default_factory=set)
    aliases: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1
    tenant_id: str = "default"
    project_id: str = ""
    source_entity_id: Optional[str] = None

    # Registry of entity subclasses by type
    _registry: ClassVar[Dict[EntityType, Type["Entity"]]] = {}

    def __init_subclass__(cls, entity_type: Optional[EntityType] = None, **kwargs: Any) -> None:
        """Auto-register subclasses by their entity_type."""
        super().__init_subclass__(**kwargs)
        if entity_type is not None:
            Entity._registry[entity_type] = cls

    def __post_init__(self) -> None:
        """Validate labels on construction."""
        invalid = self.labels - ENTITY_LABELS
        if invalid:
            raise ValueError(f"Invalid labels: {invalid}. Allowed: {ENTITY_LABELS}")

    def touch(self) -> None:
        """Update the modification timestamp and bump version."""
        self.updated_at = datetime.now(timezone.utc)
        self.version += 1

    def add_alias(self, alias: str) -> None:
        """Add an alias if not already present."""
        if alias not in self.aliases:
            self.aliases.append(alias)
            self.touch()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a dictionary for storage/indexing."""
        return {
            "id": self.id,
            "entity_type": self.entity_type.value,
            "name": self.name,
            "description": self.description,
            "labels": sorted(self.labels),
            "aliases": self.aliases,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "version": self.version,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "source_entity_id": self.source_entity_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Entity":
        """Deserialize from a dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            entity_type=EntityType(data["entity_type"]),
            name=data.get("name", ""),
            description=data.get("description", ""),
            labels=set(data.get("labels", [])),
            aliases=data.get("aliases", []),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(timezone.utc),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(timezone.utc),
            version=data.get("version", 1),
            tenant_id=data.get("tenant_id", "default"),
            project_id=data.get("project_id", ""),
            source_entity_id=data.get("source_entity_id"),
        )

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Entity):
            return NotImplemented
        return self.id == other.id

    def __repr__(self) -> str:
        return f"Entity(id={self.id!r}, type={self.entity_type.value!r}, name={self.name!r})"


class EntityRegistry:
    """
    Central registry for creating and looking up typed entities.

    Provides factory methods to create entities of specific types
    and lookup by name within a tenant/project scope.
    """

    def __init__(self) -> None:
        self._entities: Dict[str, Entity] = {}
        # Index: (tenant_id, project_id, name_lower) -> entity_id
        self._name_index: Dict[tuple, str] = {}
        # Index: alias -> entity_id
        self._alias_index: Dict[str, str] = {}

    def register(self, entity: Entity) -> Entity:
        """Register an entity, indexing it for fast lookup."""
        self._entities[entity.id] = entity
        key = (entity.tenant_id, entity.project_id, entity.name.lower())
        self._name_index[key] = entity.id
        for alias in entity.aliases:
            self._alias_index[alias.lower()] = entity.id
        return entity

    def create(
        self,
        entity_type: EntityType,
        name: str,
        **kwargs: Any,
    ) -> Entity:
        """
        Factory method: create and register an entity of the given type.

        If a registered subclass exists for this EntityType, it is used;
        otherwise a plain Entity is created.
        """
        cls = Entity._registry.get(entity_type, Entity)
        entity = cls(entity_type=entity_type, name=name, **kwargs)
        return self.register(entity)

    def get(self, entity_id: str) -> Optional[Entity]:
        """Retrieve an entity by ID."""
        return self._entities.get(entity_id)

    def get_by_name(
        self,
        name: str,
        tenant_id: str = "default",
        project_id: str = "",
    ) -> Optional[Entity]:
        """Look up an entity by name within tenant/project scope."""
        key = (tenant_id, project_id, name.lower())
        entity_id = self._name_index.get(key)
        if entity_id:
            return self._entities.get(entity_id)
        return None

    def get_by_alias(self, alias: str) -> Optional[Entity]:
        """Look up an entity by any of its aliases."""
        entity_id = self._alias_index.get(alias.lower())
        if entity_id:
            return self._entities.get(entity_id)
        return None

    def search(
        self,
        entity_type: Optional[EntityType] = None,
        tenant_id: Optional[str] = None,
        labels: Optional[Set[str]] = None,
        name_contains: Optional[str] = None,
    ) -> List[Entity]:
        """Search entities by type, tenant, labels, and/or name substring."""
        results: List[Entity] = []
        for entity in self._entities.values():
            if entity_type is not None and entity.entity_type != entity_type:
                continue
            if tenant_id is not None and entity.tenant_id != tenant_id:
                continue
            if labels is not None and not labels.issubset(entity.labels):
                continue
            if name_contains is not None and name_contains.lower() not in entity.name.lower():
                continue
            results.append(entity)
        return results

    def remove(self, entity_id: str) -> bool:
        """Remove an entity and its indices. Returns True if found."""
        entity = self._entities.pop(entity_id, None)
        if entity is None:
            return False
        key = (entity.tenant_id, entity.project_id, entity.name.lower())
        self._name_index.pop(key, None)
        for alias in entity.aliases:
            self._alias_index.pop(alias.lower(), None)
        return True

    def __len__(self) -> int:
        return len(self._entities)

    def __contains__(self, entity_id: str) -> bool:
        return entity_id in self._entities

    def __iter__(self):
        return iter(self._entities.values())


# ---- Specialized entity subclasses ----
# Registered via __init_subclass__ with entity_type kwarg


class UserEntity(Entity, entity_type=EntityType.USER):
    """User entity with email and role information."""

    def __init__(self, email: str = "", role: str = "", **kwargs: Any) -> None:
        kwargs.setdefault("entity_type", EntityType.USER)
        super().__init__(**kwargs)
        self.email = email
        self.role = role


class OrganizationEntity(Entity, entity_type=EntityType.ORGANIZATION):
    """Organization with domain and parent org reference."""

    def __init__(self, domain: str = "", parent_org_id: Optional[str] = None, **kwargs: Any) -> None:
        kwargs.setdefault("entity_type", EntityType.ORGANIZATION)
        super().__init__(**kwargs)
        self.domain = domain
        self.parent_org_id = parent_org_id


class ProjectEntity(Entity, entity_type=EntityType.PROJECT):
    """Project with lifecycle status and owner reference."""

    def __init__(
        self,
        status: str = "active",
        owner_id: Optional[str] = None,
        repository_ids: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("entity_type", EntityType.PROJECT)
        super().__init__(**kwargs)
        self.status = status
        self.owner_id = owner_id
        self.repository_ids = repository_ids or []


class VulnerabilityEntity(Entity, entity_type=EntityType.VULNERABILITY):
    """Security vulnerability with severity and CVE reference."""

    def __init__(
        self,
        severity: str = "medium",
        cve_id: str = "",
        cvss_score: float = 0.0,
        affected_component_ids: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("entity_type", EntityType.VULNERABILITY)
        super().__init__(**kwargs)
        self.severity = severity
        self.cve_id = cve_id
        self.cvss_score = cvss_score
        self.affected_component_ids = affected_component_ids or []


class APIServiceEntity(Entity, entity_type=EntityType.API):
    """API endpoint with method, path, and auth requirements."""

    def __init__(
        self,
        method: str = "GET",
        path: str = "/",
        auth_required: bool = True,
        rate_limit: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("entity_type", EntityType.API)
        super().__init__(**kwargs)
        self.method = method
        self.path = path
        self.auth_required = auth_required
        self.rate_limit = rate_limit


class DatabaseEntity(Entity, entity_type=EntityType.DATABASE):
    """Database with engine type and connection reference."""

    def __init__(
        self,
        engine: str = "",
        host: str = "",
        port: int = 0,
        schema_version: str = "",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("entity_type", EntityType.DATABASE)
        super().__init__(**kwargs)
        self.engine = engine
        self.host = host
        self.port = port
        self.schema_version = schema_version


class IncidentEntity(Entity, entity_type=EntityType.INCIDENT):
    """Security or operational incident with severity and timeline."""

    def __init__(
        self,
        severity: str = "medium",
        status: str = "open",
        reported_at: Optional[datetime] = None,
        resolved_at: Optional[datetime] = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("entity_type", EntityType.INCIDENT)
        super().__init__(**kwargs)
        self.severity = severity
        self.status = status
        self.reported_at = reported_at
        self.resolved_at = resolved_at


class KGTestCaseEntity(Entity, entity_type=EntityType.TEST):
    """Test case with type, status, and coverage information."""

    def __init__(
        self,
        test_type: str = "unit",
        status: str = "pending",
        coverage_target: str = "",
        last_run_at: Optional[datetime] = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("entity_type", EntityType.TEST)
        super().__init__(**kwargs)
        self.test_type = test_type
        self.status = status
        self.coverage_target = coverage_target
        self.last_run_at = last_run_at