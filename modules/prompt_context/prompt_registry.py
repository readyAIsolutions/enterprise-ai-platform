"""
Prompt Registry - Enterprise-grade prompt lifecycle management.

Capabilities:
- Prompt definition with objective, template, and metadata
- Semantic versioning with full history
- Lifecycle states: draft -> active -> deprecated -> archived
- Changelog tracking with performance metrics per version
- Rollback to any previous version
- Prompt ID generation with collision resistance
- Template variable validation
- A/B testing support with variant tracking
- Audit trail for all mutations
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, TypeVar, Generic
from collections import defaultdict
import re
import copy
import threading


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PromptStatus(str, Enum):
    """Lifecycle states for prompt templates."""
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"
    EXPERIMENTAL = "experimental"


class ChangeType(str, Enum):
    """Types of changes recorded in the changelog."""
    CREATED = "created"
    MODIFIED = "modified"
    VARIABLE_ADDED = "variable_added"
    VARIABLE_REMOVED = "variable_removed"
    OBJECTIVE_CHANGED = "objective_changed"
    TEMPLATE_CHANGED = "template_changed"
    TAGS_CHANGED = "tags_changed"
    METADATA_CHANGED = "metadata_changed"
    ROLLBACK = "rollback"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"
    ACTIVATED = "activated"


class MetricName(str, Enum):
    """Standard performance metric names."""
    ACCURACY = "accuracy"
    HALLUCINATION_RATE = "hallucination_rate"
    TOKEN_EFFICIENCY = "token_efficiency"
    LATENCY_MS = "latency_ms"
    COST = "cost"
    RETRIEVAL_QUALITY = "retrieval_quality"
    USER_SATISFACTION = "user_satisfaction"
    TASK_COMPLETION = "task_completion"
    TOOL_ACCURACY = "tool_accuracy"
    PROMPT_STABILITY = "prompt_stability"
    RESPONSE_CONSISTENCY = "response_consistency"


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class ChangelogEntry:
    """A single entry in the prompt's changelog."""
    version: str
    change_type: ChangeType
    description: str
    author: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    diff: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "change_type": self.change_type.value,
            "description": self.description,
            "author": self.author,
            "timestamp": self.timestamp.isoformat(),
            "diff": self.diff,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChangelogEntry":
        return cls(
            version=data["version"],
            change_type=ChangeType(data["change_type"]),
            description=data["description"],
            author=data["author"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            diff=data.get("diff"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class PerformanceMetric:
    """A single performance measurement for a prompt version."""
    version: str
    metric_name: MetricName
    value: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    sample_size: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "metric_name": self.metric_name.value,
            "value": self.value,
            "timestamp": self.timestamp.isoformat(),
            "sample_size": self.sample_size,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PerformanceMetric":
        return cls(
            version=data["version"],
            metric_name=MetricName(data["metric_name"]),
            value=data["value"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            sample_size=data.get("sample_size", 1),
            metadata=data.get("metadata", {}),
        )


@dataclass
class PromptVersion:
    """A specific version snapshot of a prompt."""
    version: str
    objective: str
    template: str
    variables: Set[str]
    status: PromptStatus
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    parent_version: Optional[str] = None
    checksum: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.checksum:
            self.checksum = self._compute_checksum()

    def _compute_checksum(self) -> str:
        content = f"{self.objective}|{self.template}|{sorted(self.variables)}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "objective": self.objective,
            "template": self.template,
            "variables": sorted(self.variables),
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "parent_version": self.parent_version,
            "checksum": self.checksum,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PromptVersion":
        return cls(
            version=data["version"],
            objective=data["objective"],
            template=data["template"],
            variables=set(data.get("variables", [])),
            status=PromptStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            parent_version=data.get("parent_version"),
            checksum=data.get("checksum", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class PromptRecord:
    """Full record of a prompt with all versions and history."""
    prompt_id: str
    name: str
    current_version: str
    versions: Dict[str, PromptVersion] = field(default_factory=dict)
    changelog: List[ChangelogEntry] = field(default_factory=list)
    performance_history: List[PerformanceMetric] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt_id": self.prompt_id,
            "name": self.name,
            "current_version": self.current_version,
            "versions": {k: v.to_dict() for k, v in self.versions.items()},
            "changelog": [c.to_dict() for c in self.changelog],
            "performance_history": [p.to_dict() for p in self.performance_history],
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PromptRecord":
        record = cls(
            prompt_id=data["prompt_id"],
            name=data["name"],
            current_version=data["current_version"],
            tags=data.get("tags", []),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            metadata=data.get("metadata", {}),
        )
        for vk, vv in data.get("versions", {}).items():
            record.versions[vk] = PromptVersion.from_dict(vv)
        for ce in data.get("changelog", []):
            record.changelog.append(ChangelogEntry.from_dict(ce))
        for pm in data.get("performance_history", []):
            record.performance_history.append(PerformanceMetric.from_dict(pm))
        return record


# ---------------------------------------------------------------------------
# Utility: Semantic Versioning
# ---------------------------------------------------------------------------

class SemanticVersion:
    """Semantic version parser and comparator (MAJOR.MINOR.PATCH[-pre])."""

    _PATTERN = re.compile(
        r"^(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z0-9.]+))?$"
    )

    def __init__(self, major: int, minor: int, patch: int, pre: Optional[str] = None):
        self.major = major
        self.minor = minor
        self.patch = patch
        self.pre = pre

    @classmethod
    def parse(cls, version_str: str) -> "SemanticVersion":
        m = cls._PATTERN.match(version_str.strip())
        if not m:
            raise ValueError(f"Invalid semantic version: {version_str}")
        return cls(
            major=int(m.group(1)),
            minor=int(m.group(2)),
            patch=int(m.group(3)),
            pre=m.group(4) or None,
        )

    @classmethod
    def try_parse(cls, version_str: str) -> Optional["SemanticVersion"]:
        try:
            return cls.parse(version_str)
        except ValueError:
            return None

    def bump_major(self) -> "SemanticVersion":
        return SemanticVersion(self.major + 1, 0, 0)

    def bump_minor(self) -> "SemanticVersion":
        return SemanticVersion(self.major, self.minor + 1, 0)

    def bump_patch(self) -> "SemanticVersion":
        return SemanticVersion(self.major, self.minor, self.patch + 1)

    def bump_pre(self, label: str = "alpha") -> "SemanticVersion":
        return SemanticVersion(self.major, self.minor, self.patch, pre=f"{label}.1" if not self.pre else f"{label}.1")

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.pre:
            base += f"-{self.pre}"
        return base

    def __repr__(self) -> str:
        return f"SemanticVersion({self})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemanticVersion):
            return NotImplemented
        return (self.major, self.minor, self.patch, self.pre) == (
            other.major, other.minor, other.patch, other.pre,
        )

    def __lt__(self, other: "SemanticVersion") -> bool:
        # Compare core versions
        if (self.major, self.minor, self.patch) != (other.major, other.minor, other.patch):
            return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)
        # Pre-release: no pre > any pre
        if self.pre is None and other.pre is not None:
            return False
        if self.pre is not None and other.pre is None:
            return True
        if self.pre is not None and other.pre is not None:
            return self.pre < other.pre
        return False

    def __le__(self, other: "SemanticVersion") -> bool:
        return self < other or self == other

    def __gt__(self, other: "SemanticVersion") -> bool:
        return not (self <= other)

    def __ge__(self, other: "SemanticVersion") -> bool:
        return not (self < other)

    def __hash__(self) -> int:
        return hash((self.major, self.minor, self.patch, self.pre))


# ---------------------------------------------------------------------------
# Prompt ID Generator
# ---------------------------------------------------------------------------

class PromptIDGenerator:
    """Generates collision-resistant prompt IDs."""

    PREFIX = "prmpt"

    @staticmethod
    def generate(name: str) -> str:
        """Generate a unique prompt ID from a name."""
        short_uuid = uuid.uuid4().hex[:8]
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.lower()).strip("-")[:32]
        return f"{PromptIDGenerator.PREFIX}_{slug}_{short_uuid}"

    @staticmethod
    def validate(prompt_id: str) -> bool:
        """Validate prompt ID format."""
        return bool(re.match(rf"^{PromptIDGenerator.PREFIX}_[a-z0-9\-]+_[a-f0-9]{{8}}$", prompt_id))

    @staticmethod
    def short_id(prompt_id: str) -> str:
        """Extract short identifier from prompt ID."""
        parts = prompt_id.split("_")
        return parts[1] if len(parts) >= 2 else prompt_id


# ---------------------------------------------------------------------------
# Prompt Registry
# ---------------------------------------------------------------------------

class PromptRegistryError(Exception):
    """Base exception for prompt registry errors."""


class PromptNotFoundError(PromptRegistryError):
    """Raised when a prompt is not found."""


class VersionNotFoundError(PromptRegistryError):
    """Raised when a specific version is not found."""


class InvalidTransitionError(PromptRegistryError):
    """Raised when an invalid status transition is attempted."""


class RollbackError(PromptRegistryError):
    """Raised when rollback fails."""


class PromptRegistry:
    """
    Enterprise-grade prompt registry with full lifecycle management.

    Features:
    - CRUD operations for prompt templates
    - Semantic versioning with automatic bump detection
    - Lifecycle state machine with valid transitions
    - Comprehensive changelog
    - Performance metrics per version
    - Rollback support
    - Thread-safe operations
    - Serialization/deserialization

    Usage::

        registry = PromptRegistry()
        prompt_id = registry.define(
            name="summarizer",
            objective="Summarize articles concisely",
            template="Summarize the following: {{content}}"
        )
        version = registry.get_current(prompt_id)
        assembled = registry.assemble(prompt_id, variables={"content": "..."})
    """

    # Valid state transitions
    VALID_TRANSITIONS: Dict[PromptStatus, Set[PromptStatus]] = {
        PromptStatus.DRAFT: {PromptStatus.ACTIVE, PromptStatus.EXPERIMENTAL, PromptStatus.ARCHIVED},
        PromptStatus.EXPERIMENTAL: {PromptStatus.DRAFT, PromptStatus.ACTIVE, PromptStatus.ARCHIVED},
        PromptStatus.ACTIVE: {PromptStatus.DEPRECATED, PromptStatus.ARCHIVED, PromptStatus.EXPERIMENTAL},
        PromptStatus.DEPRECATED: {PromptStatus.ACTIVE, PromptStatus.ARCHIVED},
        PromptStatus.ARCHIVED: {PromptStatus.DRAFT},
    }

    def __init__(self, storage_path: Optional[str] = None):
        self._prompts: Dict[str, PromptRecord] = {}
        self._lock = threading.RLock()
        self._storage_path = storage_path

    # ------------------------------------------------------------------
    # Core CRUD
    # ------------------------------------------------------------------

    def define(
        self,
        name: str,
        objective: str,
        template: str,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        author: str = "system",
        status: PromptStatus = PromptStatus.DRAFT,
    ) -> str:
        """
        Define a new prompt template and register it.

        Args:
            name: Human-readable prompt name.
            objective: What this prompt aims to accomplish.
            template: The prompt template with {{variable}} placeholders.
            tags: Optional categorization tags.
            metadata: Optional arbitrary metadata.
            author: Who is creating this prompt.
            status: Initial lifecycle status.

        Returns:
            The generated prompt_id.

        Raises:
            ValueError: If template has no variables or name is empty.
        """
        if not name or not name.strip():
            raise ValueError("Prompt name cannot be empty")
        if not objective or not objective.strip():
            raise ValueError("Prompt objective cannot be empty")
        if not template or not template.strip():
            raise ValueError("Prompt template cannot be empty")

        prompt_id = PromptIDGenerator.generate(name)
        variables = self._extract_variables(template)
        version_str = "0.1.0"

        version_obj = PromptVersion(
            version=version_str,
            objective=objective,
            template=template,
            variables=variables,
            status=status,
        )

        record = PromptRecord(
            prompt_id=prompt_id,
            name=name,
            current_version=version_str,
            versions={version_str: version_obj},
            tags=tags or [],
            metadata=metadata or {},
        )

        entry = ChangelogEntry(
            version=version_str,
            change_type=ChangeType.CREATED,
            description=f"Prompt '{name}' created with objective: {objective[:80]}",
            author=author,
        )
        record.changelog.append(entry)

        with self._lock:
            self._prompts[prompt_id] = record

        return prompt_id

    def get(self, prompt_id: str) -> PromptRecord:
        """Retrieve a prompt record by ID."""
        with self._lock:
            if prompt_id not in self._prompts:
                raise PromptNotFoundError(f"Prompt not found: {prompt_id}")
            return self._prompts[prompt_id]

    def get_version(self, prompt_id: str, version: str) -> PromptVersion:
        """Retrieve a specific version of a prompt."""
        record = self.get(prompt_id)
        if version not in record.versions:
            raise VersionNotFoundError(
                f"Version {version} not found for prompt {prompt_id}. "
                f"Available: {list(record.versions.keys())}"
            )
        return record.versions[version]

    def get_current(self, prompt_id: str) -> PromptVersion:
        """Retrieve the current (latest) version of a prompt."""
        record = self.get(prompt_id)
        return record.versions[record.current_version]

    def list_prompts(
        self,
        status: Optional[PromptStatus] = None,
        tags: Optional[List[str]] = None,
        search: Optional[str] = None,
    ) -> List[PromptRecord]:
        """List prompts with optional filtering."""
        with self._lock:
            results = list(self._prompts.values())

            if status:
                results = [
                    r for r in results
                    if r.versions[r.current_version].status == status
                ]
            if tags:
                required = set(tags)
                results = [r for r in results if required.issubset(set(r.tags))]
            if search:
                search_lower = search.lower()
                results = [
                    r for r in results
                    if search_lower in r.name.lower()
                    or any(search_lower in v.objective.lower() for v in r.versions.values())
                ]

            return results

    def update(
        self,
        prompt_id: str,
        objective: Optional[str] = None,
        template: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        author: str = "system",
        bump: Optional[str] = None,
    ) -> str:
        """
        Update a prompt, creating a new version.

        Args:
            prompt_id: The prompt to update.
            objective: New objective (or None to keep).
            template: New template (or None to keep).
            tags: New tags (or None to keep).
            metadata: New metadata (merged with existing).
            author: Who is making the change.
            bump: Version bump strategy: 'major', 'minor', 'patch', or auto-detect.

        Returns:
            The new version string.
        """
        record = self.get(prompt_id)
        current = record.versions[record.current_version]

        new_objective = objective if objective is not None else current.objective
        new_template = template if template is not None else current.template

        # Detect changes
        changes = []
        if objective is not None and objective != current.objective:
            changes.append(ChangeType.OBJECTIVE_CHANGED)
        if template is not None and template != current.template:
            changes.append(ChangeType.TEMPLATE_CHANGED)
        if tags is not None and set(tags) != set(record.tags):
            changes.append(ChangeType.TAGS_CHANGED)
        if metadata is not None:
            changes.append(ChangeType.METADATA_CHANGED)

        if not changes and not bump:
            # No actual changes
            return record.current_version

        change_type = changes[0] if changes else ChangeType.MODIFIED

        # Compute new version
        new_version = self._bump_version(
            current.version,
            strategy=bump,
            has_objective_change=(ChangeType.OBJECTIVE_CHANGED in changes),
            has_template_change=(ChangeType.TEMPLATE_CHANGED in changes),
        )

        # Determine new status
        new_status = current.status
        if current.status == PromptStatus.DEPRECATED and (
            ChangeType.OBJECTIVE_CHANGED in changes or ChangeType.TEMPLATE_CHANGED in changes
        ):
            new_status = PromptStatus.ACTIVE  # Un-deprecate on meaningful change

        new_variables = self._extract_variables(new_template)
        new_version_obj = PromptVersion(
            version=new_version,
            objective=new_objective,
            template=new_template,
            variables=new_variables,
            status=new_status,
            parent_version=current.version,
        )

        # Generate diff
        diff = self._generate_diff(current.template, new_template)

        entry = ChangelogEntry(
            version=new_version,
            change_type=change_type,
            description=self._build_change_description(changes, current.version, new_version),
            author=author,
            diff=diff,
        )

        with self._lock:
            record = self._prompts[prompt_id]  # Re-acquire under lock
            record.versions[new_version] = new_version_obj
            record.current_version = new_version
            record.changelog.append(entry)
            if tags is not None:
                record.tags = tags
            if metadata is not None:
                record.metadata = {**record.metadata, **metadata}
            record.updated_at = datetime.now(timezone.utc)

        return new_version

    def delete(self, prompt_id: str, hard: bool = False) -> None:
        """
        Delete a prompt. Soft delete sets status to ARCHIVED; hard delete removes entirely.
        """
        if hard:
            with self._lock:
                if prompt_id in self._prompts:
                    del self._prompts[prompt_id]
        else:
            self.set_status(prompt_id, PromptStatus.ARCHIVED)

    # ------------------------------------------------------------------
    # Status Management
    # ------------------------------------------------------------------

    def set_status(
        self,
        prompt_id: str,
        new_status: PromptStatus,
        author: str = "system",
    ) -> None:
        """Transition a prompt to a new lifecycle status."""
        record = self.get(prompt_id)
        current = record.versions[record.current_version]

        if new_status == current.status:
            return

        if new_status not in self.VALID_TRANSITIONS.get(current.status, set()):
            raise InvalidTransitionError(
                f"Cannot transition from {current.status.value} to {new_status.value}. "
                f"Valid transitions: {[s.value for s in self.VALID_TRANSITIONS.get(current.status, set())]}"
            )

        change_map = {
            PromptStatus.ACTIVE: ChangeType.ACTIVATED,
            PromptStatus.DEPRECATED: ChangeType.DEPRECATED,
            PromptStatus.ARCHIVED: ChangeType.ARCHIVED,
        }

        with self._lock:
            record = self._prompts[prompt_id]
            version_obj = record.versions[record.current_version]
            version_obj.status = new_status
            record.changelog.append(ChangelogEntry(
                version=record.current_version,
                change_type=change_map.get(new_status, ChangeType.MODIFIED),
                description=f"Status changed to {new_status.value}",
                author=author,
            ))
            record.updated_at = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Version Management
    # ------------------------------------------------------------------

    def rollback(
        self,
        prompt_id: str,
        target_version: str,
        author: str = "system",
    ) -> str:
        """
        Rollback to a previous version, creating a new version from it.

        Args:
            prompt_id: The prompt to rollback.
            target_version: The version to rollback to.
            author: Who is performing the rollback.

        Returns:
            The new version string after rollback.

        Raises:
            RollbackError: If target version doesn't exist or rollback is invalid.
        """
        record = self.get(prompt_id)

        if target_version not in record.versions:
            raise RollbackError(f"Target version {target_version} not found")

        if target_version == record.current_version:
            raise RollbackError(f"Already at version {target_version}")

        target = record.versions[target_version]
        current = record.versions[record.current_version]

        # Validate rollback is to a valid version
        if target.status == PromptStatus.ARCHIVED:
            raise RollbackError(f"Cannot rollback to archived version {target_version}")

        new_version = self._bump_version(current.version, strategy="major")

        new_version_obj = PromptVersion(
            version=new_version,
            objective=target.objective,
            template=target.template,
            variables=target.variables,
            status=PromptStatus.ACTIVE,
            parent_version=target_version,
            metadata={"rollback_from": current.version, **target.metadata},
        )

        diff = self._generate_diff(current.template, target.template)

        entry = ChangelogEntry(
            version=new_version,
            change_type=ChangeType.ROLLBACK,
            description=f"Rollback from {current.version} to {target_version}",
            author=author,
            diff=diff,
        )

        with self._lock:
            record = self._prompts[prompt_id]
            record.versions[new_version] = new_version_obj
            record.current_version = new_version
            record.changelog.append(entry)
            record.updated_at = datetime.now(timezone.utc)

        return new_version

    def get_history(self, prompt_id: str) -> List[ChangelogEntry]:
        """Get the full changelog history for a prompt."""
        record = self.get(prompt_id)
        return list(record.changelog)

    def get_version_tree(self, prompt_id: str) -> Dict[str, List[str]]:
        """Get the version ancestry tree."""
        record = self.get(prompt_id)
        tree: Dict[str, List[str]] = {}
        for ver, vobj in record.versions.items():
            parent = vobj.parent_version
            if parent:
                tree.setdefault(parent, []).append(ver)
            else:
                tree.setdefault("root", []).append(ver)
        return tree

    def compare_versions(
        self, prompt_id: str, version_a: str, version_b: str
    ) -> Dict[str, Any]:
        """Compare two versions of a prompt."""
        va = self.get_version(prompt_id, version_a)
        vb = self.get_version(prompt_id, version_b)

        return {
            "version_a": version_a,
            "version_b": version_b,
            "objective_changed": va.objective != vb.objective,
            "template_changed": va.template != vb.template,
            "variables_added": sorted(vb.variables - va.variables),
            "variables_removed": sorted(va.variables - vb.variables),
            "status_a": va.status.value,
            "status_b": vb.status.value,
            "diff": self._generate_diff(va.template, vb.template),
        }

    # ------------------------------------------------------------------
    # Performance Metrics
    # ------------------------------------------------------------------

    def record_metric(
        self,
        prompt_id: str,
        metric_name: MetricName,
        value: float,
        version: Optional[str] = None,
        sample_size: int = 1,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a performance metric for a prompt version."""
        record = self.get(prompt_id)
        ver = version or record.current_version

        metric = PerformanceMetric(
            version=ver,
            metric_name=metric_name,
            value=value,
            sample_size=sample_size,
            metadata=metadata or {},
        )

        with self._lock:
            record = self._prompts[prompt_id]
            record.performance_history.append(metric)

    def get_metrics(
        self,
        prompt_id: str,
        metric_name: Optional[MetricName] = None,
        version: Optional[str] = None,
        limit: int = 100,
    ) -> List[PerformanceMetric]:
        """Retrieve performance metrics with optional filtering."""
        record = self.get(prompt_id)
        metrics = record.performance_history

        if metric_name:
            metrics = [m for m in metrics if m.metric_name == metric_name]
        if version:
            metrics = [m for m in metrics if m.version == version]

        return metrics[-limit:]

    def get_aggregated_metrics(
        self, prompt_id: str, version: Optional[str] = None
    ) -> Dict[MetricName, Dict[str, float]]:
        """Get aggregated metrics (avg, min, max, count) per metric name."""
        record = self.get(prompt_id)
        metrics = record.performance_history
        if version:
            metrics = [m for m in metrics if m.version == version]

        grouped: Dict[MetricName, List[float]] = defaultdict(list)
        for m in metrics:
            grouped[m.metric_name].append(m.value)

        result = {}
        for name, values in grouped.items():
            result[name] = {
                "avg": sum(values) / len(values),
                "min": min(values),
                "max": max(values),
                "count": len(values),
                "latest": values[-1],
            }
        return result

    def get_best_version(
        self,
        prompt_id: str,
        by_metric: MetricName = MetricName.ACCURACY,
        higher_is_better: bool = True,
    ) -> Optional[str]:
        """Find the best-performing version by a given metric."""
        metrics = self.get_metrics(prompt_id, metric_name=by_metric)

        if not metrics:
            return None

        key = lambda m: m.value
        best = max(metrics, key=key) if higher_is_better else min(metrics, key=key)
        return best.version

    # ------------------------------------------------------------------
    # Assemble
    # ------------------------------------------------------------------

    def assemble(
        self,
        prompt_id: str,
        variables: Dict[str, str],
        version: Optional[str] = None,
        validate: bool = True,
    ) -> str:
        """
        Assemble a prompt by filling template variables.

        Args:
            prompt_id: The prompt to assemble.
            variables: Variable values to substitute.
            version: Specific version to use (defaults to current).
            validate: If True, raise on missing/extra variables.

        Returns:
            The assembled prompt string.

        Raises:
            ValueError: If required variables are missing (when validate=True).
        """
        prompt_version = (
            self.get_version(prompt_id, version)
            if version
            else self.get_current(prompt_id)
        )

        if prompt_version.status == PromptStatus.ARCHIVED:
            raise InvalidTransitionError(
                f"Cannot assemble archived prompt {prompt_id}"
            )

        if validate:
            missing = prompt_version.variables - set(variables.keys())
            if missing:
                raise ValueError(
                    f"Missing required variables for prompt '{prompt_id}': {missing}"
                )
            extra = set(variables.keys()) - prompt_version.variables
            if extra:
                raise ValueError(
                    f"Unknown variables provided for prompt '{prompt_id}': {extra}"
                )

        template = prompt_version.template
        for var_name, value in variables.items():
            placeholder = f"{{{{{var_name}}}}}"
            template = template.replace(placeholder, str(value))

        return template

    def validate_variables(
        self, prompt_id: str, variables: Dict[str, str], version: Optional[str] = None
    ) -> Tuple[bool, List[str], List[str]]:
        """
        Validate variables against a prompt template.

        Returns:
            Tuple of (is_valid, missing_vars, extra_vars).
        """
        prompt_version = (
            self.get_version(prompt_id, version)
            if version
            else self.get_current(prompt_id)
        )

        missing = sorted(prompt_version.variables - set(variables.keys()))
        extra = sorted(set(variables.keys()) - prompt_version.variables)
        return (len(missing) == 0 and len(extra) == 0, missing, extra)

    # ------------------------------------------------------------------
    # A/B Testing
    # ------------------------------------------------------------------

    def create_variant(
        self,
        prompt_id: str,
        name_suffix: str,
        objective: Optional[str] = None,
        template: Optional[str] = None,
        author: str = "system",
    ) -> str:
        """Create an A/B test variant of a prompt."""
        record = self.get(prompt_id)
        current = record.versions[record.current_version]

        variant_name = f"{record.name}-{name_suffix}"

        return self.define(
            name=variant_name,
            objective=objective or current.objective,
            template=template or current.template,
            tags=record.tags + ["variant", f"parent:{record.prompt_id}"],
            metadata={**record.metadata, "parent_prompt_id": record.prompt_id},
            author=author,
            status=PromptStatus.EXPERIMENTAL,
        )

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the entire registry to a dictionary."""
        with self._lock:
            return {
                prompt_id: record.to_dict()
                for prompt_id, record in self._prompts.items()
            }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PromptRegistry":
        """Deserialize a registry from a dictionary."""
        registry = cls()
        with registry._lock:
            for prompt_id, record_data in data.items():
                registry._prompts[prompt_id] = PromptRecord.from_dict(record_data)
        return registry

    def save(self, path: Optional[str] = None) -> None:
        """Persist the registry to disk as JSON."""
        target = path or self._storage_path
        if not target:
            raise ValueError("No storage path specified")
        data = self.to_dict()
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

    @classmethod
    def load(cls, path: str) -> "PromptRegistry":
        """Load the registry from a JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        registry = cls.from_dict(data)
        registry._storage_path = path
        return registry

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_variables(template: str) -> Set[str]:
        """Extract {{variable}} names from a template."""
        return set(re.findall(r"\{\{(\w+)\}\}", template))

    @staticmethod
    def _generate_diff(old_template: str, new_template: str) -> str:
        """Generate a simple line-based diff between two templates."""
        import difflib
        diff_lines = list(difflib.unified_diff(
            old_template.splitlines(keepends=True),
            new_template.splitlines(keepends=True),
            fromfile="previous",
            tofile="current",
            lineterm="",
        ))
        return "".join(diff_lines) if diff_lines else "(no changes)"

    @staticmethod
    def _build_change_description(
        changes: List[ChangeType], old_ver: str, new_ver: str
    ) -> str:
        """Build a human-readable change description."""
        change_names = [c.value for c in changes]
        return f"Updated from {old_ver} to {new_ver}: {', '.join(change_names)}"

    def _bump_version(
        self,
        current_version: str,
        strategy: Optional[str] = None,
        has_objective_change: bool = False,
        has_template_change: bool = False,
    ) -> str:
        """Compute the next version string."""
        try:
            ver = SemanticVersion.parse(current_version)
        except ValueError:
            # Non-semantic version: increment a simple counter
            try:
                num = int(current_version)
                return str(num + 1)
            except ValueError:
                return f"{current_version}.1"

        if strategy == "major":
            return str(ver.bump_major())
        elif strategy == "minor":
            return str(ver.bump_minor())
        elif strategy == "patch":
            return str(ver.bump_patch())
        else:
            # Auto-detect based on changes
            if has_objective_change:
                return str(ver.bump_major())
            elif has_template_change:
                return str(ver.bump_minor())
            else:
                return str(ver.bump_patch())

    def __len__(self) -> int:
        with self._lock:
            return len(self._prompts)

    def __contains__(self, prompt_id: str) -> bool:
        with self._lock:
            return prompt_id in self._prompts

    def __repr__(self) -> str:
        with self._lock:
            return f"PromptRegistry({len(self._prompts)} prompts)"


# ---------------------------------------------------------------------------
# Standalone utility functions
# ---------------------------------------------------------------------------

def detect_template_issues(template: str) -> List[str]:
    """Detect common issues in a prompt template."""
    issues = []

    # Check for unbalanced braces
    opens = template.count("{{")
    closes = template.count("}}")
    if opens != closes:
        issues.append(f"Unbalanced braces: {opens} opens, {closes} closes")

    # Check for empty variables
    empty_vars = re.findall(r"\{\{\s*\}\}", template)
    if empty_vars:
        issues.append(f"Empty variable placeholders found: {len(empty_vars)}")

    # Check for duplicate variable names
    vars_found = re.findall(r"\{\{(\w+)\}\}", template)
    if len(vars_found) != len(set(vars_found)):
        from collections import Counter
        duplicates = [v for v, c in Counter(vars_found).items() if c > 1]
        issues.append(f"Duplicate variable names: {duplicates}")

    # Check for very long template
    if len(template) > 100_000:
        issues.append(f"Template is very long ({len(template)} chars), may cause token issues")

    return issues