"""
ENI Enterprise — Tenant Manager: Full Multi-Tenant Isolation System

Provides complete tenant lifecycle management, RBAC, resource quotas,
configuration overrides, audit logging, and data partitioning for the
Eni Builder platform. Integrates with Platform Kernel via module interface.

Capabilities:
  - Tenant Model: ID, name, tier, quotas, isolation mode (shared/dedicated/hybrid)
  - Lifecycle: provision, suspend, reactivate, delete with data cleanup
  - RBAC: admin, developer, viewer, auditor + extensible custom roles
  - Resource Quotas: API calls, storage, agents, models, tokens
  - Tenant-level configuration overrides with inheritance
  - Comprehensive audit logging of all tenant operations
  - Tenant-aware data partitioning with secure isolation

Author: Eni Builder — Enterprise Platform
Version: 1.0.0
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import re
import threading
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    Union,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════

_TENANT_ID_PATTERN: re.Pattern = re.compile(r"^[a-z][a-z0-9\-]{0,61}[a-z0-9]$")
_MAX_ROLE_NAME_LENGTH: int = 64
_MAX_TENANT_NAME_LENGTH: int = 128
_MAX_CONFIG_KEY_LENGTH: int = 256
_DEFAULT_PAGE_SIZE: int = 50


# ═══════════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════════

class TenantStatus(Enum):
    """Lifecycle status of a tenant."""
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETING = "deleting"
    DELETED = "deleted"
    ARCHIVED = "archived"

    @property
    def is_operational(self) -> bool:
        """Whether the tenant can serve requests."""
        return self in (TenantStatus.ACTIVE,)

    @property
    def is_terminal(self) -> bool:
        """Whether the tenant has reached a terminal state."""
        return self in (TenantStatus.DELETED, TenantStatus.ARCHIVED)


class IsolationMode(Enum):
    """Data and compute isolation strategy for the tenant."""
    SHARED = "shared"           # Shared infrastructure, logical tenant separation
    DEDICATED = "dedicated"     # Dedicated infra, complete physical isolation
    HYBRID = "hybrid"           # Shared compute, dedicated storage (or vice versa)

    @property
    def requires_dedicated_infrastructure(self) -> bool:
        return self == IsolationMode.DEDICATED

    @property
    def allows_cross_tenant_caching(self) -> bool:
        return self == IsolationMode.SHARED


class SubscriptionTier(Enum):
    """Billing / capability tier for the tenant."""
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"
    UNLIMITED = "unlimited"

    def __ge__(self, other: "SubscriptionTier") -> bool:
        if self.__class__ is other.__class__:
            _order = {t: i for i, t in enumerate(SubscriptionTier)}
            return _order[self] >= _order[other]
        return NotImplemented

    def __le__(self, other: "SubscriptionTier") -> bool:
        if self.__class__ is other.__class__:
            _order = {t: i for i, t in enumerate(SubscriptionTier)}
            return _order[self] <= _order[other]
        return NotImplemented


class AuditEventType(Enum):
    """Categories of auditable events."""
    TENANT_CREATED = "tenant.created"
    TENANT_PROVISIONED = "tenant.provisioned"
    TENANT_SUSPENDED = "tenant.suspended"
    TENANT_REACTIVATED = "tenant.reactivated"
    TENANT_DELETED = "tenant.deleted"
    TENANT_UPDATED = "tenant.updated"
    TENANT_CONFIG_CHANGED = "tenant.config_changed"
    TENANT_CONFIG_RESET = "tenant.config_reset"
    ROLE_CREATED = "role.created"
    ROLE_UPDATED = "role.updated"
    ROLE_DELETED = "role.deleted"
    ROLE_ASSIGNED = "role.assigned"
    ROLE_REVOKED = "role.revoked"
    QUOTA_EXCEEDED = "quota.exceeded"
    QUOTA_UPDATED = "quota.updated"
    QUOTA_RESET = "quota.reset"
    ACCESS_DENIED = "access.denied"
    DATA_PARTITION_CREATED = "data.partition_created"
    DATA_PARTITION_DELETED = "data.partition_deleted"
    DATA_CLEANUP = "data.cleanup"


class Permission(Enum):
    """Granular permissions assignable to roles."""
    # Tenant administration
    TENANT_READ = "tenant:read"
    TENANT_WRITE = "tenant:write"
    TENANT_DELETE = "tenant:delete"
    TENANT_MANAGE_ROLES = "tenant:manage_roles"
    TENANT_MANAGE_QUOTAS = "tenant:manage_quotas"
    TENANT_VIEW_AUDIT = "tenant:view_audit"

    # Agent operations
    AGENT_CREATE = "agent:create"
    AGENT_READ = "agent:read"
    AGENT_UPDATE = "agent:update"
    AGENT_DELETE = "agent:delete"
    AGENT_EXECUTE = "agent:execute"
    AGENT_DEPLOY = "agent:deploy"

    # Model operations
    MODEL_INVOKE = "model:invoke"
    MODEL_FINE_TUNE = "model:fine_tune"
    MODEL_DEPLOY = "model:deploy"

    # Data operations
    DATA_READ = "data:read"
    DATA_WRITE = "data:write"
    DATA_DELETE = "data:delete"
    DATA_EXPORT = "data:export"
    DATA_IMPORT = "data:import"

    # Storage operations
    STORAGE_READ = "storage:read"
    STORAGE_WRITE = "storage:write"

    # Evaluation & monitoring
    EVALUATION_RUN = "evaluation:run"
    EVALUATION_READ = "evaluation:read"
    MONITORING_READ = "monitoring:read"
    MONITORING_CONFIGURE = "monitoring:configure"

    # Billing
    BILLING_READ = "billing:read"
    BILLING_MANAGE = "billing:manage"

    # Platform
    API_KEY_MANAGE = "api_key:manage"
    WEBHOOK_MANAGE = "webhook:manage"
    INTEGRATION_MANAGE = "integration:manage"


# ═══════════════════════════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Quota:
    """Resource quota configuration for a tenant."""
    max_api_calls_per_day: int = 1000
    max_api_calls_per_minute: int = 100
    max_storage_bytes: int = 10 * 1024 * 1024 * 1024  # 10 GB
    max_agents: int = 5
    max_models: int = 3
    max_tokens_per_day: int = 1_000_000
    max_tokens_per_request: int = 100_000
    max_concurrent_sessions: int = 10
    max_users: int = 25
    max_custom_roles: int = 10
    max_webhooks: int = 5

    # Rate-limiting windows (seconds)
    rate_limit_window_seconds: int = 60

    def as_dict(self) -> Dict[str, int]:
        return {
            "max_api_calls_per_day": self.max_api_calls_per_day,
            "max_api_calls_per_minute": self.max_api_calls_per_minute,
            "max_storage_bytes": self.max_storage_bytes,
            "max_agents": self.max_agents,
            "max_models": self.max_models,
            "max_tokens_per_day": self.max_tokens_per_day,
            "max_tokens_per_request": self.max_tokens_per_request,
            "max_concurrent_sessions": self.max_concurrent_sessions,
            "max_users": self.max_users,
            "max_custom_roles": self.max_custom_roles,
            "max_webhooks": self.max_webhooks,
            "rate_limit_window_seconds": self.rate_limit_window_seconds,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, int]) -> "Quota":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def merge(self, overrides: "Quota") -> "Quota":
        """Return a new Quota with non-default overrides applied."""
        merged = copy.deepcopy(self)
        for field_name in self.__dataclass_fields__:
            override_val = getattr(overrides, field_name)
            default_val = Quota.__dataclass_fields__[field_name].default
            if override_val != default_val:
                setattr(merged, field_name, override_val)
        return merged


# ── Tier default quotas ───────────────────────────────────────────────────────

_TIER_DEFAULT_QUOTAS: Dict[SubscriptionTier, Quota] = {
    SubscriptionTier.FREE: Quota(
        max_api_calls_per_day=100,
        max_api_calls_per_minute=10,
        max_storage_bytes=100 * 1024 * 1024,  # 100 MB
        max_agents=1,
        max_models=1,
        max_tokens_per_day=100_000,
        max_tokens_per_request=10_000,
        max_concurrent_sessions=2,
        max_users=3,
        max_custom_roles=0,
        max_webhooks=1,
    ),
    SubscriptionTier.STARTER: Quota(
        max_api_calls_per_day=1000,
        max_api_calls_per_minute=50,
        max_storage_bytes=5 * 1024 * 1024 * 1024,  # 5 GB
        max_agents=5,
        max_models=3,
        max_tokens_per_day=1_000_000,
        max_tokens_per_request=50_000,
        max_concurrent_sessions=10,
        max_users=25,
        max_custom_roles=3,
        max_webhooks=5,
    ),
    SubscriptionTier.PROFESSIONAL: Quota(
        max_api_calls_per_day=10_000,
        max_api_calls_per_minute=200,
        max_storage_bytes=50 * 1024 * 1024 * 1024,  # 50 GB
        max_agents=25,
        max_models=10,
        max_tokens_per_day=10_000_000,
        max_tokens_per_request=200_000,
        max_concurrent_sessions=50,
        max_users=100,
        max_custom_roles=10,
        max_webhooks=20,
    ),
    SubscriptionTier.ENTERPRISE: Quota(
        max_api_calls_per_day=100_000,
        max_api_calls_per_minute=1000,
        max_storage_bytes=500 * 1024 * 1024 * 1024,  # 500 GB
        max_agents=100,
        max_models=50,
        max_tokens_per_day=100_000_000,
        max_tokens_per_request=500_000,
        max_concurrent_sessions=200,
        max_users=500,
        max_custom_roles=50,
        max_webhooks=100,
    ),
    SubscriptionTier.UNLIMITED: Quota(
        max_api_calls_per_day=1_000_000,
        max_api_calls_per_minute=10_000,
        max_storage_bytes=5 * 1024 * 1024 * 1024 * 1024,  # 5 TB
        max_agents=1_000,
        max_models=200,
        max_tokens_per_day=1_000_000_000,
        max_tokens_per_request=2_000_000,
        max_concurrent_sessions=1_000,
        max_users=5_000,
        max_custom_roles=200,
        max_webhooks=500,
    ),
}


@dataclass
class Role:
    """A role definition with an associated set of permissions."""
    name: str
    permissions: Set[Permission] = field(default_factory=set)
    role_id: str = field(default_factory=lambda: f"role_{uuid.uuid4().hex[:12]}")
    description: str = ""
    is_system: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.name or len(self.name) > _MAX_ROLE_NAME_LENGTH:
            raise ValueError(
                f"Role name must be 1-{_MAX_ROLE_NAME_LENGTH} characters"
            )

    def has_permission(self, permission: Permission) -> bool:
        """Check if this role grants a specific permission."""
        return permission in self.permissions

    def has_any_permission(self, permissions: Set[Permission]) -> bool:
        """Check if the role grants any of the given permissions."""
        return bool(self.permissions & permissions)

    def has_all_permissions(self, permissions: Set[Permission]) -> bool:
        """Check if the role grants all of the given permissions."""
        return permissions.issubset(self.permissions)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role_id": self.role_id,
            "name": self.name,
            "description": self.description,
            "permissions": sorted(p.value for p in self.permissions),
            "is_system": self.is_system,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


# ── System-defined roles ──────────────────────────────────────────────────────

def _build_system_roles() -> Dict[str, Role]:
    """Construct the immutable system role definitions."""
    return {
        "admin": Role(
            name="admin",
            role_id="role_sys_admin",
            description="Full administrative access to the tenant",
            is_system=True,
            permissions={
                Permission.TENANT_READ,
                Permission.TENANT_WRITE,
                Permission.TENANT_DELETE,
                Permission.TENANT_MANAGE_ROLES,
                Permission.TENANT_MANAGE_QUOTAS,
                Permission.TENANT_VIEW_AUDIT,
                Permission.AGENT_CREATE,
                Permission.AGENT_READ,
                Permission.AGENT_UPDATE,
                Permission.AGENT_DELETE,
                Permission.AGENT_EXECUTE,
                Permission.AGENT_DEPLOY,
                Permission.MODEL_INVOKE,
                Permission.MODEL_FINE_TUNE,
                Permission.MODEL_DEPLOY,
                Permission.DATA_READ,
                Permission.DATA_WRITE,
                Permission.DATA_DELETE,
                Permission.DATA_EXPORT,
                Permission.DATA_IMPORT,
                Permission.STORAGE_READ,
                Permission.STORAGE_WRITE,
                Permission.EVALUATION_RUN,
                Permission.EVALUATION_READ,
                Permission.MONITORING_READ,
                Permission.MONITORING_CONFIGURE,
                Permission.BILLING_READ,
                Permission.BILLING_MANAGE,
                Permission.API_KEY_MANAGE,
                Permission.WEBHOOK_MANAGE,
                Permission.INTEGRATION_MANAGE,
            },
        ),
        "developer": Role(
            name="developer",
            role_id="role_sys_developer",
            description="Development access: create and manage agents, models, data",
            is_system=True,
            permissions={
                Permission.TENANT_READ,
                Permission.AGENT_CREATE,
                Permission.AGENT_READ,
                Permission.AGENT_UPDATE,
                Permission.AGENT_DELETE,
                Permission.AGENT_EXECUTE,
                Permission.AGENT_DEPLOY,
                Permission.MODEL_INVOKE,
                Permission.MODEL_FINE_TUNE,
                Permission.DATA_READ,
                Permission.DATA_WRITE,
                Permission.DATA_DELETE,
                Permission.DATA_EXPORT,
                Permission.DATA_IMPORT,
                Permission.STORAGE_READ,
                Permission.STORAGE_WRITE,
                Permission.EVALUATION_RUN,
                Permission.EVALUATION_READ,
                Permission.MONITORING_READ,
                Permission.API_KEY_MANAGE,
                Permission.WEBHOOK_MANAGE,
            },
        ),
        "viewer": Role(
            name="viewer",
            role_id="role_sys_viewer",
            description="Read-only access to tenant resources",
            is_system=True,
            permissions={
                Permission.TENANT_READ,
                Permission.AGENT_READ,
                Permission.DATA_READ,
                Permission.EVALUATION_READ,
                Permission.MONITORING_READ,
                Permission.BILLING_READ,
            },
        ),
        "auditor": Role(
            name="auditor",
            role_id="role_sys_auditor",
            description="Audit access: view logs, configurations, and monitoring data",
            is_system=True,
            permissions={
                Permission.TENANT_READ,
                Permission.TENANT_VIEW_AUDIT,
                Permission.AGENT_READ,
                Permission.DATA_READ,
                Permission.EVALUATION_READ,
                Permission.MONITORING_READ,
                Permission.MONITORING_CONFIGURE,
            },
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Tenant Data Model
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Tenant:
    """Core tenant entity representing a single organizational unit."""

    tenant_id: str
    name: str
    tier: SubscriptionTier = SubscriptionTier.FREE
    status: TenantStatus = TenantStatus.PROVISIONING
    isolation_mode: IsolationMode = IsolationMode.SHARED

    # Quotas
    quotas: Quota = field(default_factory=Quota)

    # RBAC state
    roles: Dict[str, Role] = field(default_factory=dict)
    user_role_assignments: Dict[str, Set[str]] = field(
        default_factory=dict
    )  # user_id -> {role_name}

    # Configuration overrides (tenant-level overrides of platform defaults)
    config_overrides: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    metadata: Dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    suspended_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None

    # Partitions
    data_partitions: List[str] = field(default_factory=list)

    # Internal tracking
    _audit_log: List["AuditEntry"] = field(default_factory=list, repr=False)

    # ── Validation ────────────────────────────────────────────────────────────

    def __post_init__(self) -> None:
        if not _TENANT_ID_PATTERN.match(self.tenant_id):
            raise ValueError(
                f"Invalid tenant_id '{self.tenant_id}': must match "
                f"pattern {_TENANT_ID_PATTERN.pattern}"
            )
        if not self.name or len(self.name) > _MAX_TENANT_NAME_LENGTH:
            raise ValueError(
                f"Tenant name must be 1-{_MAX_TENANT_NAME_LENGTH} characters"
            )
        # Apply tier defaults if quotas were not explicitly set
        if self.quotas == Quota():
            self.quotas = copy.deepcopy(_TIER_DEFAULT_QUOTAS.get(self.tier, Quota()))
        # Initialize system roles
        self._init_system_roles()

    def _init_system_roles(self) -> None:
        """Ensure system roles are always present."""
        system_roles = _build_system_roles()
        for role_name, role in system_roles.items():
            if role_name not in self.roles:
                self.roles[role_name] = copy.deepcopy(role)

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def active_users(self) -> Set[str]:
        """Return the set of user IDs that have at least one role assigned."""
        return set(self.user_role_assignments.keys())

    @property
    def custom_roles(self) -> Dict[str, Role]:
        """Return only non-system roles."""
        return {k: v for k, v in self.roles.items() if not v.is_system}

    @property
    def tenant_hash(self) -> str:
        """Stable hash for data partitioning."""
        return hashlib.sha256(self.tenant_id.encode()).hexdigest()[:16]

    # ── Role helpers ──────────────────────────────────────────────────────────

    def get_user_permissions(self, user_id: str) -> Set[Permission]:
        """Compute the effective permission set for a user (union of all assigned roles)."""
        role_names = self.user_role_assignments.get(user_id, set())
        perms: Set[Permission] = set()
        for rn in role_names:
            role = self.roles.get(rn)
            if role:
                perms |= role.permissions
        return perms

    def user_has_permission(self, user_id: str, permission: Permission) -> bool:
        """Check whether a user has a specific permission."""
        return permission in self.get_user_permissions(user_id)

    def user_has_any_permission(self, user_id: str, permissions: Set[Permission]) -> bool:
        """Check if user has at least one of the given permissions."""
        user_perms = self.get_user_permissions(user_id)
        return bool(user_perms & permissions)

    def user_has_all_permissions(self, user_id: str, permissions: Set[Permission]) -> bool:
        """Check if user has all of the given permissions."""
        user_perms = self.get_user_permissions(user_id)
        return permissions.issubset(user_perms)

    # ── Configuration ─────────────────────────────────────────────────────────

    def get_config(self, key: str, default: Any = None) -> Any:
        """Retrieve a tenant-level configuration override, falling back to default."""
        return self.config_overrides.get(key, default)

    def set_config(self, key: str, value: Any) -> None:
        """Set a tenant-level configuration override."""
        if len(key) > _MAX_CONFIG_KEY_LENGTH:
            raise ValueError(
                f"Config key must be <= {_MAX_CONFIG_KEY_LENGTH} characters"
            )
        self.config_overrides[key] = value
        self.updated_at = datetime.now(timezone.utc)

    def delete_config(self, key: str) -> bool:
        """Remove a config override. Returns True if key existed."""
        if key in self.config_overrides:
            del self.config_overrides[key]
            self.updated_at = datetime.now(timezone.utc)
            return True
        return False

    def reset_config(self) -> None:
        """Clear all configuration overrides."""
        self.config_overrides.clear()
        self.updated_at = datetime.now(timezone.utc)

    # ── Quota helpers ─────────────────────────────────────────────────────────

    def update_quotas(self, **kwargs: int) -> None:
        """Update specific quota fields."""
        for key, value in kwargs.items():
            if hasattr(self.quotas, key):
                setattr(self.quotas, key, value)
        self.updated_at = datetime.now(timezone.utc)

    def reset_quotas_to_tier_defaults(self) -> None:
        """Reset quotas to the defaults for the tenant's tier."""
        self.quotas = copy.deepcopy(
            _TIER_DEFAULT_QUOTAS.get(self.tier, Quota())
        )
        self.updated_at = datetime.now(timezone.utc)

    # ── Partitioning ──────────────────────────────────────────────────────────

    def get_partition_key(self) -> str:
        """Return the partition key for tenant-aware data routing."""
        return f"tn_{self.tenant_hash}"

    def add_partition(self, partition_name: str) -> None:
        """Register a named data partition for this tenant."""
        if partition_name not in self.data_partitions:
            self.data_partitions.append(partition_name)

    def remove_partition(self, partition_name: str) -> bool:
        """Remove a named data partition. Returns True if it existed."""
        if partition_name in self.data_partitions:
            self.data_partitions.remove(partition_name)
            return True
        return False

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self, include_audit: bool = False) -> Dict[str, Any]:
        """Serialize the tenant to a dictionary."""
        d: Dict[str, Any] = {
            "tenant_id": self.tenant_id,
            "name": self.name,
            "tier": self.tier.value,
            "status": self.status.value,
            "isolation_mode": self.isolation_mode.value,
            "quotas": self.quotas.as_dict(),
            "roles": {k: v.to_dict() for k, v in self.roles.items()},
            "user_role_assignments": {
                k: sorted(v) for k, v in self.user_role_assignments.items()
            },
            "config_overrides": self.config_overrides,
            "metadata": self.metadata,
            "data_partitions": self.data_partitions,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "suspended_at": self.suspended_at.isoformat() if self.suspended_at else None,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
        }
        if include_audit:
            d["audit_log"] = [e.to_dict() for e in self._audit_log]
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Tenant":
        """Deserialize a tenant from a dictionary."""
        tier = SubscriptionTier(data.get("tier", "free"))
        status = TenantStatus(data.get("status", "active"))
        isolation_mode = IsolationMode(data.get("isolation_mode", "shared"))
        quotas = Quota.from_dict(data.get("quotas", {}))
        roles: Dict[str, Role] = {}
        for role_name, role_data in data.get("roles", {}).items():
            if isinstance(role_data, dict):
                permissions = {
                    Permission(p) for p in role_data.get("permissions", [])
                }
                roles[role_name] = Role(
                    name=role_data.get("name", role_name),
                    role_id=role_data.get("role_id", f"role_{uuid.uuid4().hex[:12]}"),
                    permissions=permissions,
                    description=role_data.get("description", ""),
                    is_system=role_data.get("is_system", False),
                )
        user_role_assignments = data.get("user_role_assignments", {})
        return cls(
            tenant_id=data["tenant_id"],
            name=data["name"],
            tier=tier,
            status=status,
            isolation_mode=isolation_mode,
            quotas=quotas,
            roles=roles,
            user_role_assignments={
                k: set(v) for k, v in user_role_assignments.items()
            },
            config_overrides=data.get("config_overrides", {}),
            metadata=data.get("metadata", {}),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Audit Entry
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class AuditEntry:
    """A single record in the audit log."""
    event_type: AuditEventType
    tenant_id: str
    actor_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    entry_id: str = field(default_factory=lambda: f"audit_{uuid.uuid4().hex[:16]}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "event_type": self.event_type.value,
            "tenant_id": self.tenant_id,
            "actor_id": self.actor_id,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
            "success": self.success,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Tenant Manager
# ═══════════════════════════════════════════════════════════════════════════════

class TenantManagerError(Exception):
    """Base exception for tenant manager errors."""
    pass


class TenantNotFoundError(TenantManagerError):
    """Raised when a tenant is not found."""
    pass


class TenantStatusError(TenantManagerError):
    """Raised when an operation is invalid for the tenant's current status."""
    pass


class QuotaExceededError(TenantManagerError):
    """Raised when a resource quota is exceeded."""
    pass


class PermissionDeniedError(TenantManagerError):
    """Raised when an actor lacks required permissions."""
    pass


class RoleConflictError(TenantManagerError):
    """Raised when a role name conflicts with a system role."""
    pass


class TenantManager:
    """
    Central manager for multi-tenant isolation.

    Manages the full lifecycle of tenants, RBAC, resource quotas,
    configuration overrides, audit logging, and data partitioning.

    Thread-safe. Integrates with Platform Kernel via the module interface.

    Usage::

        manager = TenantManager()
        tenant = manager.provision_tenant("acme-corp", "Acme Corp",
                                          tier=SubscriptionTier.ENTERPRISE)
        manager.assign_role("acme-corp", "user-1", "admin")
        manager.check_quota("acme-corp", "api_calls", 1)
    """

    def __init__(self) -> None:
        self._tenants: Dict[str, Tenant] = {}
        self._lock: threading.RLock = threading.RLock()
        self._global_audit_log: List[AuditEntry] = []
        self._usage_counters: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: defaultdict(int)
        )
        self._cleanup_hooks: Dict[str, Callable[[Tenant], None]] = {}
        self._provisioning_hooks: Dict[str, Callable[[Tenant], None]] = {}

        logger.info("TenantManager initialized (v1.0.0)")

    # ── Hook registration ─────────────────────────────────────────────────────

    def register_cleanup_hook(
        self, hook_id: str, hook: Callable[[Tenant], None]
    ) -> None:
        """Register a callback invoked when a tenant is deleted."""
        with self._lock:
            self._cleanup_hooks[hook_id] = hook
            logger.debug("Registered cleanup hook '%s'", hook_id)

    def unregister_cleanup_hook(self, hook_id: str) -> bool:
        """Remove a cleanup hook. Returns True if it existed."""
        with self._lock:
            return self._cleanup_hooks.pop(hook_id, None) is not None

    def register_provisioning_hook(
        self, hook_id: str, hook: Callable[[Tenant], None]
    ) -> None:
        """Register a callback invoked after a tenant is provisioned."""
        with self._lock:
            self._provisioning_hooks[hook_id] = hook
            logger.debug("Registered provisioning hook '%s'", hook_id)

    def unregister_provisioning_hook(self, hook_id: str) -> bool:
        """Remove a provisioning hook. Returns True if it existed."""
        with self._lock:
            return self._provisioning_hooks.pop(hook_id, None) is not None

    # ── Audit helpers ─────────────────────────────────────────────────────────

    def _audit(
        self,
        event_type: AuditEventType,
        tenant_id: str,
        actor_id: str,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
    ) -> AuditEntry:
        """Record an audit event and append to both the tenant and global logs."""
        entry = AuditEntry(
            event_type=event_type,
            tenant_id=tenant_id,
            actor_id=actor_id,
            details=details or {},
            success=success,
        )
        with self._lock:
            self._global_audit_log.append(entry)
            tenant = self._get_tenant_unsafe(tenant_id)
            if tenant:
                tenant._audit_log.append(entry)
        logger.info(
            "AUDIT [%s] tenant=%s actor=%s success=%s",
            event_type.value,
            tenant_id,
            actor_id,
            success,
        )
        return entry

    def get_audit_log(
        self,
        tenant_id: Optional[str] = None,
        event_type: Optional[AuditEventType] = None,
        limit: int = _DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> List[AuditEntry]:
        """Query the audit log with optional filters."""
        with self._lock:
            source = (
                self._tenants[tenant_id]._audit_log
                if tenant_id and tenant_id in self._tenants
                else self._global_audit_log
            )
            results = source
            if event_type:
                results = [e for e in results if e.event_type == event_type]
            return results[offset : offset + limit]

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_tenant_unsafe(self, tenant_id: str) -> Optional[Tenant]:
        """Get a tenant without acquiring the lock (caller must hold _lock)."""
        return self._tenants.get(tenant_id)

    def _get_tenant(self, tenant_id: str) -> Tenant:
        """Get a tenant, raising TenantNotFoundError if missing."""
        with self._lock:
            tenant = self._tenants.get(tenant_id)
            if tenant is None:
                raise TenantNotFoundError(f"Tenant '{tenant_id}' not found")
            return tenant

    def _require_operational(self, tenant: Tenant, operation: str) -> None:
        """Raise if the tenant is not ACTIVE."""
        if not tenant.status.is_operational:
            raise TenantStatusError(
                f"Cannot {operation}: tenant '{tenant.tenant_id}' is {tenant.status.value}"
            )

    def _require_permission(
        self, tenant: Tenant, actor_id: str, permission: Permission, operation: str
    ) -> None:
        """Raise PermissionDeniedError if the actor lacks the permission.

        System actors bypass all permission checks — they represent the
        platform itself operating on behalf of internal processes.
        """
        if actor_id == "system":
            return
        if not tenant.user_has_permission(actor_id, permission):
            raise PermissionDeniedError(
                f"Actor '{actor_id}' lacks permission '{permission.value}' "
                f"for operation '{operation}' on tenant '{tenant.tenant_id}'"
            )

    # ── Lifecycle: Provision ──────────────────────────────────────────────────

    def provision_tenant(
        self,
        tenant_id: str,
        name: str,
        tier: Union[SubscriptionTier, str] = SubscriptionTier.FREE,
        isolation_mode: Union[IsolationMode, str] = IsolationMode.SHARED,
        quotas: Optional[Quota] = None,
        metadata: Optional[Dict[str, str]] = None,
        actor_id: str = "system",
    ) -> Tenant:
        """
        Provision a new tenant.

        Args:
            tenant_id: Unique identifier (lowercase, hyphens, alphanumeric).
            name: Human-readable tenant name.
            tier: Subscription tier determining default quotas.
            isolation_mode: Data/compute isolation strategy.
            quotas: Optional explicit quota overrides.
            metadata: Arbitrary key-value metadata.
            actor_id: ID of the actor performing provisioning.

        Returns:
            The newly created Tenant.

        Raises:
            ValueError: If tenant_id or name is invalid.
            TenantManagerError: If tenant_id is already in use.
        """
        if isinstance(tier, str):
            tier = SubscriptionTier(tier.lower())
        if isinstance(isolation_mode, str):
            isolation_mode = IsolationMode(isolation_mode.lower())

        with self._lock:
            if tenant_id in self._tenants:
                existing = self._tenants[tenant_id]
                if not existing.status.is_terminal:
                    raise TenantManagerError(
                        f"Tenant '{tenant_id}' already exists (status: {existing.status.value})"
                    )

            tenant = Tenant(
                tenant_id=tenant_id,
                name=name,
                tier=tier,
                status=TenantStatus.PROVISIONING,
                isolation_mode=isolation_mode,
                quotas=quotas if quotas else copy.deepcopy(
                    _TIER_DEFAULT_QUOTAS[tier]
                ),
                metadata=metadata or {},
            )
            self._tenants[tenant_id] = tenant

        self._audit(
            AuditEventType.TENANT_CREATED,
            tenant_id,
            actor_id,
            {"name": name, "tier": tier.value, "isolation_mode": isolation_mode.value},
        )

        # Transition to ACTIVE
        self._activate_tenant_internal(tenant, actor_id)

        # Fire provisioning hooks
        with self._lock:
            hooks = list(self._provisioning_hooks.values())
        for hook in hooks:
            try:
                hook(tenant)
            except Exception:
                logger.exception(
                    "Provisioning hook failed for tenant '%s'", tenant_id
                )

        self._audit(
            AuditEventType.TENANT_PROVISIONED,
            tenant_id,
            actor_id,
            {"status": TenantStatus.ACTIVE.value},
        )
        logger.info("Tenant '%s' provisioned successfully (tier=%s)", tenant_id, tier.value)
        return tenant

    def _activate_tenant_internal(self, tenant: Tenant, actor_id: str) -> None:
        """Transition tenant from PROVISIONING to ACTIVE."""
        with self._lock:
            if tenant.status != TenantStatus.PROVISIONING:
                raise TenantStatusError(
                    f"Cannot activate tenant '{tenant.tenant_id}' from "
                    f"status '{tenant.status.value}'"
                )
            tenant.status = TenantStatus.ACTIVE
            tenant.updated_at = datetime.now(timezone.utc)

    # ── Lifecycle: Suspend ────────────────────────────────────────────────────

    def suspend_tenant(
        self,
        tenant_id: str,
        actor_id: str = "system",
        reason: str = "",
        require_permission: bool = False,
    ) -> Tenant:
        """
        Suspend a tenant, halting all operations while preserving data.

        Args:
            tenant_id: The tenant to suspend.
            actor_id: Actor performing the suspension.
            reason: Human-readable reason for the suspension.
            require_permission: If True, checks actor has TENANT_WRITE.

        Returns:
            The updated Tenant.
        """
        tenant = self._get_tenant(tenant_id)
        if require_permission:
            self._require_permission(tenant, actor_id, Permission.TENANT_WRITE, "suspend")

        with self._lock:
            if tenant.status == TenantStatus.SUSPENDED:
                logger.info("Tenant '%s' already suspended", tenant_id)
                return tenant
            if tenant.status.is_terminal:
                raise TenantStatusError(
                    f"Cannot suspend tenant '{tenant_id}': status is "
                    f"'{tenant.status.value}'"
                )
            tenant.status = TenantStatus.SUSPENDED
            tenant.suspended_at = datetime.now(timezone.utc)
            tenant.updated_at = datetime.now(timezone.utc)

        self._audit(
            AuditEventType.TENANT_SUSPENDED,
            tenant_id,
            actor_id,
            {"reason": reason, "suspended_at": tenant.suspended_at.isoformat()},
        )
        logger.warning("Tenant '%s' suspended by '%s': %s", tenant_id, actor_id, reason)
        return tenant

    # ── Lifecycle: Reactivate ─────────────────────────────────────────────────

    def reactivate_tenant(
        self,
        tenant_id: str,
        actor_id: str = "system",
        require_permission: bool = False,
    ) -> Tenant:
        """
        Reactivate a suspended tenant, restoring normal operations.

        Args:
            tenant_id: The tenant to reactivate.
            actor_id: Actor performing the reactivation.
            require_permission: If True, checks actor has TENANT_WRITE.

        Returns:
            The updated Tenant.
        """
        tenant = self._get_tenant(tenant_id)
        if require_permission:
            self._require_permission(tenant, actor_id, Permission.TENANT_WRITE, "reactivate")

        with self._lock:
            if tenant.status != TenantStatus.SUSPENDED:
                raise TenantStatusError(
                    f"Cannot reactivate tenant '{tenant_id}': status is "
                    f"'{tenant.status.value}' (expected '{TenantStatus.SUSPENDED.value}')"
                )
            tenant.status = TenantStatus.ACTIVE
            tenant.suspended_at = None
            tenant.updated_at = datetime.now(timezone.utc)

        self._audit(
            AuditEventType.TENANT_REACTIVATED,
            tenant_id,
            actor_id,
            {"reactivated_at": tenant.updated_at.isoformat()},
        )
        logger.info("Tenant '%s' reactivated by '%s'", tenant_id, actor_id)
        return tenant

    # ── Lifecycle: Delete ─────────────────────────────────────────────────────

    def delete_tenant(
        self,
        tenant_id: str,
        actor_id: str = "system",
        force: bool = False,
        require_permission: bool = False,
    ) -> Tenant:
        """
        Delete a tenant with full data cleanup.

        Performs a multi-stage deletion:
          1. Mark as DELETING
          2. Execute registered cleanup hooks
          3. Remove data partitions
          4. Mark as DELETED
          5. Optionally remove from registry (force=True)

        Args:
            tenant_id: The tenant to delete.
            actor_id: Actor performing the deletion.
            force: If True, immediately remove from internal registry.
            require_permission: If True, checks actor has TENANT_DELETE.

        Returns:
            The deleted Tenant (in DELETED state).
        """
        tenant = self._get_tenant(tenant_id)
        if require_permission:
            self._require_permission(tenant, actor_id, Permission.TENANT_DELETE, "delete")

        with self._lock:
            if tenant.status.is_terminal:
                raise TenantStatusError(
                    f"Tenant '{tenant_id}' is already {tenant.status.value}"
                )
            tenant.status = TenantStatus.DELETING
            tenant.updated_at = datetime.now(timezone.utc)

        self._audit(
            AuditEventType.TENANT_DELETED,
            tenant_id,
            actor_id,
            {"stage": "deleting", "force": force},
        )

        # Execute cleanup hooks
        cleanup_errors: List[str] = []
        with self._lock:
            hooks = list(self._cleanup_hooks.values())
        for hook in hooks:
            try:
                hook(tenant)
            except Exception as exc:
                cleanup_errors.append(str(exc))
                logger.exception(
                    "Cleanup hook failed for tenant '%s': %s", tenant_id, exc
                )

        # Clear data partitions
        with self._lock:
            for partition in list(tenant.data_partitions):
                self._audit(
                    AuditEventType.DATA_PARTITION_DELETED,
                    tenant_id,
                    actor_id,
                    {"partition": partition},
                )
            tenant.data_partitions.clear()

            # Clear user assignments and roles
            tenant.user_role_assignments.clear()
            tenant.roles.clear()
            tenant.config_overrides.clear()

            tenant.status = TenantStatus.DELETED
            tenant.deleted_at = datetime.now(timezone.utc)
            tenant.updated_at = datetime.now(timezone.utc)

            self._audit(
                AuditEventType.DATA_CLEANUP,
                tenant_id,
                actor_id,
                {"cleanup_errors": cleanup_errors},
            )

            if force:
                del self._tenants[tenant_id]
                # Clean up usage counters
                self._usage_counters.pop(tenant_id, None)
                logger.info("Tenant '%s' force-deleted and removed from registry", tenant_id)

        logger.info(
            "Tenant '%s' deleted by '%s' (cleanup_errors=%d)",
            tenant_id, actor_id, len(cleanup_errors),
        )
        return tenant

    # ── Tenant queries ────────────────────────────────────────────────────────

    def get_tenant(self, tenant_id: str) -> Tenant:
        """Retrieve a tenant by ID."""
        return self._get_tenant(tenant_id)

    def list_tenants(
        self,
        status: Optional[TenantStatus] = None,
        tier: Optional[SubscriptionTier] = None,
        limit: int = _DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> List[Tenant]:
        """List tenants with optional filtering."""
        with self._lock:
            results = list(self._tenants.values())
            if status:
                results = [t for t in results if t.status == status]
            if tier:
                results = [t for t in results if t.tier == tier]
            return sorted(results, key=lambda t: t.created_at, reverse=True)[
                offset : offset + limit
            ]

    def tenant_exists(self, tenant_id: str) -> bool:
        """Check whether a tenant exists (in any non-terminal state)."""
        with self._lock:
            tenant = self._tenants.get(tenant_id)
            return tenant is not None and not tenant.status.is_terminal

    # ── RBAC: Role management ─────────────────────────────────────────────────

    def create_role(
        self,
        tenant_id: str,
        role_name: str,
        permissions: Set[Permission],
        actor_id: str = "system",
        description: str = "",
    ) -> Role:
        """
        Create a custom role for a tenant.

        Args:
            tenant_id: The tenant to create the role in.
            role_name: Unique role name (must not clash with system roles).
            permissions: Set of permissions for the role.
            actor_id: Actor creating the role.
            description: Optional human-readable description.

        Returns:
            The newly created Role.

        Raises:
            RoleConflictError: If the role name is already a system role.
            TenantManagerError: If the role name already exists.
        """
        tenant = self._get_tenant(tenant_id)
        self._require_operational(tenant, "create_role")
        self._require_permission(tenant, actor_id, Permission.TENANT_MANAGE_ROLES, "create_role")

        with self._lock:
            # Reject if system role
            system_roles = _build_system_roles()
            if role_name in system_roles:
                raise RoleConflictError(
                    f"'{role_name}' is a reserved system role"
                )
            if role_name in tenant.roles:
                raise TenantManagerError(
                    f"Role '{role_name}' already exists in tenant '{tenant_id}'"
                )
            # Enforce max custom roles quota
            if len(tenant.custom_roles) >= tenant.quotas.max_custom_roles:
                raise QuotaExceededError(
                    f"Tenant '{tenant_id}' has reached max custom roles "
                    f"({tenant.quotas.max_custom_roles})"
                )

            role = Role(
                name=role_name,
                permissions=permissions,
                description=description,
            )
            tenant.roles[role_name] = role
            tenant.updated_at = datetime.now(timezone.utc)

        self._audit(
            AuditEventType.ROLE_CREATED,
            tenant_id,
            actor_id,
            {"role_name": role_name, "permissions": sorted(p.value for p in permissions)},
        )
        logger.info("Role '%s' created in tenant '%s'", role_name, tenant_id)
        return role

    def update_role(
        self,
        tenant_id: str,
        role_name: str,
        permissions: Optional[Set[Permission]] = None,
        description: Optional[str] = None,
        actor_id: str = "system",
    ) -> Role:
        """Update a custom role's permissions and/or description."""
        tenant = self._get_tenant(tenant_id)
        self._require_operational(tenant, "update_role")
        self._require_permission(tenant, actor_id, Permission.TENANT_MANAGE_ROLES, "update_role")

        with self._lock:
            role = tenant.roles.get(role_name)
            if role is None:
                raise TenantManagerError(
                    f"Role '{role_name}' not found in tenant '{tenant_id}'"
                )
            if role.is_system:
                raise RoleConflictError(
                    f"Cannot modify system role '{role_name}'"
                )

            if permissions is not None:
                role.permissions = permissions
            if description is not None:
                role.description = description
            role.updated_at = datetime.now(timezone.utc)
            tenant.updated_at = datetime.now(timezone.utc)

        self._audit(
            AuditEventType.ROLE_UPDATED,
            tenant_id,
            actor_id,
            {
                "role_name": role_name,
                "permissions": sorted(p.value for p in role.permissions),
            },
        )
        logger.info("Role '%s' updated in tenant '%s'", role_name, tenant_id)
        return role

    def delete_role(
        self,
        tenant_id: str,
        role_name: str,
        actor_id: str = "system",
    ) -> bool:
        """
        Delete a custom role. Revokes it from all assigned users.

        Returns True if the role existed and was deleted.
        """
        tenant = self._get_tenant(tenant_id)
        self._require_operational(tenant, "delete_role")
        self._require_permission(tenant, actor_id, Permission.TENANT_MANAGE_ROLES, "delete_role")

        with self._lock:
            if role_name not in tenant.roles:
                return False
            role = tenant.roles[role_name]
            if role.is_system:
                raise RoleConflictError(
                    f"Cannot delete system role '{role_name}'"
                )

            del tenant.roles[role_name]
            # Revoke from all users
            revoked_users: List[str] = []
            for user_id, assigned in list(tenant.user_role_assignments.items()):
                if role_name in assigned:
                    assigned.discard(role_name)
                    revoked_users.append(user_id)
                    if not assigned:
                        del tenant.user_role_assignments[user_id]
            tenant.updated_at = datetime.now(timezone.utc)

        self._audit(
            AuditEventType.ROLE_DELETED,
            tenant_id,
            actor_id,
            {"role_name": role_name, "revoked_from_users": revoked_users},
        )
        logger.info(
            "Role '%s' deleted from tenant '%s', revoked from %d users",
            role_name, tenant_id, len(revoked_users),
        )
        return True

    def get_roles(self, tenant_id: str) -> Dict[str, Role]:
        """Get all roles (system + custom) for a tenant."""
        return dict(self._get_tenant(tenant_id).roles)

    # ── RBAC: User-role assignments ───────────────────────────────────────────

    def assign_role(
        self,
        tenant_id: str,
        user_id: str,
        role_name: str,
        actor_id: str = "system",
    ) -> None:
        """
        Assign a role to a user within a tenant.

        Raises:
            TenantStatusError: If tenant is not operational.
            TenantManagerError: If the role does not exist.
        """
        tenant = self._get_tenant(tenant_id)
        self._require_operational(tenant, "assign_role")
        self._require_permission(tenant, actor_id, Permission.TENANT_MANAGE_ROLES, "assign_role")

        with self._lock:
            if role_name not in tenant.roles:
                raise TenantManagerError(
                    f"Role '{role_name}' not found in tenant '{tenant_id}'"
                )
            if user_id not in tenant.user_role_assignments:
                tenant.user_role_assignments[user_id] = set()
            tenant.user_role_assignments[user_id].add(role_name)
            tenant.updated_at = datetime.now(timezone.utc)

        self._audit(
            AuditEventType.ROLE_ASSIGNED,
            tenant_id,
            actor_id,
            {"user_id": user_id, "role_name": role_name},
        )
        logger.info("Role '%s' assigned to user '%s' in tenant '%s'", role_name, user_id, tenant_id)

    def revoke_role(
        self,
        tenant_id: str,
        user_id: str,
        role_name: str,
        actor_id: str = "system",
    ) -> bool:
        """
        Revoke a role from a user. Returns True if the role was assigned.
        """
        tenant = self._get_tenant(tenant_id)
        self._require_operational(tenant, "revoke_role")
        self._require_permission(tenant, actor_id, Permission.TENANT_MANAGE_ROLES, "revoke_role")

        with self._lock:
            assigned = tenant.user_role_assignments.get(user_id, set())
            if role_name not in assigned:
                return False
            assigned.discard(role_name)
            if not assigned:
                del tenant.user_role_assignments[user_id]
            tenant.updated_at = datetime.now(timezone.utc)

        self._audit(
            AuditEventType.ROLE_REVOKED,
            tenant_id,
            actor_id,
            {"user_id": user_id, "role_name": role_name},
        )
        logger.info(
            "Role '%s' revoked from user '%s' in tenant '%s'",
            role_name, user_id, tenant_id,
        )
        return True

    def get_user_roles(self, tenant_id: str, user_id: str) -> Set[str]:
        """Get the set of role names assigned to a user."""
        tenant = self._get_tenant(tenant_id)
        return set(tenant.user_role_assignments.get(user_id, set()))

    def get_user_permissions(self, tenant_id: str, user_id: str) -> Set[Permission]:
        """Get the effective permission set for a user."""
        tenant = self._get_tenant(tenant_id)
        return tenant.get_user_permissions(user_id)

    def check_permission(
        self, tenant_id: str, user_id: str, permission: Permission
    ) -> bool:
        """Check whether a user has a specific permission."""
        tenant = self._get_tenant(tenant_id)
        if not tenant.status.is_operational:
            return False
        result = tenant.user_has_permission(user_id, permission)
        if not result:
            self._audit(
                AuditEventType.ACCESS_DENIED,
                tenant_id,
                user_id,
                {"permission": permission.value},
                success=False,
            )
        return result

    # ── Quotas ────────────────────────────────────────────────────────────────

    def get_quotas(self, tenant_id: str) -> Quota:
        """Get the current quotas for a tenant."""
        return self._get_tenant(tenant_id).quotas

    def update_quotas(
        self,
        tenant_id: str,
        actor_id: str = "system",
        **kwargs: int,
    ) -> Quota:
        """Update specific quota fields for a tenant."""
        tenant = self._get_tenant(tenant_id)

        with self._lock:
            tenant.update_quotas(**kwargs)

        self._audit(
            AuditEventType.QUOTA_UPDATED,
            tenant_id,
            actor_id,
            {"updated_fields": kwargs},
        )
        return tenant.quotas

    def reset_quotas(self, tenant_id: str, actor_id: str = "system") -> Quota:
        """Reset quotas to tier defaults."""
        tenant = self._get_tenant(tenant_id)
        with self._lock:
            tenant.reset_quotas_to_tier_defaults()
        self._audit(AuditEventType.QUOTA_RESET, tenant_id, actor_id)
        return tenant.quotas

    def check_quota(
        self,
        tenant_id: str,
        resource: str,
        requested: int = 1,
    ) -> bool:
        """
        Check whether a resource usage would exceed the tenant's quota.

        Args:
            tenant_id: The tenant to check.
            resource: One of 'api_calls', 'storage_bytes', 'tokens', 'agents',
                      'models', 'sessions', 'users'.
            requested: The amount being requested.

        Returns:
            True if within quota, raises QuotaExceededError otherwise.
        """
        tenant = self._get_tenant(tenant_id)
        self._require_operational(tenant, f"check_quota:{resource}")

        quota = tenant.quotas
        with self._lock:
            current = self._usage_counters[tenant_id].get(resource, 0)

        resource_map = {
            "api_calls": quota.max_api_calls_per_day,
            "storage_bytes": quota.max_storage_bytes,
            "tokens": quota.max_tokens_per_day,
            "agents": quota.max_agents,
            "models": quota.max_models,
            "sessions": quota.max_concurrent_sessions,
            "users": quota.max_users,
        }

        limit = resource_map.get(resource)
        if limit is None:
            logger.warning("Unknown resource '%s' for quota check on '%s'", resource, tenant_id)
            return True  # Unknown resources pass through

        if current + requested > limit:
            msg = (
                f"Quota exceeded for '{resource}' in tenant '{tenant_id}': "
                f"{current + requested} > {limit}"
            )
            self._audit(
                AuditEventType.QUOTA_EXCEEDED,
                tenant_id,
                "system",
                {
                    "resource": resource,
                    "current": current,
                    "requested": requested,
                    "limit": limit,
                },
                success=False,
            )
            raise QuotaExceededError(msg)

        return True

    def record_usage(
        self,
        tenant_id: str,
        resource: str,
        amount: int = 1,
        check_quota: bool = True,
    ) -> int:
        """
        Record resource usage for a tenant, optionally checking quota first.

        Returns the new total for the resource.
        """
        if check_quota:
            self.check_quota(tenant_id, resource, amount)

        with self._lock:
            self._usage_counters[tenant_id][resource] += amount
            new_total = self._usage_counters[tenant_id][resource]
        return new_total

    def get_usage(self, tenant_id: str) -> Dict[str, int]:
        """Get current resource usage snapshot for a tenant."""
        tenant = self._get_tenant(tenant_id)
        with self._lock:
            return dict(self._usage_counters[tenant.tenant_id])

    def reset_usage(self, tenant_id: str) -> None:
        """Reset all usage counters for a tenant."""
        with self._lock:
            self._usage_counters.pop(tenant_id, None)
        logger.info("Usage counters reset for tenant '%s'", tenant_id)

    # ── Configuration ─────────────────────────────────────────────────────────

    def get_config(self, tenant_id: str, key: str, default: Any = None) -> Any:
        """Get a tenant configuration override."""
        tenant = self._get_tenant(tenant_id)
        return tenant.get_config(key, default)

    def set_config(
        self,
        tenant_id: str,
        key: str,
        value: Any,
        actor_id: str = "system",
    ) -> None:
        """Set a tenant-level configuration override."""
        tenant = self._get_tenant(tenant_id)
        self._require_operational(tenant, "set_config")
        old_value = tenant.get_config(key, sentinel := object())
        with self._lock:
            tenant.set_config(key, value)
        self._audit(
            AuditEventType.TENANT_CONFIG_CHANGED,
            tenant_id,
            actor_id,
            {
                "key": key,
                "old_value": str(old_value) if old_value is not sentinel else None,
                "new_value": str(value),
            },
        )

    def delete_config(
        self, tenant_id: str, key: str, actor_id: str = "system"
    ) -> bool:
        """Remove a configuration override. Returns True if removed."""
        tenant = self._get_tenant(tenant_id)
        self._require_operational(tenant, "delete_config")
        with self._lock:
            existed = tenant.delete_config(key)
        if existed:
            self._audit(
                AuditEventType.TENANT_CONFIG_RESET,
                tenant_id,
                actor_id,
                {"key": key},
            )
        return existed

    def get_all_config(self, tenant_id: str) -> Dict[str, Any]:
        """Get all configuration overrides for a tenant."""
        tenant = self._get_tenant(tenant_id)
        return dict(tenant.config_overrides)

    def reset_all_config(self, tenant_id: str, actor_id: str = "system") -> None:
        """Reset all configuration overrides for a tenant."""
        tenant = self._get_tenant(tenant_id)
        self._require_operational(tenant, "reset_config")
        with self._lock:
            tenant.reset_config()
        self._audit(AuditEventType.TENANT_CONFIG_RESET, tenant_id, actor_id)

    # ── Data Partitioning ─────────────────────────────────────────────────────

    def get_partition_key(self, tenant_id: str) -> str:
        """Get the data partition key for a tenant."""
        tenant = self._get_tenant(tenant_id)
        return tenant.get_partition_key()

    def create_partition(
        self,
        tenant_id: str,
        partition_name: str,
        actor_id: str = "system",
    ) -> str:
        """
        Create a named data partition for a tenant.

        Returns the full partition identifier string.
        """
        tenant = self._get_tenant(tenant_id)
        self._require_operational(tenant, "create_partition")
        with self._lock:
            tenant.add_partition(partition_name)
        full_key = f"{tenant.get_partition_key()}:{partition_name}"
        self._audit(
            AuditEventType.DATA_PARTITION_CREATED,
            tenant_id,
            actor_id,
            {"partition_name": partition_name, "full_key": full_key},
        )
        return full_key

    def delete_partition(
        self,
        tenant_id: str,
        partition_name: str,
        actor_id: str = "system",
    ) -> bool:
        """Remove a named data partition. Returns True if it existed."""
        tenant = self._get_tenant(tenant_id)
        self._require_operational(tenant, "delete_partition")
        with self._lock:
            existed = tenant.remove_partition(partition_name)
        if existed:
            self._audit(
                AuditEventType.DATA_PARTITION_DELETED,
                tenant_id,
                actor_id,
                {"partition_name": partition_name},
            )
        return existed

    def get_partitions(self, tenant_id: str) -> List[str]:
        """Get all data partition names for a tenant."""
        tenant = self._get_tenant(tenant_id)
        return list(tenant.data_partitions)

    # ── Metadata ──────────────────────────────────────────────────────────────

    def update_metadata(
        self,
        tenant_id: str,
        metadata: Dict[str, str],
        actor_id: str = "system",
        merge: bool = True,
    ) -> None:
        """Update tenant metadata, merging or replacing."""
        tenant = self._get_tenant(tenant_id)
        with self._lock:
            if merge:
                tenant.metadata.update(metadata)
            else:
                tenant.metadata = dict(metadata)
            tenant.updated_at = datetime.now(timezone.utc)
        self._audit(
            AuditEventType.TENANT_UPDATED,
            tenant_id,
            actor_id,
            {"metadata": metadata, "merge": merge},
        )

    # ── Tier management ───────────────────────────────────────────────────────

    def change_tier(
        self,
        tenant_id: str,
        new_tier: Union[SubscriptionTier, str],
        actor_id: str = "system",
        reset_quotas: bool = True,
    ) -> Tenant:
        """
        Change a tenant's subscription tier, optionally resetting quotas.
        """
        if isinstance(new_tier, str):
            new_tier = SubscriptionTier(new_tier.lower())

        tenant = self._get_tenant(tenant_id)
        old_tier = tenant.tier

        with self._lock:
            tenant.tier = new_tier
            if reset_quotas:
                tenant.reset_quotas_to_tier_defaults()
            tenant.updated_at = datetime.now(timezone.utc)

        self._audit(
            AuditEventType.TENANT_UPDATED,
            tenant_id,
            actor_id,
            {
                "old_tier": old_tier.value,
                "new_tier": new_tier.value,
                "quotas_reset": reset_quotas,
            },
        )
        logger.info(
            "Tenant '%s' tier changed: %s -> %s", tenant_id, old_tier.value, new_tier.value
        )
        return tenant

    # ── Bulk operations ───────────────────────────────────────────────────────

    def suspend_all_by_tier(
        self,
        tier: SubscriptionTier,
        actor_id: str = "system",
        reason: str = "Bulk suspension",
    ) -> List[str]:
        """Suspend all active tenants of a given tier."""
        suspended: List[str] = []
        with self._lock:
            targets = [
                t.tenant_id
                for t in self._tenants.values()
                if t.tier == tier and t.status == TenantStatus.ACTIVE
            ]
        for tid in targets:
            try:
                self.suspend_tenant(tid, actor_id, reason)
                suspended.append(tid)
            except TenantManagerError as exc:
                logger.error("Failed to suspend '%s': %s", tid, exc)
        return suspended

    # ── Health / introspection ────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Return platform-wide tenant statistics."""
        with self._lock:
            total = len(self._tenants)
            by_status: Dict[str, int] = defaultdict(int)
            by_tier: Dict[str, int] = defaultdict(int)
            for t in self._tenants.values():
                by_status[t.status.value] += 1
                by_tier[t.tier.value] += 1
        return {
            "total_tenants": total,
            "by_status": dict(by_status),
            "by_tier": dict(by_tier),
            "total_audit_entries": len(self._global_audit_log),
        }

    def health_check(self) -> Dict[str, Any]:
        """Lightweight health check for integration with Platform Kernel."""
        try:
            stats = self.get_stats()
            return {"status": "healthy", "stats": stats}
        except Exception as exc:
            return {"status": "unhealthy", "error": str(exc)}


# ═══════════════════════════════════════════════════════════════════════════════
# Module Interface — Platform Kernel Integration
# ═══════════════════════════════════════════════════════════════════════════════

# Singleton pattern for Platform Kernel integration
_tenant_manager_instance: Optional[TenantManager] = None
_instance_lock: threading.Lock = threading.Lock()


def get_tenant_manager() -> TenantManager:
    """Return the singleton TenantManager instance (creates on first call)."""
    global _tenant_manager_instance
    if _tenant_manager_instance is None:
        with _instance_lock:
            if _tenant_manager_instance is None:
                _tenant_manager_instance = TenantManager()
    return _tenant_manager_instance


def reset_tenant_manager() -> None:
    """Reset the singleton instance (primarily for testing)."""
    global _tenant_manager_instance
    with _instance_lock:
        _tenant_manager_instance = None


# Module export interface expected by Platform Kernel
__module__ = {
    "name": "tenancy",
    "version": "1.0.0",
    "manager": get_tenant_manager,
    "health_check": lambda: get_tenant_manager().health_check(),
}