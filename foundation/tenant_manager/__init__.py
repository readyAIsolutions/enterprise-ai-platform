"""
Tenant Manager - Enterprise Multi-Tenancy Foundation.

Provides comprehensive multi-tenant management including tenant lifecycle,
data isolation, workspace management, RBAC, and billing tracking.

Modules:
    manager: Tenant CRUD, status tracking, configuration, rate limiting
    isolation: Data isolation enforcement, resource quotas, encryption
    workspace: Per-tenant workspace management with lifecycle
    rbac: Role-based access control with permission sets
    billing: Usage tracking, metering, reports, and alerts
"""

from .manager import TenantManager, Tenant, TenantStatus, TenantConfig, RateLimitConfig
from .isolation import TenantIsolation, ResourceQuota, IsolationPolicy
from .workspace import WorkspaceManager, Workspace, WorkspaceTemplate, WorkspaceStatus
from .rbac import RBACManager, Role, Permission, RoleAssignment, AccessResult
from .billing import BillingTracker, UsageRecord, BillingReport, UsageAlert, MeteringEngine

__all__ = [
    # manager
    "TenantManager",
    "Tenant",
    "TenantStatus",
    "TenantConfig",
    "RateLimitConfig",
    # isolation
    "TenantIsolation",
    "ResourceQuota",
    "IsolationPolicy",
    # workspace
    "WorkspaceManager",
    "Workspace",
    "WorkspaceTemplate",
    "WorkspaceStatus",
    # rbac
    "RBACManager",
    "Role",
    "Permission",
    "RoleAssignment",
    "AccessResult",
    # billing
    "BillingTracker",
    "UsageRecord",
    "BillingReport",
    "UsageAlert",
    "MeteringEngine",
]