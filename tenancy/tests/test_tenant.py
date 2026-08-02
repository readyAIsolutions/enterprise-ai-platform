"""
Comprehensive tests for the Tenant Manager — multi-tenant isolation system.

Covers:
  - Tenant lifecycle (provision, suspend, reactivate, delete)
  - RBAC (role CRUD, assignments, permission checks)
  - Resource quotas (enforcement, updates, resets)
  - Configuration overrides
  - Audit logging
  - Data partitioning
  - Exception handling and edge cases
  - Concurrency safety
"""

import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Set

import pytest

from enterprise.tenancy import (
    AuditEntry,
    AuditEventType,
    IsolationMode,
    Permission,
    PermissionDeniedError,
    Quota,
    QuotaExceededError,
    Role,
    RoleConflictError,
    SubscriptionTier,
    Tenant,
    TenantManager,
    TenantManagerError,
    TenantNotFoundError,
    TenantStatus,
    TenantStatusError,
    get_tenant_manager,
    reset_tenant_manager,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    """Ensure each test starts with a clean TenantManager singleton."""
    reset_tenant_manager()
    yield
    reset_tenant_manager()


@pytest.fixture
def manager() -> TenantManager:
    """Provide a fresh TenantManager instance."""
    return TenantManager()


@pytest.fixture
def tenant(manager: TenantManager) -> Tenant:
    """Provision a default tenant for tests."""
    return manager.provision_tenant(
        "test-corp", "Test Corporation",
        tier=SubscriptionTier.PROFESSIONAL,
        isolation_mode=IsolationMode.SHARED,
    )


@pytest.fixture
def tenant_free(manager: TenantManager) -> Tenant:
    """Provision a free-tier tenant."""
    return manager.provision_tenant(
        "free-corp", "Free Corp", tier=SubscriptionTier.FREE,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Tenant Model Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestTenantModel:
    """Tests for the Tenant dataclass itself."""

    def test_tenant_creation_valid(self) -> None:
        """Tenant should be creatable with valid parameters."""
        t = Tenant(
            tenant_id="acme-corp",
            name="Acme Corp",
            tier=SubscriptionTier.ENTERPRISE,
            isolation_mode=IsolationMode.DEDICATED,
        )
        assert t.tenant_id == "acme-corp"
        assert t.name == "Acme Corp"
        assert t.tier == SubscriptionTier.ENTERPRISE
        assert t.isolation_mode == IsolationMode.DEDICATED
        assert t.status == TenantStatus.PROVISIONING
        assert t.quotas.max_agents == 100  # Enterprise tier default

    def test_tenant_id_validation(self) -> None:
        """Invalid tenant IDs should be rejected."""
        with pytest.raises(ValueError):
            Tenant(tenant_id="INVALID", name="Bad")
        with pytest.raises(ValueError):
            Tenant(tenant_id="-starts-with-hyphen", name="Bad")
        with pytest.raises(ValueError):
            Tenant(tenant_id="ends-with-hyphen-", name="Bad")
        with pytest.raises(ValueError):
            Tenant(tenant_id="a" * 65, name="Too long ID")

    def test_tenant_name_validation(self) -> None:
        """Invalid names should be rejected."""
        with pytest.raises(ValueError):
            Tenant(tenant_id="test-1", name="")
        with pytest.raises(ValueError):
            Tenant(tenant_id="test-1", name="X" * 129)

    def test_system_roles_initialized(self) -> None:
        """System roles should be automatically initialized."""
        t = Tenant(tenant_id="test-1", name="Test")
        assert "admin" in t.roles
        assert "developer" in t.roles
        assert "viewer" in t.roles
        assert "auditor" in t.roles
        assert t.roles["admin"].is_system
        assert Permission.TENANT_DELETE in t.roles["admin"].permissions
        assert Permission.TENANT_DELETE not in t.roles["viewer"].permissions

    def test_get_user_permissions(self) -> None:
        """User permissions should be the union of all assigned roles."""
        t = Tenant(tenant_id="test-1", name="Test")
        t.user_role_assignments["user-1"] = {"admin"}
        perms = t.get_user_permissions("user-1")
        assert Permission.TENANT_DELETE in perms
        assert Permission.AGENT_CREATE in perms

    def test_get_user_permissions_empty(self) -> None:
        """Users with no roles should have no permissions."""
        t = Tenant(tenant_id="test-1", name="Test")
        perms = t.get_user_permissions("unknown-user")
        assert perms == set()

    def test_user_has_permission(self) -> None:
        """Direct permission check should work."""
        t = Tenant(tenant_id="test-1", name="Test")
        t.user_role_assignments["user-1"] = {"auditor"}
        assert t.user_has_permission("user-1", Permission.MONITORING_READ)
        assert not t.user_has_permission("user-1", Permission.AGENT_DELETE)

    def test_tenant_hash_stability(self) -> None:
        """Tenant hash should be stable across calls."""
        t = Tenant(tenant_id="test-1", name="Test")
        h1 = t.tenant_hash
        h2 = t.tenant_hash
        assert h1 == h2
        assert len(h1) == 16

    def test_custom_roles_property(self) -> None:
        """custom_roles should exclude system roles."""
        t = Tenant(tenant_id="test-1", name="Test")
        assert len(t.custom_roles) == 0
        t.roles["engineer"] = Role(name="engineer", permissions={Permission.AGENT_CREATE})
        assert len(t.custom_roles) == 1

    def test_config_overrides(self) -> None:
        """Config get/set/delete should work correctly."""
        t = Tenant(tenant_id="test-1", name="Test")
        assert t.get_config("theme", "light") == "light"
        t.set_config("theme", "dark")
        assert t.get_config("theme") == "dark"
        assert t.delete_config("theme")
        assert not t.delete_config("theme")
        assert t.get_config("theme", "light") == "light"

    def test_reset_config(self) -> None:
        """reset_config should clear all overrides."""
        t = Tenant(tenant_id="test-1", name="Test")
        t.set_config("a", 1)
        t.set_config("b", 2)
        t.reset_config()
        assert t.config_overrides == {}

    def test_config_key_length_limit(self) -> None:
        """Config keys over 256 chars should be rejected."""
        t = Tenant(tenant_id="test-1", name="Test")
        with pytest.raises(ValueError):
            t.set_config("k" * 257, "value")

    def test_serialization_roundtrip(self) -> None:
        """Tenant should survive to_dict -> from_dict roundtrip."""
        t = Tenant(
            tenant_id="acme-corp", name="Acme Corp",
            tier=SubscriptionTier.ENTERPRISE,
            isolation_mode=IsolationMode.HYBRID,
        )
        t.set_config("theme", "dark")
        t.user_role_assignments["u1"] = {"admin"}
        d = t.to_dict()
        t2 = Tenant.from_dict(d)
        assert t2.tenant_id == "acme-corp"
        assert t2.name == "Acme Corp"
        assert t2.tier == SubscriptionTier.ENTERPRISE
        assert t2.isolation_mode == IsolationMode.HYBRID
        assert t2.get_config("theme") == "dark"
        assert t2.user_role_assignments["u1"] == {"admin"}

    def test_serialization_include_audit(self) -> None:
        """to_dict should include audit log when requested."""
        t = Tenant(tenant_id="test-1", name="Test")
        d = t.to_dict(include_audit=True)
        assert "audit_log" in d


class TestQuota:
    """Tests for the Quota dataclass."""

    def test_quota_defaults(self) -> None:
        q = Quota()
        assert q.max_agents == 5
        assert q.max_storage_bytes == 10 * 1024 ** 3

    def test_quota_as_dict(self) -> None:
        q = Quota(max_agents=42)
        d = q.as_dict()
        assert d["max_agents"] == 42
        assert "max_models" in d

    def test_quota_from_dict(self) -> None:
        q = Quota.from_dict({"max_agents": 10, "max_models": 20})
        assert q.max_agents == 10
        assert q.max_models == 20

    def test_quota_merge(self) -> None:
        base = Quota(max_agents=5, max_models=3)
        overrides = Quota(max_agents=50, max_models=Quota.__dataclass_fields__["max_models"].default)
        merged = base.merge(overrides)
        assert merged.max_agents == 50  # Overridden
        assert merged.max_models == 3  # Not overridden (falls back to base)

    def test_tier_default_quotas(self) -> None:
        """Each tier should have appropriate defaults."""
        from enterprise.tenancy.tenant_manager import _TIER_DEFAULT_QUOTAS

        free_q = _TIER_DEFAULT_QUOTAS[SubscriptionTier.FREE]
        ent_q = _TIER_DEFAULT_QUOTAS[SubscriptionTier.ENTERPRISE]
        assert free_q.max_agents == 1
        assert ent_q.max_agents == 100
        assert free_q.max_api_calls_per_day < ent_q.max_api_calls_per_day


# ═══════════════════════════════════════════════════════════════════════════════
# Provisioning Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestProvisioning:
    """Tests for the tenant provisioning flow."""

    def test_provision_basic(self, manager: TenantManager) -> None:
        """Basic tenant provisioning should succeed with ACTIVE status."""
        t = manager.provision_tenant("acme-corp", "Acme Corp")
        assert t.tenant_id == "acme-corp"
        assert t.status == TenantStatus.ACTIVE
        assert t.tier == SubscriptionTier.FREE
        assert t.isolation_mode == IsolationMode.SHARED

    def test_provision_with_tier(self, manager: TenantManager) -> None:
        """Provisioning with a tier should set appropriate quotas."""
        t = manager.provision_tenant("big-corp", "Big Corp",
                                     tier=SubscriptionTier.ENTERPRISE)
        assert t.tier == SubscriptionTier.ENTERPRISE
        assert t.quotas.max_agents == 100
        assert t.quotas.max_users == 500

    def test_provision_with_isolation(self, manager: TenantManager) -> None:
        """Isolation mode should be respected."""
        t = manager.provision_tenant("iso-corp", "ISO Corp",
                                     isolation_mode=IsolationMode.DEDICATED)
        assert t.isolation_mode == IsolationMode.DEDICATED

    def test_provision_duplicate_active(self, manager: TenantManager) -> None:
        """Provisioning an existing active tenant should fail."""
        manager.provision_tenant("dup-corp", "Dup Corp")
        with pytest.raises(TenantManagerError, match="already exists"):
            manager.provision_tenant("dup-corp", "Dup Corp")

    def test_provision_with_custom_quotas(self, manager: TenantManager) -> None:
        """Custom quotas should override tier defaults."""
        custom = Quota(max_agents=99, max_models=88)
        t = manager.provision_tenant("custom-corp", "Custom Corp",
                                     tier=SubscriptionTier.ENTERPRISE,
                                     quotas=custom)
        assert t.quotas.max_agents == 99
        assert t.quotas.max_models == 88

    def test_provision_sets_audit_entries(self, manager: TenantManager) -> None:
        """Provisioning should create audit entries."""
        manager.provision_tenant("audit-corp", "Audit Corp")
        log = manager.get_audit_log("audit-corp")
        events = [e.event_type for e in log]
        assert AuditEventType.TENANT_CREATED in events
        assert AuditEventType.TENANT_PROVISIONED in events

    def test_provision_string_tier(self, manager: TenantManager) -> None:
        """String tier should be accepted."""
        t = manager.provision_tenant("str-corp", "String Corp", tier="professional")
        assert t.tier == SubscriptionTier.PROFESSIONAL

    def test_provision_string_isolation(self, manager: TenantManager) -> None:
        """String isolation mode should be accepted."""
        t = manager.provision_tenant("str2-corp", "String Corp",
                                     isolation_mode="hybrid")
        assert t.isolation_mode == IsolationMode.HYBRID

    def test_provision_with_metadata(self, manager: TenantManager) -> None:
        """Metadata should be stored."""
        t = manager.provision_tenant("meta-corp", "Meta Corp",
                                     metadata={"dept": "engineering"})
        assert t.metadata["dept"] == "engineering"

    def test_provision_hooks_fire(self, manager: TenantManager) -> None:
        """Registered provisioning hooks should fire."""
        calls = []

        def hook(t: Tenant) -> None:
            calls.append(t.tenant_id)

        manager.register_provisioning_hook("test-hook", hook)
        manager.provision_tenant("hook-corp", "Hook Corp")
        assert "hook-corp" in calls

        manager.unregister_provisioning_hook("test-hook")
        calls.clear()
        manager.provision_tenant("hook2-corp", "Hook2 Corp")
        assert calls == []


# ═══════════════════════════════════════════════════════════════════════════════
# Lifecycle Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestLifecycle:
    """Tests for suspend, reactivate, and delete flows."""

    def test_suspend_active_tenant(self, manager: TenantManager, tenant: Tenant) -> None:
        """Suspending an active tenant should transition to SUSPENDED."""
        t = manager.suspend_tenant(tenant.tenant_id, reason="maintenance")
        assert t.status == TenantStatus.SUSPENDED
        assert t.suspended_at is not None

    def test_suspend_idempotent(self, manager: TenantManager, tenant: Tenant) -> None:
        """Suspending an already suspended tenant should be a no-op."""
        manager.suspend_tenant(tenant.tenant_id)
        t = manager.suspend_tenant(tenant.tenant_id)
        assert t.status == TenantStatus.SUSPENDED

    def test_suspend_deleted_tenant_fails(self, manager: TenantManager) -> None:
        """Suspending a deleted tenant should raise."""
        t = manager.provision_tenant("del-me", "Delete Me")
        manager.delete_tenant(t.tenant_id)
        with pytest.raises(TenantStatusError):
            manager.suspend_tenant(t.tenant_id)

    def test_reactivate_suspended_tenant(self, manager: TenantManager, tenant: Tenant) -> None:
        """Reactivating should restore ACTIVE status."""
        manager.suspend_tenant(tenant.tenant_id)
        t = manager.reactivate_tenant(tenant.tenant_id)
        assert t.status == TenantStatus.ACTIVE
        assert t.suspended_at is None

    def test_reactivate_active_tenant_fails(self, manager: TenantManager, tenant: Tenant) -> None:
        """Reactivating an active tenant should raise."""
        with pytest.raises(TenantStatusError):
            manager.reactivate_tenant(tenant.tenant_id)

    def test_delete_basic(self, manager: TenantManager) -> None:
        """Deleting a tenant should transition to DELETED."""
        t = manager.provision_tenant("delete-me", "Delete Me")
        t = manager.delete_tenant(t.tenant_id)
        assert t.status == TenantStatus.DELETED
        assert t.deleted_at is not None
        assert t.data_partitions == []
        assert t.user_role_assignments == {}

    def test_delete_force_removes_from_registry(self, manager: TenantManager) -> None:
        """Force delete should remove tenant from the registry."""
        t = manager.provision_tenant("force-delete-me", "Force Delete")
        manager.delete_tenant(t.tenant_id, force=True)
        with pytest.raises(TenantNotFoundError):
            manager.get_tenant(t.tenant_id)

    def test_delete_already_deleted(self, manager: TenantManager) -> None:
        """Deleting an already deleted tenant should raise."""
        t = manager.provision_tenant("del-twice", "Delete Twice")
        manager.delete_tenant(t.tenant_id)
        with pytest.raises(TenantStatusError):
            manager.delete_tenant(t.tenant_id)

    def test_cleanup_hooks_fire_on_delete(self, manager: TenantManager) -> None:
        """Registered cleanup hooks should execute on delete."""
        cleanup_calls = []

        def cleanup(t: Tenant) -> None:
            cleanup_calls.append(t.tenant_id)

        manager.register_cleanup_hook("clean-1", cleanup)
        t = manager.provision_tenant("clean-me", "Clean Me")
        manager.delete_tenant(t.tenant_id)
        assert "clean-me" in cleanup_calls

    def test_cleanup_hook_errors_handled(self, manager: TenantManager) -> None:
        """Cleanup hook errors should not prevent deletion."""
        def bad_hook(t: Tenant) -> None:
            raise RuntimeError("Simulated cleanup failure")

        manager.register_cleanup_hook("bad", bad_hook)
        t = manager.provision_tenant("bad-clean", "Bad Clean")
        manager.delete_tenant(t.tenant_id)  # Should not raise
        assert t.status == TenantStatus.DELETED

    def test_suspend_with_permission_check(self, manager: TenantManager, tenant: Tenant) -> None:
        """Suspend with require_permission=True should check permissions."""
        # Assign admin role to actor
        manager.assign_role(tenant.tenant_id, "actor-1", "admin")
        t = manager.suspend_tenant(tenant.tenant_id, actor_id="actor-1",
                                   require_permission=True)
        assert t.status == TenantStatus.SUSPENDED

    def test_suspend_without_permission_fails(self, manager: TenantManager, tenant: Tenant) -> None:
        """Suspend should fail if actor lacks permission."""
        with pytest.raises(PermissionDeniedError):
            manager.suspend_tenant(tenant.tenant_id, actor_id="no-perms",
                                   require_permission=True)

    def test_delete_with_permission_check(self, manager: TenantManager) -> None:
        """Delete with require_permission=True should check."""
        t = manager.provision_tenant("perm-del", "Perm Delete")
        manager.assign_role(t.tenant_id, "admin-user", "admin")
        manager.delete_tenant(t.tenant_id, actor_id="admin-user",
                              require_permission=True)
        assert t.status == TenantStatus.DELETED


# ═══════════════════════════════════════════════════════════════════════════════
# Query Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestQueries:
    """Tests for tenant listing and retrieval."""

    def test_get_tenant_found(self, manager: TenantManager, tenant: Tenant) -> None:
        """get_tenant should return the correct tenant."""
        t = manager.get_tenant(tenant.tenant_id)
        assert t.tenant_id == tenant.tenant_id

    def test_get_tenant_not_found(self, manager: TenantManager) -> None:
        """get_tenant should raise for unknown tenant."""
        with pytest.raises(TenantNotFoundError):
            manager.get_tenant("nonexistent")

    def test_list_tenants_all(self, manager: TenantManager) -> None:
        """list_tenants should return all tenants."""
        manager.provision_tenant("a-corp", "A Corp")
        manager.provision_tenant("b-corp", "B Corp")
        tenants = manager.list_tenants()
        assert len(tenants) == 2

    def test_list_tenants_by_status(self, manager: TenantManager) -> None:
        """List should filter by status."""
        manager.provision_tenant("active-1", "Active 1")
        t2 = manager.provision_tenant("susp-1", "Susp 1")
        manager.suspend_tenant(t2.tenant_id)

        active = manager.list_tenants(status=TenantStatus.ACTIVE)
        suspended = manager.list_tenants(status=TenantStatus.SUSPENDED)
        assert len(active) == 1
        assert len(suspended) == 1

    def test_list_tenants_by_tier(self, manager: TenantManager) -> None:
        """List should filter by tier."""
        manager.provision_tenant("free-1", "Free 1", tier=SubscriptionTier.FREE)
        manager.provision_tenant("ent-1", "Ent 1", tier=SubscriptionTier.ENTERPRISE)
        frees = manager.list_tenants(tier=SubscriptionTier.FREE)
        ents = manager.list_tenants(tier=SubscriptionTier.ENTERPRISE)
        assert len(frees) == 1
        assert len(ents) == 1

    def test_tenant_exists(self, manager: TenantManager, tenant: Tenant) -> None:
        """tenant_exists should be accurate."""
        assert manager.tenant_exists(tenant.tenant_id)
        assert not manager.tenant_exists("nonexistent")

    def test_tenant_exists_deleted(self, manager: TenantManager) -> None:
        """Deleted tenants should return False for exists."""
        t = manager.provision_tenant("exists-del", "Exists Delete")
        manager.delete_tenant(t.tenant_id)
        assert not manager.tenant_exists(t.tenant_id)

    def test_get_stats(self, manager: TenantManager) -> None:
        """get_stats should return correct counts."""
        manager.provision_tenant("s1", "S1", tier=SubscriptionTier.FREE)
        manager.provision_tenant("s2", "S2", tier=SubscriptionTier.ENTERPRISE)
        stats = manager.get_stats()
        assert stats["total_tenants"] == 2
        assert "active" in stats["by_status"]
        assert "free" in stats["by_tier"]
        assert "enterprise" in stats["by_tier"]


# ═══════════════════════════════════════════════════════════════════════════════
# RBAC Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestRBAC:
    """Tests for role-based access control."""

    # ── Role CRUD ─────────────────────────────────────────────────────────────

    def test_create_custom_role(self, manager: TenantManager, tenant: Tenant) -> None:
        """Custom role should be created successfully."""
        role = manager.create_role(
            tenant.tenant_id, "engineer",
            permissions={Permission.AGENT_CREATE, Permission.DATA_READ},
            description="Engineering role",
        )
        assert role.name == "engineer"
        assert Permission.AGENT_CREATE in role.permissions
        assert role.role_id.startswith("role_")

    def test_create_role_system_conflict(self, manager: TenantManager, tenant: Tenant) -> None:
        """Creating a role with a system role name should fail."""
        with pytest.raises(RoleConflictError):
            manager.create_role(tenant.tenant_id, "admin", set())

    def test_create_duplicate_role(self, manager: TenantManager, tenant: Tenant) -> None:
        """Creating a duplicate role name should fail."""
        manager.create_role(tenant.tenant_id, "engineer", set())
        with pytest.raises(TenantManagerError, match="already exists"):
            manager.create_role(tenant.tenant_id, "engineer", set())

    def test_create_role_exceeds_quota(self, manager: TenantManager, tenant_free: Tenant) -> None:
        """Free tier should not allow custom roles."""
        with pytest.raises(QuotaExceededError):
            manager.create_role(tenant_free.tenant_id, "custom-role", set())

    def test_update_role(self, manager: TenantManager, tenant: Tenant) -> None:
        """Updating a role should change permissions."""
        manager.create_role(tenant.tenant_id, "ops", {Permission.AGENT_READ})
        updated = manager.update_role(
            tenant.tenant_id, "ops",
            permissions={Permission.AGENT_CREATE, Permission.AGENT_DELETE},
            description="Ops team",
        )
        assert Permission.AGENT_CREATE in updated.permissions
        assert Permission.AGENT_DELETE in updated.permissions
        assert Permission.AGENT_READ not in updated.permissions
        assert updated.description == "Ops team"

    def test_update_system_role_fails(self, manager: TenantManager, tenant: Tenant) -> None:
        """Updating system roles should be rejected."""
        with pytest.raises(RoleConflictError):
            manager.update_role(tenant.tenant_id, "admin", permissions=set())

    def test_update_nonexistent_role(self, manager: TenantManager, tenant: Tenant) -> None:
        """Updating a nonexistent role should raise."""
        with pytest.raises(TenantManagerError):
            manager.update_role(tenant.tenant_id, "no-such-role", permissions=set())

    def test_delete_role(self, manager: TenantManager, tenant: Tenant) -> None:
        """Deleting a custom role should succeed."""
        manager.create_role(tenant.tenant_id, "temp-role", {Permission.DATA_READ})
        assert manager.delete_role(tenant.tenant_id, "temp-role")
        assert "temp-role" not in manager.get_roles(tenant.tenant_id)

    def test_delete_role_revokes_from_users(self, manager: TenantManager, tenant: Tenant) -> None:
        """Deleting a role should revoke it from all users."""
        manager.create_role(tenant.tenant_id, "temp", {Permission.DATA_READ})
        manager.assign_role(tenant.tenant_id, "user-a", "temp")
        manager.assign_role(tenant.tenant_id, "user-b", "temp")
        manager.delete_role(tenant.tenant_id, "temp")
        assert "temp" not in manager.get_user_roles(tenant.tenant_id, "user-a")
        assert "temp" not in manager.get_user_roles(tenant.tenant_id, "user-b")

    def test_delete_system_role_fails(self, manager: TenantManager, tenant: Tenant) -> None:
        """Deleting a system role should fail."""
        with pytest.raises(RoleConflictError):
            manager.delete_role(tenant.tenant_id, "viewer")

    def test_get_roles(self, manager: TenantManager, tenant: Tenant) -> None:
        """get_roles should return system + custom roles."""
        manager.create_role(tenant.tenant_id, "custom", {Permission.DATA_READ})
        roles = manager.get_roles(tenant.tenant_id)
        assert "admin" in roles
        assert "developer" in roles
        assert "viewer" in roles
        assert "auditor" in roles
        assert "custom" in roles

    # ── Role assignments ──────────────────────────────────────────────────────

    def test_assign_role(self, manager: TenantManager, tenant: Tenant) -> None:
        """Assigning a role should work."""
        manager.assign_role(tenant.tenant_id, "user-1", "developer")
        roles = manager.get_user_roles(tenant.tenant_id, "user-1")
        assert "developer" in roles

    def test_assign_multiple_roles(self, manager: TenantManager, tenant: Tenant) -> None:
        """Multiple roles should be assignable."""
        manager.assign_role(tenant.tenant_id, "user-1", "viewer")
        manager.assign_role(tenant.tenant_id, "user-1", "auditor")
        roles = manager.get_user_roles(tenant.tenant_id, "user-1")
        assert roles == {"viewer", "auditor"}

    def test_assign_nonexistent_role(self, manager: TenantManager, tenant: Tenant) -> None:
        """Assigning a nonexistent role should fail."""
        with pytest.raises(TenantManagerError):
            manager.assign_role(tenant.tenant_id, "user-1", "no-such-role")

    def test_assign_to_suspended_tenant_fails(self, manager: TenantManager, tenant: Tenant) -> None:
        """Cannot assign roles while tenant is suspended."""
        manager.suspend_tenant(tenant.tenant_id)
        with pytest.raises(TenantStatusError):
            manager.assign_role(tenant.tenant_id, "user-1", "viewer")

    def test_revoke_role(self, manager: TenantManager, tenant: Tenant) -> None:
        """Revoking a role should work."""
        manager.assign_role(tenant.tenant_id, "user-1", "viewer")
        assert manager.revoke_role(tenant.tenant_id, "user-1", "viewer")
        assert "viewer" not in manager.get_user_roles(tenant.tenant_id, "user-1")

    def test_revoke_role_not_assigned(self, manager: TenantManager, tenant: Tenant) -> None:
        """Revoking an unassigned role should return False."""
        assert not manager.revoke_role(tenant.tenant_id, "user-1", "viewer")

    def test_get_user_permissions(self, manager: TenantManager, tenant: Tenant) -> None:
        """User permissions should reflect assigned roles."""
        manager.assign_role(tenant.tenant_id, "dev-1", "developer")
        perms = manager.get_user_permissions(tenant.tenant_id, "dev-1")
        assert Permission.AGENT_CREATE in perms
        assert Permission.TENANT_DELETE not in perms

    def test_check_permission(self, manager: TenantManager, tenant: Tenant) -> None:
        """check_permission should return correct boolean."""
        manager.assign_role(tenant.tenant_id, "admin-user", "admin")
        assert manager.check_permission(tenant.tenant_id, "admin-user", Permission.TENANT_DELETE)
        assert not manager.check_permission(tenant.tenant_id, "viewer-user", Permission.TENANT_DELETE)

    def test_check_permission_suspended_tenant(self, manager: TenantManager, tenant: Tenant) -> None:
        """check_permission should return False for suspended tenants."""
        manager.assign_role(tenant.tenant_id, "user", "admin")
        manager.suspend_tenant(tenant.tenant_id)
        assert not manager.check_permission(tenant.tenant_id, "user", Permission.AGENT_CREATE)

    def test_require_permission_on_operations(self, manager: TenantManager, tenant: Tenant) -> None:
        """Operations with require_permission=True should check permissions."""
        # user without permissions
        with pytest.raises(PermissionDeniedError):
            manager.create_role(tenant.tenant_id, "r1", set(), actor_id="noob")

        # Give permission
        manager.assign_role(tenant.tenant_id, "noob", "admin")
        role = manager.create_role(tenant.tenant_id, "r1", set(), actor_id="noob")
        assert role.name == "r1"


# ═══════════════════════════════════════════════════════════════════════════════
# Quota Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestQuotaManagement:
    """Tests for resource quota enforcement and management."""

    def test_get_quotas(self, manager: TenantManager, tenant: Tenant) -> None:
        """get_quotas should return the tenant's Quota."""
        q = manager.get_quotas(tenant.tenant_id)
        assert q.max_agents == 25  # PROFESSIONAL default

    def test_update_quotas(self, manager: TenantManager, tenant: Tenant) -> None:
        """update_quotas should modify specific fields."""
        q = manager.update_quotas(tenant.tenant_id, max_agents=50, max_users=2000)
        assert q.max_agents == 50
        assert q.max_users == 2000

    def test_reset_quotas(self, manager: TenantManager, tenant: Tenant) -> None:
        """reset_quotas should restore tier defaults."""
        manager.update_quotas(tenant.tenant_id, max_agents=999)
        manager.reset_quotas(tenant.tenant_id)
        q = manager.get_quotas(tenant.tenant_id)
        assert q.max_agents == 25  # Back to PROFESSIONAL default

    def test_check_quota_within_limit(self, manager: TenantManager, tenant: Tenant) -> None:
        """check_quota should return True when within limits."""
        assert manager.check_quota(tenant.tenant_id, "api_calls", 10)

    def test_check_quota_exceeded(self, manager: TenantManager, tenant_free: Tenant) -> None:
        """check_quota should raise when exceeding limits."""
        tenant_free.quotas.max_api_calls_per_day = 5
        manager.record_usage(tenant_free.tenant_id, "api_calls", 5, check_quota=False)
        with pytest.raises(QuotaExceededError):
            manager.check_quota(tenant_free.tenant_id, "api_calls", 1)

    def test_record_usage(self, manager: TenantManager, tenant: Tenant) -> None:
        """record_usage should increment counters."""
        new_total = manager.record_usage(tenant.tenant_id, "api_calls", 5)
        assert new_total == 5
        assert manager.get_usage(tenant.tenant_id)["api_calls"] == 5

    def test_record_usage_cumulative(self, manager: TenantManager, tenant: Tenant) -> None:
        """record_usage should be cumulative."""
        manager.record_usage(tenant.tenant_id, "tokens", 100)
        manager.record_usage(tenant.tenant_id, "tokens", 200)
        assert manager.get_usage(tenant.tenant_id)["tokens"] == 300

    def test_record_usage_fails_on_quota(self, manager: TenantManager, tenant_free: Tenant) -> None:
        """record_usage should raise on quota exceeded."""
        tenant_free.quotas.max_api_calls_per_day = 1
        manager.record_usage(tenant_free.tenant_id, "api_calls", 1, check_quota=False)
        with pytest.raises(QuotaExceededError):
            manager.record_usage(tenant_free.tenant_id, "api_calls", 1)

    def test_record_usage_skip_quota_check(self, manager: TenantManager, tenant_free: Tenant) -> None:
        """record_usage with check_quota=False should bypass limits."""
        tenant_free.quotas.max_api_calls_per_day = 1
        # Should not raise
        manager.record_usage(tenant_free.tenant_id, "api_calls", 10, check_quota=False)
        assert manager.get_usage(tenant_free.tenant_id)["api_calls"] == 10

    def test_reset_usage(self, manager: TenantManager, tenant: Tenant) -> None:
        """reset_usage should zero out counters."""
        manager.record_usage(tenant.tenant_id, "api_calls", 50)
        manager.reset_usage(tenant.tenant_id)
        usage = manager.get_usage(tenant.tenant_id)
        assert usage == {}

    def test_quota_audit_on_exceeded(self, manager: TenantManager, tenant_free: Tenant) -> None:
        """Quota exceeded should generate an audit entry."""
        tenant_free.quotas.max_agents = 0
        with pytest.raises(QuotaExceededError):
            manager.check_quota(tenant_free.tenant_id, "agents", 1)
        log = manager.get_audit_log(tenant_free.tenant_id,
                                     event_type=AuditEventType.QUOTA_EXCEEDED)
        assert len(log) >= 1

    def test_unknown_resource_passes(self, manager: TenantManager, tenant: Tenant) -> None:
        """Unknown resource types should pass through."""
        assert manager.check_quota(tenant.tenant_id, "unknown_thing", 9999)


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfiguration:
    """Tests for tenant configuration overrides."""

    def test_set_and_get_config(self, manager: TenantManager, tenant: Tenant) -> None:
        """Config override should be storable and retrievable."""
        manager.set_config(tenant.tenant_id, "max_retries", "5")
        assert manager.get_config(tenant.tenant_id, "max_retries") == "5"

    def test_config_default(self, manager: TenantManager, tenant: Tenant) -> None:
        """Missing config should return default."""
        assert manager.get_config(tenant.tenant_id, "theme", "light") == "light"

    def test_delete_config(self, manager: TenantManager, tenant: Tenant) -> None:
        """delete_config should remove an override."""
        manager.set_config(tenant.tenant_id, "key", "val")
        assert manager.delete_config(tenant.tenant_id, "key")
        assert manager.get_config(tenant.tenant_id, "key", "default") == "default"

    def test_delete_missing_config(self, manager: TenantManager, tenant: Tenant) -> None:
        """delete_config on missing key should return False."""
        assert not manager.delete_config(tenant.tenant_id, "nonexistent")

    def test_get_all_config(self, manager: TenantManager, tenant: Tenant) -> None:
        """get_all_config should return all overrides."""
        manager.set_config(tenant.tenant_id, "a", 1)
        manager.set_config(tenant.tenant_id, "b", 2)
        config = manager.get_all_config(tenant.tenant_id)
        assert config == {"a": 1, "b": 2}

    def test_reset_all_config(self, manager: TenantManager, tenant: Tenant) -> None:
        """reset_all_config should clear all overrides."""
        manager.set_config(tenant.tenant_id, "a", 1)
        manager.reset_all_config(tenant.tenant_id)
        assert manager.get_all_config(tenant.tenant_id) == {}

    def test_config_audit_entry(self, manager: TenantManager, tenant: Tenant) -> None:
        """Setting config should generate audit entry."""
        manager.set_config(tenant.tenant_id, "audit-test", "value", actor_id="admin")
        log = [e for e in manager.get_audit_log(tenant.tenant_id)
               if e.event_type == AuditEventType.TENANT_CONFIG_CHANGED]
        assert len(log) >= 1
        assert log[-1].details["key"] == "audit-test"


# ═══════════════════════════════════════════════════════════════════════════════
# Data Partitioning Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestDataPartitioning:
    """Tests for tenant-aware data partitioning."""

    def test_get_partition_key(self, manager: TenantManager, tenant: Tenant) -> None:
        """Partition key should be derived from tenant ID."""
        key = manager.get_partition_key(tenant.tenant_id)
        assert key.startswith("tn_")
        assert len(key) == 19  # "tn_" + 16 hex chars

    def test_create_partition(self, manager: TenantManager, tenant: Tenant) -> None:
        """Creating a partition should return a full key."""
        full_key = manager.create_partition(tenant.tenant_id, "vectors")
        assert ":" in full_key
        assert "vectors" in full_key
        assert full_key.startswith("tn_")

    def test_get_partitions(self, manager: TenantManager, tenant: Tenant) -> None:
        """get_partitions should list all partitions."""
        manager.create_partition(tenant.tenant_id, "p1")
        manager.create_partition(tenant.tenant_id, "p2")
        partitions = manager.get_partitions(tenant.tenant_id)
        assert "p1" in partitions
        assert "p2" in partitions
        assert len(partitions) == 2

    def test_delete_partition(self, manager: TenantManager, tenant: Tenant) -> None:
        """delete_partition should remove a partition."""
        manager.create_partition(tenant.tenant_id, "temp")
        assert manager.delete_partition(tenant.tenant_id, "temp")
        assert "temp" not in manager.get_partitions(tenant.tenant_id)

    def test_delete_partition_missing(self, manager: TenantManager, tenant: Tenant) -> None:
        """delete_partition on nonexistent should return False."""
        assert not manager.delete_partition(tenant.tenant_id, "nonexistent")

    def test_create_partition_duplicate(self, manager: TenantManager, tenant: Tenant) -> None:
        """Creating a duplicate partition should be a no-op."""
        k1 = manager.create_partition(tenant.tenant_id, "dup")
        k2 = manager.create_partition(tenant.tenant_id, "dup")
        assert k1 == k2
        assert len(manager.get_partitions(tenant.tenant_id)) == 1

    def test_partition_key_different_per_tenant(self, manager: TenantManager) -> None:
        """Different tenants should have different partition keys."""
        t1 = manager.provision_tenant("corp-a", "Corp A")
        t2 = manager.provision_tenant("corp-b", "Corp B")
        k1 = manager.get_partition_key(t1.tenant_id)
        k2 = manager.get_partition_key(t2.tenant_id)
        assert k1 != k2


# ═══════════════════════════════════════════════════════════════════════════════
# Audit Logging Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditLogging:
    """Tests for the audit logging subsystem."""

    def test_audit_entries_created(self, manager: TenantManager, tenant: Tenant) -> None:
        """Operations should create audit entries."""
        log = manager.get_audit_log(tenant.tenant_id)
        assert len(log) > 0
        for entry in log:
            assert isinstance(entry, AuditEntry)
            assert entry.tenant_id == tenant.tenant_id
            assert entry.entry_id.startswith("audit_")

    def test_global_audit_log(self, manager: TenantManager) -> None:
        """Global audit log should contain all entries."""
        t1 = manager.provision_tenant("log-a", "Log A")
        t2 = manager.provision_tenant("log-b", "Log B")
        log = manager.get_audit_log()
        events = [e.event_type for e in log]
        assert AuditEventType.TENANT_CREATED in events
        assert AuditEventType.TENANT_PROVISIONED in events

    def test_audit_filter_by_event_type(self, manager: TenantManager, tenant: Tenant) -> None:
        """Audit log should be filterable by event type."""
        manager.suspend_tenant(tenant.tenant_id)
        log = manager.get_audit_log(tenant.tenant_id,
                                     event_type=AuditEventType.TENANT_SUSPENDED)
        assert len(log) == 1
        assert log[0].event_type == AuditEventType.TENANT_SUSPENDED

    def test_audit_pagination(self, manager: TenantManager) -> None:
        """Audit log should support limit/offset pagination."""
        for i in range(10):
            manager.provision_tenant(f"page-{i}", f"Page {i}")
        log = manager.get_audit_log(limit=5, offset=0)
        assert len(log) <= 5

    def test_access_denied_audit(self, manager: TenantManager, tenant: Tenant) -> None:
        """Access denied should be logged as an audit entry."""
        manager.check_permission(tenant.tenant_id, "unknown", Permission.TENANT_DELETE)
        log = manager.get_audit_log(tenant.tenant_id,
                                     event_type=AuditEventType.ACCESS_DENIED)
        assert len(log) >= 1

    def test_role_assignment_audit(self, manager: TenantManager, tenant: Tenant) -> None:
        """Role assignments should be audited."""
        manager.assign_role(tenant.tenant_id, "user-x", "viewer")
        log = manager.get_audit_log(tenant.tenant_id,
                                     event_type=AuditEventType.ROLE_ASSIGNED)
        assert any(e.details.get("user_id") == "user-x" for e in log)


# ═══════════════════════════════════════════════════════════════════════════════
# Tier Management Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestTierManagement:
    """Tests for tier changes and management."""

    def test_change_tier(self, manager: TenantManager, tenant: Tenant) -> None:
        """change_tier should update tier and optionally reset quotas."""
        manager.update_quotas(tenant.tenant_id, max_agents=999)
        t = manager.change_tier(tenant.tenant_id, SubscriptionTier.ENTERPRISE)
        assert t.tier == SubscriptionTier.ENTERPRISE
        assert t.quotas.max_agents == 100  # Reset to Enterprise default

    def test_change_tier_no_reset(self, manager: TenantManager, tenant: Tenant) -> None:
        """change_tier with reset_quotas=False should preserve custom quotas."""
        manager.update_quotas(tenant.tenant_id, max_agents=777)
        t = manager.change_tier(tenant.tenant_id, SubscriptionTier.ENTERPRISE,
                                reset_quotas=False)
        assert t.tier == SubscriptionTier.ENTERPRISE
        assert t.quotas.max_agents == 777

    def test_change_tier_string(self, manager: TenantManager, tenant: Tenant) -> None:
        """String tier should be accepted."""
        t = manager.change_tier(tenant.tenant_id, "enterprise")
        assert t.tier == SubscriptionTier.ENTERPRISE

    def test_suspend_all_by_tier(self, manager: TenantManager) -> None:
        """suspend_all_by_tier should suspend all matching tenants."""
        manager.provision_tenant("f1", "Free 1", tier=SubscriptionTier.FREE)
        manager.provision_tenant("f2", "Free 2", tier=SubscriptionTier.FREE)
        manager.provision_tenant("p1", "Pro 1", tier=SubscriptionTier.PROFESSIONAL)

        suspended = manager.suspend_all_by_tier(SubscriptionTier.FREE)
        assert len(suspended) == 2
        assert manager.get_tenant("f1").status == TenantStatus.SUSPENDED
        assert manager.get_tenant("p1").status == TenantStatus.ACTIVE


# ═══════════════════════════════════════════════════════════════════════════════
# Metadata Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestMetadata:
    """Tests for tenant metadata management."""

    def test_update_metadata_merge(self, manager: TenantManager, tenant: Tenant) -> None:
        """update_metadata with merge=True should combine."""
        manager.update_metadata(tenant.tenant_id, {"a": "1"})
        manager.update_metadata(tenant.tenant_id, {"b": "2"})
        t = manager.get_tenant(tenant.tenant_id)
        assert t.metadata["a"] == "1"
        assert t.metadata["b"] == "2"

    def test_update_metadata_replace(self, manager: TenantManager, tenant: Tenant) -> None:
        """update_metadata with merge=False should replace."""
        manager.update_metadata(tenant.tenant_id, {"a": "1"})
        manager.update_metadata(tenant.tenant_id, {"b": "2"}, merge=False)
        t = manager.get_tenant(tenant.tenant_id)
        assert "a" not in t.metadata
        assert t.metadata["b"] == "2"


# ═══════════════════════════════════════════════════════════════════════════════
# Health & Singleton Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestHealthAndSingleton:
    """Tests for health check and singleton pattern."""

    def test_health_check_healthy(self, manager: TenantManager) -> None:
        """Health check should return healthy when functional."""
        result = manager.health_check()
        assert result["status"] == "healthy"
        assert "stats" in result

    def test_singleton_same_instance(self) -> None:
        """get_tenant_manager should return the same instance."""
        m1 = get_tenant_manager()
        m2 = get_tenant_manager()
        assert m1 is m2

    def test_singleton_reset(self) -> None:
        """reset_tenant_manager should create a new instance."""
        m1 = get_tenant_manager()
        reset_tenant_manager()
        m2 = get_tenant_manager()
        assert m1 is not m2


# ═══════════════════════════════════════════════════════════════════════════════
# Concurrency Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestConcurrency:
    """Tests for thread-safety of the TenantManager."""

    def test_concurrent_provisioning(self, manager: TenantManager) -> None:
        """Concurrent provisioning of different tenants should not error."""
        errors: list = []

        def provision(i: int) -> None:
            try:
                manager.provision_tenant(f"conc-{i}", f"Concurrent {i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=provision, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(manager.list_tenants()) == 20

    def test_concurrent_role_assignments(self, manager: TenantManager, tenant: Tenant) -> None:
        """Concurrent role assignments should be safe."""
        errors: list = []

        def assign(i: int) -> None:
            try:
                manager.assign_role(tenant.tenant_id, f"user-{i}", "viewer")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=assign, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        for i in range(10):
            assert "viewer" in manager.get_user_roles(tenant.tenant_id, f"user-{i}")

    def test_concurrent_usage_recording(self, manager: TenantManager, tenant: Tenant) -> None:
        """Concurrent usage recording should be safe."""
        manager.update_quotas(tenant.tenant_id, max_api_calls_per_day=100_000)

        def record() -> None:
            for _ in range(50):
                manager.record_usage(tenant.tenant_id, "api_calls", 1)

        threads = [threading.Thread(target=record) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        usage = manager.get_usage(tenant.tenant_id)
        assert usage["api_calls"] == 250


# ═══════════════════════════════════════════════════════════════════════════════
# Exceptions Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestExceptions:
    """Tests for exception hierarchy."""

    def test_exception_inheritance(self) -> None:
        """Custom exceptions should inherit from TenantManagerError."""
        assert issubclass(TenantNotFoundError, TenantManagerError)
        assert issubclass(TenantStatusError, TenantManagerError)
        assert issubclass(QuotaExceededError, TenantManagerError)
        assert issubclass(PermissionDeniedError, TenantManagerError)
        assert issubclass(RoleConflictError, TenantManagerError)

    def test_exception_messages(self) -> None:
        """Exceptions should carry the provided message."""
        err = TenantNotFoundError("tenant 'x' missing")
        assert "tenant 'x' missing" in str(err)

        err = QuotaExceededError("quota blown")
        assert "quota blown" in str(err)


# ═══════════════════════════════════════════════════════════════════════════════
# Hook Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestHooks:
    """Tests for hook registration and lifecycle."""

    def test_register_unregister_cleanup(self, manager: TenantManager) -> None:
        """Cleanup hooks should be registerable and unregisterable."""
        calls = []

        def hook(t: Tenant) -> None:
            calls.append(1)

        manager.register_cleanup_hook("h1", hook)
        assert manager.unregister_cleanup_hook("h1")
        assert not manager.unregister_cleanup_hook("h1")

    def test_register_unregister_provisioning(self, manager: TenantManager) -> None:
        """Provisioning hooks should be registerable and unregisterable."""
        hook = lambda t: None
        manager.register_provisioning_hook("ph1", hook)
        assert manager.unregister_provisioning_hook("ph1")
        assert not manager.unregister_provisioning_hook("ph1")


# ═══════════════════════════════════════════════════════════════════════════════
# Permission Enum Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestPermissions:
    """Tests for the Permission enum and its usage."""

    def test_permission_values_unique(self) -> None:
        """All permission values should be unique."""
        values = [p.value for p in Permission]
        assert len(values) == len(set(values))

    def test_role_has_permission(self) -> None:
        """Role.has_permission should work."""
        role = Role(name="test", permissions={Permission.AGENT_READ})
        assert role.has_permission(Permission.AGENT_READ)
        assert not role.has_permission(Permission.AGENT_DELETE)

    def test_role_has_any_permission(self) -> None:
        """Role.has_any_permission should work."""
        role = Role(name="test", permissions={Permission.DATA_READ, Permission.DATA_WRITE})
        assert role.has_any_permission({Permission.DATA_READ})
        assert role.has_any_permission({Permission.AGENT_DELETE, Permission.DATA_READ})
        assert not role.has_any_permission({Permission.AGENT_DELETE})

    def test_role_has_all_permissions(self) -> None:
        """Role.has_all_permissions should work."""
        role = Role(name="test", permissions={Permission.AGENT_CREATE, Permission.AGENT_READ})
        assert role.has_all_permissions({Permission.AGENT_CREATE, Permission.AGENT_READ})
        assert not role.has_all_permissions({Permission.AGENT_CREATE, Permission.AGENT_DELETE})

    def test_role_validation(self) -> None:
        """Role name validation should work."""
        with pytest.raises(ValueError):
            Role(name="")
        with pytest.raises(ValueError):
            Role(name="x" * 65)


# ═══════════════════════════════════════════════════════════════════════════════
# Enum Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestEnums:
    """Tests for enum behaviors."""

    def test_tenant_status_properties(self) -> None:
        """TenantStatus properties should be correct."""
        assert TenantStatus.ACTIVE.is_operational
        assert not TenantStatus.SUSPENDED.is_operational
        assert not TenantStatus.PROVISIONING.is_operational
        assert TenantStatus.DELETED.is_terminal
        assert TenantStatus.ARCHIVED.is_terminal

    def test_subscription_tier_ordering(self) -> None:
        """Tier ordering should work."""
        assert SubscriptionTier.ENTERPRISE >= SubscriptionTier.PROFESSIONAL
        assert SubscriptionTier.FREE <= SubscriptionTier.STARTER

    def test_isolation_mode_properties(self) -> None:
        """IsolationMode properties should be correct."""
        assert IsolationMode.DEDICATED.requires_dedicated_infrastructure
        assert not IsolationMode.SHARED.requires_dedicated_infrastructure
        assert IsolationMode.SHARED.allows_cross_tenant_caching
        assert not IsolationMode.DEDICATED.allows_cross_tenant_caching