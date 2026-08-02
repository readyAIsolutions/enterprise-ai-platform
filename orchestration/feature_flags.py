"""
Config & Feature Flag System: Dynamic Config, Targeting Rules, Versioning, Audit.

Provides a production-grade feature-flag and dynamic-configuration layer with:
  - Boolean and multivariate feature flags
  - Targeting rules: by user, tenant, percentage rollout, environment, groups
  - Gradual rollouts (0% -> 100%) with consistent bucketing
  - Config versioning with rollback support
  - Full audit log of every flag/config change
  - Caching with TTL for hot-path evaluations
  - Kill switches for emergency toggles
  - Flag dependencies (flag A requires flag B)
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class FeatureFlagError(Exception):
    """Base exception for feature flag system errors."""
    pass


class FlagNotFoundError(FeatureFlagError):
    """A requested feature flag does not exist."""
    def __init__(self, flag_name: str):
        self.flag_name = flag_name
        super().__init__(f"Feature flag not found: {flag_name}")


class FlagDependencyError(FeatureFlagError):
    """A flag dependency is not satisfied."""
    def __init__(self, flag_name: str, dependency: str):
        self.flag_name = flag_name
        self.dependency = dependency
        super().__init__(
            f"Flag '{flag_name}' requires '{dependency}' to be enabled"
        )


class FlagValidationError(FeatureFlagError):
    """Flag configuration is invalid."""
    pass


class ConfigVersionError(FeatureFlagError):
    """Config version operation failed."""
    pass


# ---------------------------------------------------------------------------
# Enums and Constants
# ---------------------------------------------------------------------------

class FlagType(Enum):
    """The type of a feature flag."""
    BOOLEAN = auto()
    MULTIVARIATE = auto()
    NUMBER = auto()
    STRING = auto()
    JSON = auto()


class FlagState(Enum):
    """Operational state of a flag."""
    ACTIVE = auto()        # Normal evaluation
    KILLED = auto()        # Emergency kill — always returns default
    ARCHIVED = auto()      # No longer evaluated, kept for history
    STAGED = auto()        # Defined but not yet active (draft)


class TargetOperator(Enum):
    """Comparison operators for targeting rules."""
    EQUALS = auto()
    NOT_EQUALS = auto()
    IN = auto()
    NOT_IN = auto()
    CONTAINS = auto()
    STARTS_WITH = auto()
    ENDS_WITH = auto()
    GREATER_THAN = auto()
    LESS_THAN = auto()
    GREATER_EQUAL = auto()
    LESS_EQUAL = auto()
    REGEX = auto()
    EXISTS = auto()
    NOT_EXISTS = auto()


class AuditAction(Enum):
    """Recorded action types for the audit log."""
    FLAG_CREATED = auto()
    FLAG_UPDATED = auto()
    FLAG_DELETED = auto()
    FLAG_KILLED = auto()
    FLAG_RESTORED = auto()
    FLAG_ARCHIVED = auto()
    CONFIG_SET = auto()
    CONFIG_DELETED = auto()
    ROLLOUT_CHANGED = auto()
    TARGETING_CHANGED = auto()
    VERSION_ROLLBACK = auto()
    CACHE_CLEARED = auto()


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class TargetRule:
    """A single targeting condition evaluated against an evaluation context.

    Attributes:
        attribute: The context attribute key (e.g. 'user_id', 'tenant', 'country').
        operator: Comparison operator.
        value: Value to compare against.
        weight: Priority weight; higher-weight rules evaluate first.
    """
    attribute: str
    operator: TargetOperator
    value: Any
    weight: int = 0

    def evaluate(self, context: Dict[str, Any]) -> bool:
        attr_value = context.get(self.attribute)
        op = self.operator

        if op == TargetOperator.EXISTS:
            return self.attribute in context
        if op == TargetOperator.NOT_EXISTS:
            return self.attribute not in context
        if attr_value is None:
            return False
        if op == TargetOperator.EQUALS:
            return attr_value == self.value
        if op == TargetOperator.NOT_EQUALS:
            return attr_value != self.value
        if op == TargetOperator.IN:
            values = self.value if isinstance(self.value, (list, set, tuple)) else [self.value]
            return attr_value in values
        if op == TargetOperator.NOT_IN:
            values = self.value if isinstance(self.value, (list, set, tuple)) else [self.value]
            return attr_value not in values
        if op == TargetOperator.CONTAINS:
            try:
                return self.value in attr_value
            except TypeError:
                return False
        if op == TargetOperator.STARTS_WITH:
            return str(attr_value).startswith(str(self.value))
        if op == TargetOperator.ENDS_WITH:
            return str(attr_value).endswith(str(self.value))
        if op == TargetOperator.GREATER_THAN:
            return attr_value > self.value
        if op == TargetOperator.LESS_THAN:
            return attr_value < self.value
        if op == TargetOperator.GREATER_EQUAL:
            return attr_value >= self.value
        if op == TargetOperator.LESS_EQUAL:
            return attr_value <= self.value
        if op == TargetOperator.REGEX:
            import re
            return bool(re.search(str(self.value), str(attr_value)))
        return False


@dataclass
class TargetingRuleSet:
    """A set of targeting rules evaluated in priority order.

    Attributes:
        rules: Ordered targeting rules (highest weight first).
        default_serve: The value to serve if no rules match.
        rollout_percentage: Percentage of non-targeted traffic (0-100).
        rollout_salt: Hash salt for consistent percentage bucketing.
    """
    rules: List[TargetRule] = field(default_factory=list)
    default_serve: Any = None
    rollout_percentage: float = 100.0
    rollout_salt: str = ""

    def evaluate(self, context: Dict[str, Any]) -> Tuple[bool, Any]:
        """Evaluate targeting rules against context.

        Returns:
            (matched, value) — matched is True if a rule matched or the
            rollout bucket hit; value is the result to serve.
        """
        if not self.rules and self.rollout_percentage >= 100.0:
            return (True, self.default_serve)

        # Rules by descending weight
        sorted_rules = sorted(self.rules, key=lambda r: r.weight, reverse=True)
        for rule in sorted_rules:
            if rule.evaluate(context):
                return (True, self.default_serve)

        # No matching rule — check rollout for residual traffic
        if self.rollout_percentage >= 100.0:
            # 100% rollout but rules didn't match -> exclude
            return (False, self.default_serve)

        if self.rollout_percentage > 0.0:
            user_key = context.get("user_id", context.get("tenant", "unknown"))
            bucket = _hash_to_bucket(
                f"{self.rollout_salt}:{user_key}" if self.rollout_salt else user_key
            )
            if bucket <= self.rollout_percentage:
                return (True, self.default_serve)

        return (False, self.default_serve)


@dataclass
class FlagDefinition:
    """Complete definition of a feature flag.

    Attributes:
        name: Unique flag identifier.
        flag_type: The type of flag (boolean, multivariate, etc.).
        state: Operational state (active, killed, archived, staged).
        description: Human-readable description.
        enabled: For boolean flags, whether the flag is on.
        value: For multivariate/number/string/json flags, the current value.
        variations: For multivariate flags, allowed variations.
        targeting: Targeting rules and rollout configuration.
        dependencies: Other flag names this flag requires.
        tags: Organizational/search tags.
        owner: Person/team responsible for this flag.
        expires_at: Optional expiry timestamp (Unix).
        metadata: Arbitrary additional data.
    """
    name: str
    flag_type: FlagType = FlagType.BOOLEAN
    state: FlagState = FlagState.ACTIVE
    description: str = ""
    enabled: bool = False
    value: Any = None
    variations: Optional[List[Any]] = None
    targeting: TargetingRuleSet = field(default_factory=TargetingRuleSet)
    dependencies: List[str] = field(default_factory=list)
    tags: Set[str] = field(default_factory=set)
    owner: str = ""
    expires_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.flag_type == FlagType.BOOLEAN and self.value is None:
            self.value = self.enabled
        if self.variations is None:
            self.variations = []


@dataclass
class AuditEntry:
    """A single audit log entry recording a change to the flag system.

    Attributes:
        id: Unique entry identifier.
        timestamp: Unix timestamp of the action.
        action: The type of action performed.
        flag_name: Affected flag name (or config key).
        actor: Who performed the action (user/system).
        changes: Dict describing old -> new values.
        reason: Optional rationale for the change.
        version_before: Config version before the change.
        version_after: Config version after the change.
        metadata: Additional contextual data.
    """
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)
    action: AuditAction = AuditAction.FLAG_CREATED
    flag_name: str = ""
    actor: str = "system"
    changes: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    version_before: int = 0
    version_after: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Config Version Store
# ---------------------------------------------------------------------------

@dataclass
class ConfigSnapshot:
    """A point-in-time snapshot of all flags and their state."""
    version: int
    flags: Dict[str, FlagDefinition]
    timestamp: float = field(default_factory=time.time)
    description: str = ""


class ConfigVersionStore:
    """Stores versioned snapshots of the flag system for rollback support.

    Maintains an append-only history with bounded retention.
    """

    def __init__(self, max_versions: int = 100):
        self._versions: List[ConfigSnapshot] = []
        self._current_version: int = 0
        self.max_versions = max_versions
        self._lock = threading.RLock()

    @property
    def current_version(self) -> int:
        return self._current_version

    def snapshot(self, flags: Dict[str, FlagDefinition],
                 description: str = "") -> int:
        """Create a new versioned snapshot from the current flag state."""
        with self._lock:
            self._current_version += 1
            snapshot = ConfigSnapshot(
                version=self._current_version,
                flags=deepcopy(flags),
                description=description,
            )
            self._versions.append(snapshot)
            # Enforce max retention
            while len(self._versions) > self.max_versions:
                self._versions.pop(0)
            return self._current_version

    def get_version(self, version: int) -> Optional[ConfigSnapshot]:
        """Retrieve a specific version snapshot."""
        with self._lock:
            for snap in self._versions:
                if snap.version == version:
                    return snap
            return None

    def get_latest(self) -> Optional[ConfigSnapshot]:
        """Get the most recent snapshot."""
        with self._lock:
            return self._versions[-1] if self._versions else None

    def list_versions(self) -> List[ConfigSnapshot]:
        """Return all stored versions (newest last)."""
        with self._lock:
            return list(self._versions)

    def rollback_to(self, version: int) -> Dict[str, FlagDefinition]:
        """Rollback to a previous version, returning the restored flags.

        Raises:
            ConfigVersionError: If version does not exist.
        """
        with self._lock:
            snap = self.get_version(version)
            if snap is None:
                raise ConfigVersionError(
                    f"Version {version} not found. Available: "
                    f"{[v.version for v in self._versions]}"
                )
            # Rollback creates a new version with the old state
            self._current_version += 1
            restored = ConfigSnapshot(
                version=self._current_version,
                flags=deepcopy(snap.flags),
                description=f"Rollback from v{self._current_version - 1} to v{version}",
            )
            self._versions.append(restored)
            return dict(restored.flags)


# ---------------------------------------------------------------------------
# Audit Logger
# ---------------------------------------------------------------------------

class AuditLogger:
    """Records all flag and config changes for compliance and debugging."""

    def __init__(self, max_entries: int = 10_000):
        self._entries: List[AuditEntry] = []
        self.max_entries = max_entries
        self._lock = threading.RLock()

    def log(
        self,
        action: AuditAction,
        flag_name: str = "",
        actor: str = "system",
        changes: Optional[Dict[str, Any]] = None,
        reason: str = "",
        version_before: int = 0,
        version_after: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditEntry:
        """Record an audit entry."""
        entry = AuditEntry(
            action=action,
            flag_name=flag_name,
            actor=actor,
            changes=changes or {},
            reason=reason,
            version_before=version_before,
            version_after=version_after,
            metadata=metadata or {},
        )
        with self._lock:
            self._entries.append(entry)
            while len(self._entries) > self.max_entries:
                self._entries.pop(0)
        logger.debug("Audit: %s | %s | by %s | %s", action.name, flag_name, actor, reason)
        return entry

    def query(
        self,
        flag_name: Optional[str] = None,
        actor: Optional[str] = None,
        action: Optional[AuditAction] = None,
        since: Optional[float] = None,
        limit: int = 100,
    ) -> List[AuditEntry]:
        """Query the audit log with optional filters."""
        results: List[AuditEntry] = []
        with self._lock:
            for entry in reversed(self._entries):
                if flag_name and entry.flag_name != flag_name:
                    continue
                if actor and entry.actor != actor:
                    continue
                if action and entry.action != action:
                    continue
                if since and entry.timestamp < since:
                    continue
                results.append(entry)
                if len(results) >= limit:
                    break
        return results

    def get_history(self, flag_name: str) -> List[AuditEntry]:
        """Get the full audit history for a specific flag."""
        return self.query(flag_name=flag_name, limit=10_000)

    def clear(self) -> None:
        """Clear all audit entries."""
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


# ---------------------------------------------------------------------------
# Config / Feature Flag Engine
# ---------------------------------------------------------------------------

class FeatureFlagEngine:
    """Central engine for managing feature flags and dynamic configuration.

    Thread-safe. Supports:
      - Boolean and multivariate flags
      - Targeting rules (user, tenant, percentage rollout)
      - Kill switches
      - Flag dependencies
      - Config versioning and rollback
      - Full audit logging
      - Per-flag evaluation caching with TTL
    """

    def __init__(
        self,
        version_store: Optional[ConfigVersionStore] = None,
        audit_logger: Optional[AuditLogger] = None,
    ):
        self._flags: Dict[str, FlagDefinition] = {}
        self._config: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self.version_store = version_store or ConfigVersionStore()
        self.audit = audit_logger or AuditLogger()
        self._eval_cache: Dict[str, Tuple[float, bool, Any]] = {}
        self._cache_ttl: float = 5.0  # seconds
        self._cache_enabled: bool = True

    # ---- Flag CRUD ----

    def create_flag(
        self,
        name: str,
        flag_type: FlagType = FlagType.BOOLEAN,
        *,
        description: str = "",
        enabled: bool = False,
        value: Any = None,
        variations: Optional[List[Any]] = None,
        targeting: Optional[TargetingRuleSet] = None,
        dependencies: Optional[List[str]] = None,
        tags: Optional[Set[str]] = None,
        owner: str = "",
        expires_at: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
        actor: str = "system",
    ) -> FlagDefinition:
        """Create a new feature flag.

        Raises:
            FlagValidationError: If a flag with the same name already exists
                or validation fails.
        """
        with self._lock:
            if name in self._flags:
                raise FlagValidationError(f"Flag '{name}' already exists")

            definition = FlagDefinition(
                name=name,
                flag_type=flag_type,
                description=description,
                enabled=enabled,
                value=value if value is not None else enabled,
                variations=variations,
                targeting=targeting or TargetingRuleSet(),
                dependencies=dependencies or [],
                tags=tags or set(),
                owner=owner,
                expires_at=expires_at,
                metadata=metadata or {},
            )

            self._validate_flag(definition)
            self._flags[name] = definition

            ver = self.version_store.snapshot(self._flags,
                                              f"Created flag '{name}'")
            self.audit.log(
                AuditAction.FLAG_CREATED,
                flag_name=name,
                actor=actor,
                changes={"created": _flag_to_dict(definition)},
                reason=f"Flag '{name}' created",
                version_after=ver,
            )
            self._invalidate_cache(name)
            return definition

    def update_flag(
        self,
        name: str,
        *,
        enabled: Optional[bool] = None,
        value: Optional[Any] = None,
        description: Optional[str] = None,
        targeting: Optional[TargetingRuleSet] = None,
        dependencies: Optional[List[str]] = None,
        variations: Optional[List[Any]] = None,
        tags: Optional[Set[str]] = None,
        owner: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        actor: str = "system",
        reason: str = "",
    ) -> FlagDefinition:
        """Update an existing feature flag. Only provided fields are changed.

        Raises:
            FlagNotFoundError: If the flag does not exist.
        """
        with self._lock:
            if name not in self._flags:
                raise FlagNotFoundError(name)

            old = self._flags[name]
            old_dict = _flag_to_dict(old)
            changes: Dict[str, Any] = {}

            if enabled is not None:
                changes["enabled"] = {"old": old.enabled, "new": enabled}
                old.enabled = enabled
                if old.flag_type == FlagType.BOOLEAN:
                    old.value = enabled
            if value is not None:
                changes["value"] = {"old": old.value, "new": value}
                old.value = value
                if old.flag_type == FlagType.BOOLEAN:
                    old.enabled = bool(value)
            if description is not None:
                changes["description"] = {"old": old.description, "new": description}
                old.description = description
            if targeting is not None:
                changes["targeting"] = {"updated": True}
                old.targeting = targeting
            if dependencies is not None:
                changes["dependencies"] = {"old": old.dependencies, "new": dependencies}
                old.dependencies = dependencies
            if variations is not None:
                changes["variations"] = {"updated": True}
                old.variations = variations
            if tags is not None:
                old.tags = tags
            if owner is not None:
                old.owner = owner
            if metadata is not None:
                old.metadata = metadata

            self._validate_flag(old)
            self._flags[name] = old

            ver = self.version_store.snapshot(self._flags,
                                              f"Updated flag '{name}'")
            self.audit.log(
                AuditAction.FLAG_UPDATED,
                flag_name=name,
                actor=actor,
                changes=changes,
                reason=reason,
                version_before=ver - 1,
                version_after=ver,
            )
            self._invalidate_cache(name)
            return old

    def delete_flag(self, name: str, actor: str = "system",
                    reason: str = "") -> None:
        """Delete a feature flag permanently.

        Raises:
            FlagNotFoundError: If the flag does not exist.
        """
        with self._lock:
            if name not in self._flags:
                raise FlagNotFoundError(name)

            # Check if other flags depend on this one
            dependents = self._find_dependents(name)
            if dependents:
                raise FlagDependencyError(
                    name, f"Flags depend on this: {', '.join(dependents)}"
                )

            del self._flags[name]
            ver = self.version_store.snapshot(self._flags,
                                              f"Deleted flag '{name}'")
            self.audit.log(
                AuditAction.FLAG_DELETED,
                flag_name=name,
                actor=actor,
                reason=reason,
                version_after=ver,
            )
            self._invalidate_cache(name)

    def get_flag(self, name: str) -> FlagDefinition:
        """Retrieve a flag definition by name.

        Raises:
            FlagNotFoundError: If the flag does not exist.
        """
        with self._lock:
            if name not in self._flags:
                raise FlagNotFoundError(name)
            return self._flags[name]

    def list_flags(
        self,
        state: Optional[FlagState] = None,
        tag: Optional[str] = None,
        owner: Optional[str] = None,
    ) -> List[FlagDefinition]:
        """List flags with optional filters."""
        with self._lock:
            results = list(self._flags.values())
            if state is not None:
                results = [f for f in results if f.state == state]
            if tag is not None:
                results = [f for f in results if tag in f.tags]
            if owner is not None:
                results = [f for f in results if f.owner == owner]
            return results

    # ---- Flag Evaluation ----

    def is_enabled(
        self,
        name: str,
        context: Optional[Dict[str, Any]] = None,
        *,
        use_cache: bool = True,
    ) -> bool:
        """Evaluate a boolean feature flag.

        Returns True if the flag is enabled for the given context.
        """
        result = self._evaluate_flag(name, context or {}, use_cache)
        return bool(result)

    def get_value(
        self,
        name: str,
        context: Optional[Dict[str, Any]] = None,
        default: Any = None,
        *,
        use_cache: bool = True,
    ) -> Any:
        """Evaluate a feature flag and return its value.

        For boolean flags, returns True/False.
        For multivariate flags, returns the selected variation.
        """
        try:
            return self._evaluate_flag(name, context or {}, use_cache)
        except (FlagNotFoundError, FlagDependencyError) as exc:
            logger.warning("Flag evaluation error for '%s': %s", name, exc)
            return default

    def _evaluate_flag(
        self, name: str, context: Dict[str, Any], use_cache: bool
    ) -> Any:
        """Internal flag evaluation with caching."""
        # Check cache first
        if use_cache and self._cache_enabled:
            cache_key = _cache_key(name, context)
            cached = self._eval_cache.get(cache_key)
            if cached:
                ts, val, _ = cached
                if time.monotonic() - ts < self._cache_ttl:
                    return val

        with self._lock:
            if name not in self._flags:
                raise FlagNotFoundError(name)

            flag = self._flags[name]

            # Kill switch
            if flag.state == FlagState.KILLED:
                result = flag.value if flag.flag_type != FlagType.BOOLEAN else False
                self._set_cache(name, context, result)
                return result

            if flag.state == FlagState.ARCHIVED:
                result = flag.value if flag.flag_type != FlagType.BOOLEAN else False
                self._set_cache(name, context, result)
                return result

            # Check expiry
            if flag.expires_at and time.time() > flag.expires_at:
                logger.warning("Flag '%s' has expired", name)
                result = flag.value if flag.flag_type != FlagType.BOOLEAN else False
                self._set_cache(name, context, result)
                return result

            # Check dependencies
            for dep in flag.dependencies:
                dep_flag = self._flags.get(dep)
                if dep_flag is None or dep_flag.state != FlagState.ACTIVE:
                    raise FlagDependencyError(name, dep)
                # Recursively evaluate dependency (not under lock to avoid deadlock)
                if not self.is_enabled(dep, context, use_cache=False):
                    result = flag.value if flag.flag_type != FlagType.BOOLEAN else False
                    self._set_cache(name, context, result)
                    return result

            # Targeting evaluation
            matched, _ = flag.targeting.evaluate(context)

            if flag.flag_type == FlagType.BOOLEAN:
                result = flag.enabled and matched
            else:
                result = flag.value if matched else flag.targeting.default_serve

            self._set_cache(name, context, result)
            return result

    def _set_cache(self, name: str, context: Dict[str, Any], value: Any) -> None:
        if self._cache_enabled:
            self._eval_cache[_cache_key(name, context)] = (time.monotonic(), value, True)

    def _invalidate_cache(self, name: Optional[str] = None) -> None:
        """Invalidate the evaluation cache, optionally for a specific flag."""
        if name is None:
            self._eval_cache.clear()
        else:
            to_remove = [k for k in self._eval_cache if k.startswith(f"{name}:")]
            for k in to_remove:
                del self._eval_cache[k]

    # ---- Kill Switch ----

    def kill_flag(self, name: str, actor: str = "system",
                  reason: str = "") -> None:
        """Emergency-kill a flag — it will always return its default."""
        with self._lock:
            if name not in self._flags:
                raise FlagNotFoundError(name)

            old_state = self._flags[name].state
            self._flags[name].state = FlagState.KILLED

            ver = self.version_store.snapshot(self._flags,
                                              f"Killed flag '{name}'")
            self.audit.log(
                AuditAction.FLAG_KILLED,
                flag_name=name,
                actor=actor,
                changes={"state": {"old": old_state.name, "new": "KILLED"}},
                reason=reason,
                version_after=ver,
            )
            self._invalidate_cache(name)

    def restore_flag(self, name: str, actor: str = "system",
                     reason: str = "") -> None:
        """Restore a killed/archived flag to active state."""
        with self._lock:
            if name not in self._flags:
                raise FlagNotFoundError(name)
            old_state = self._flags[name].state
            self._flags[name].state = FlagState.ACTIVE

            ver = self.version_store.snapshot(self._flags,
                                              f"Restored flag '{name}'")
            self.audit.log(
                AuditAction.FLAG_RESTORED,
                flag_name=name,
                actor=actor,
                changes={"state": {"old": old_state.name, "new": "ACTIVE"}},
                reason=reason,
                version_after=ver,
            )
            self._invalidate_cache(name)

    def archive_flag(self, name: str, actor: str = "system",
                     reason: str = "") -> None:
        """Archive a flag so it is no longer evaluated."""
        with self._lock:
            if name not in self._flags:
                raise FlagNotFoundError(name)
            self._flags[name].state = FlagState.ARCHIVED

            ver = self.version_store.snapshot(self._flags,
                                              f"Archived flag '{name}'")
            self.audit.log(
                AuditAction.FLAG_ARCHIVED,
                flag_name=name,
                actor=actor,
                reason=reason,
                version_after=ver,
            )
            self._invalidate_cache(name)

    # ---- Rollout Helpers ----

    def set_rollout(
        self,
        name: str,
        percentage: float,
        salt: Optional[str] = None,
        actor: str = "system",
    ) -> None:
        """Update the rollout percentage for a flag.

        Args:
            name: Flag name.
            percentage: 0-100 rollout percentage.
            salt: Optional salt for consistent bucketing.
        """
        if not (0.0 <= percentage <= 100.0):
            raise FlagValidationError(
                f"Rollout percentage must be 0-100, got {percentage}"
            )
        flag = self.get_flag(name)
        old_pct = flag.targeting.rollout_percentage
        flag.targeting.rollout_percentage = percentage
        if salt is not None:
            flag.targeting.rollout_salt = salt

        with self._lock:
            self._flags[name] = flag
            ver = self.version_store.snapshot(self._flags,
                                              f"Rollout changed for '{name}'")
            self.audit.log(
                AuditAction.ROLLOUT_CHANGED,
                flag_name=name,
                actor=actor,
                changes={"rollout_percentage": {"old": old_pct, "new": percentage}},
                version_after=ver,
            )
            self._invalidate_cache(name)

    def add_targeting_rule(
        self,
        name: str,
        attribute: str,
        operator: TargetOperator,
        value: Any,
        weight: int = 0,
        actor: str = "system",
    ) -> None:
        """Add a targeting rule to a flag."""
        rule = TargetRule(attribute=attribute, operator=operator,
                          value=value, weight=weight)
        flag = self.get_flag(name)
        flag.targeting.rules.append(rule)

        with self._lock:
            self._flags[name] = flag
            ver = self.version_store.snapshot(self._flags,
                                              f"Targeting rule added to '{name}'")
            self.audit.log(
                AuditAction.TARGETING_CHANGED,
                flag_name=name,
                actor=actor,
                changes={"rule_added": {"attribute": attribute,
                                        "operator": operator.name}},
                version_after=ver,
            )
            self._invalidate_cache(name)

    def clear_targeting_rules(self, name: str, actor: str = "system") -> None:
        """Remove all targeting rules from a flag."""
        flag = self.get_flag(name)
        flag.targeting.rules.clear()

        with self._lock:
            self._flags[name] = flag
            ver = self.version_store.snapshot(self._flags,
                                              f"Targeting rules cleared for '{name}'")
            self.audit.log(
                AuditAction.TARGETING_CHANGED,
                flag_name=name,
                actor=actor,
                changes={"rules_cleared": True},
                version_after=ver,
            )
            self._invalidate_cache(name)

    # ---- Dynamic Config ----

    def set_config(self, key: str, value: Any, actor: str = "system",
                   reason: str = "") -> None:
        """Set a dynamic configuration value."""
        with self._lock:
            old = self._config.get(key)
            self._config[key] = value
            self.audit.log(
                AuditAction.CONFIG_SET,
                flag_name=key,
                actor=actor,
                changes={"config_set": {"old": old, "new": value}},
                reason=reason,
            )

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get a dynamic configuration value."""
        with self._lock:
            return self._config.get(key, default)

    def delete_config(self, key: str, actor: str = "system") -> None:
        """Remove a dynamic config key."""
        with self._lock:
            old = self._config.pop(key, None)
            self.audit.log(
                AuditAction.CONFIG_DELETED,
                flag_name=key,
                actor=actor,
                changes={"deleted": old},
            )

    def get_all_config(self) -> Dict[str, Any]:
        """Return a shallow copy of all config values."""
        with self._lock:
            return dict(self._config)

    # ---- Versioning ----

    def snapshot(self, description: str = "") -> int:
        """Create a versioned snapshot of the current flag state."""
        with self._lock:
            return self.version_store.snapshot(self._flags, description)

    def rollback(self, version: int, actor: str = "system",
                 reason: str = "") -> Dict[str, FlagDefinition]:
        """Rollback flags to a previous version."""
        with self._lock:
            restored = self.version_store.rollback_to(version)
            self._flags = restored
            self._invalidate_cache()
            ver = self.version_store.current_version
            self.audit.log(
                AuditAction.VERSION_ROLLBACK,
                actor=actor,
                changes={"rolled_back_to": version},
                reason=reason,
                version_after=ver,
            )
            return dict(self._flags)

    # ---- Cache Management ----

    def set_cache_ttl(self, ttl: float) -> None:
        """Set the evaluation cache TTL in seconds (0 to disable)."""
        self._cache_ttl = max(0.0, ttl)
        self._cache_enabled = self._cache_ttl > 0
        if not self._cache_enabled:
            self._eval_cache.clear()

    def clear_cache(self, flag_name: Optional[str] = None) -> None:
        """Clear the evaluation cache."""
        with self._lock:
            self._invalidate_cache(flag_name)
            self.audit.log(
                AuditAction.CACHE_CLEARED,
                flag_name=flag_name or "*",
                actor="system",
            )

    # ---- Validation ----

    def _validate_flag(self, flag: FlagDefinition) -> None:
        """Validate a flag definition for internal consistency."""
        if not flag.name or not flag.name.strip():
            raise FlagValidationError("Flag name is required")

        if flag.flag_type == FlagType.MULTIVARIATE and flag.variations:
            if flag.value is not None and flag.value not in flag.variations:
                raise FlagValidationError(
                    f"Flag '{flag.name}' value '{flag.value}' "
                    f"not in allowed variations: {flag.variations}"
                )

        if not (0.0 <= flag.targeting.rollout_percentage <= 100.0):
            raise FlagValidationError(
                f"Rollout percentage must be 0-100, "
                f"got {flag.targeting.rollout_percentage}"
            )

    def _find_dependents(self, name: str) -> List[str]:
        """Find all flags that depend on a given flag."""
        return [f.name for f in self._flags.values() if name in f.dependencies]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash_to_bucket(key: str, buckets: int = 10_000) -> float:
    """Hash a key into a percentage bucket (0.0 - 100.0).

    Uses SHA-256 for consistent, uniform distribution.
    """
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return (int(h[:8], 16) % buckets) / (buckets - 1) * 100.0


def _cache_key(flag_name: str, context: Dict[str, Any]) -> str:
    """Build a deterministic cache key from flag name and context."""
    ctx_str = json.dumps(context, sort_keys=True, default=str)
    return f"{flag_name}:{hashlib.md5(ctx_str.encode()).hexdigest()[:12]}"


def _flag_to_dict(flag: FlagDefinition) -> Dict[str, Any]:
    """Serialize a FlagDefinition to a dict for audit logging."""
    return {
        "name": flag.name,
        "type": flag.flag_type.name,
        "state": flag.state.name,
        "enabled": flag.enabled,
        "value": flag.value,
        "rollout_percentage": flag.targeting.rollout_percentage,
    }


# ---------------------------------------------------------------------------
# Convenience Factory
# ---------------------------------------------------------------------------

def create_engine(
    max_versions: int = 100,
    max_audit_entries: int = 10_000,
    cache_ttl: float = 5.0,
) -> FeatureFlagEngine:
    """Create a fully-configured FeatureFlagEngine with sensible defaults."""
    engine = FeatureFlagEngine(
        version_store=ConfigVersionStore(max_versions=max_versions),
        audit_logger=AuditLogger(max_entries=max_audit_entries),
    )
    engine.set_cache_ttl(cache_ttl)
    return engine