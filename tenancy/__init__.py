"""
ENI Enterprise — Tenant Manager OS v1.0.0
Multi-Tenant Isolation, RBAC, Quotas, Audit Logging, Data Partitioning.
"""

from .tenant_manager import (
    # Manager
    TenantManager,
    get_tenant_manager,
    reset_tenant_manager,
    # Core models
    Tenant,
    Role,
    Permission,
    Quota,
    AuditEntry,
    # Enums
    TenantStatus,
    IsolationMode,
    SubscriptionTier,
    AuditEventType,
    # Exceptions
    TenantManagerError,
    TenantNotFoundError,
    TenantStatusError,
    QuotaExceededError,
    PermissionDeniedError,
    RoleConflictError,
)

__version__ = "1.0.0"

__all__ = [
    "TenantManager",
    "get_tenant_manager",
    "reset_tenant_manager",
    "Tenant",
    "Role",
    "Permission",
    "Quota",
    "AuditEntry",
    "TenantStatus",
    "IsolationMode",
    "SubscriptionTier",
    "AuditEventType",
    "TenantManagerError",
    "TenantNotFoundError",
    "TenantStatusError",
    "QuotaExceededError",
    "PermissionDeniedError",
    "RoleConflictError",
]