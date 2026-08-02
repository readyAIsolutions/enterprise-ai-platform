"""
Tests for TenantManager - CRUD, status, config, rate limiting.
"""

import time
import unittest
from datetime import datetime

from ..manager import (
    TenantManager,
    Tenant,
    TenantConfig,
    TenantStatus,
    RateLimitConfig,
)


class TestTenantManager(unittest.TestCase):

    def setUp(self):
        self.manager = TenantManager()

    # --- CRUD ---

    def test_create_tenant(self):
        t = self.manager.create_tenant(name="Acme Corp", contact_email="admin@acme.com")
        self.assertTrue(t.tenant_id.startswith("tn_"))
        self.assertEqual(t.name, "Acme Corp")
        self.assertEqual(t.status, TenantStatus.PROVISIONING)
        self.assertEqual(t.contact_email, "admin@acme.com")

    def test_create_tenant_with_config(self):
        t = self.manager.create_tenant(
            name="Beta Inc",
            config={"region": "us-east-1", "tier": "enterprise"},
            features={"ai", "analytics"},
            metadata={"department": "engineering"},
        )
        self.assertEqual(t.config.settings["region"], "us-east-1")
        self.assertEqual(t.config.settings["tier"], "enterprise")
        self.assertIn("ai", t.config.features)
        self.assertIn("analytics", t.config.features)
        self.assertEqual(t.config.metadata["department"], "engineering")

    def test_create_duplicate_name(self):
        self.manager.create_tenant(name="UniqueCorp")
        with self.assertRaises(ValueError):
            self.manager.create_tenant(name="UniqueCorp")

    def test_get_tenant(self):
        created = self.manager.create_tenant(name="TestCo")
        retrieved = self.manager.get_tenant(created.tenant_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.tenant_id, created.tenant_id)

    def test_get_tenant_not_found(self):
        self.assertIsNone(self.manager.get_tenant("nonexistent"))

    def test_get_tenant_by_name(self):
        self.manager.create_tenant(name="SearchMe")
        found = self.manager.get_tenant_by_name("SearchMe")
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "SearchMe")

    def test_get_tenant_by_name_not_found(self):
        self.assertIsNone(self.manager.get_tenant_by_name("Ghost"))

    def test_list_tenants(self):
        for name in ("A", "B", "C"):
            self.manager.create_tenant(name=name)
        tenants, total = self.manager.list_tenants()
        self.assertEqual(total, 3)
        self.assertEqual(len(tenants), 3)

    def test_list_tenants_status_filter(self):
        t1 = self.manager.create_tenant(name="Active1")
        t2 = self.manager.create_tenant(name="Suspended1")
        self.manager.activate_tenant(t1.tenant_id)  # PROVISIONING -> ACTIVE
        self.manager.activate_tenant(t2.tenant_id)  # PROVISIONING -> ACTIVE
        self.manager.set_tenant_status(t2.tenant_id, TenantStatus.SUSPENDED)
        active, total_active = self.manager.list_tenants(status_filter=TenantStatus.ACTIVE)
        suspended, total_suspended = self.manager.list_tenants(status_filter=TenantStatus.SUSPENDED)
        self.assertGreaterEqual(total_active, 1)
        self.assertGreaterEqual(total_suspended, 1)

    def test_list_tenants_pagination(self):
        for i in range(10):
            self.manager.create_tenant(name=f"Tenant{i}")
        page1, total = self.manager.list_tenants(page=1, page_size=3)
        page2, _ = self.manager.list_tenants(page=2, page_size=3)
        self.assertEqual(len(page1), 3)
        self.assertEqual(len(page2), 3)
        self.assertEqual(total, 10)

    def test_update_tenant(self):
        t = self.manager.create_tenant(name="OldName")
        updated = self.manager.update_tenant(
            t.tenant_id, name="NewName", contact_email="new@email.com",
            config_updates={"theme": "dark"}, custom_domain="new.example.com"
        )
        self.assertEqual(updated.name, "NewName")
        self.assertEqual(updated.contact_email, "new@email.com")
        self.assertEqual(updated.config.settings["theme"], "dark")
        self.assertEqual(updated.custom_domain, "new.example.com")

    def test_update_tenant_not_found(self):
        self.assertIsNone(self.manager.update_tenant("bad_id", name="Whatever"))

    def test_update_tenant_partial(self):
        t = self.manager.create_tenant(name="Partial", config={"keep": "me", "override": "old"})
        self.manager.update_tenant(t.tenant_id, config_updates={"override": "new", "add": "yes"})
        updated = self.manager.get_tenant(t.tenant_id)
        self.assertEqual(updated.config.settings["keep"], "me")
        self.assertEqual(updated.config.settings["override"], "new")
        self.assertEqual(updated.config.settings["add"], "yes")

    def test_delete_tenant_soft(self):
        t = self.manager.create_tenant(name="ToDelete")
        self.assertTrue(self.manager.delete_tenant(t.tenant_id, hard=False))
        retrieved = self.manager.get_tenant(t.tenant_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.status, TenantStatus.DEPROVISIONED)

    def test_delete_tenant_hard(self):
        t = self.manager.create_tenant(name="ToHardDelete")
        self.assertTrue(self.manager.delete_tenant(t.tenant_id, hard=True))
        self.assertIsNone(self.manager.get_tenant(t.tenant_id))

    def test_delete_tenant_not_found(self):
        self.assertFalse(self.manager.delete_tenant("bad_id"))

    def test_tenant_with_parent(self):
        parent = self.manager.create_tenant(name="ParentOrg")
        child = self.manager.create_tenant(name="ChildOrg", parent_tenant_id=parent.tenant_id)
        self.assertEqual(child.parent_tenant_id, parent.tenant_id)

    # --- Status ---

    def test_set_tenant_status(self):
        t = self.manager.create_tenant(name="StatusTest")
        updated = self.manager.set_tenant_status(t.tenant_id, TenantStatus.ACTIVE, "Setup done")
        self.assertEqual(updated.status, TenantStatus.ACTIVE)

    def test_invalid_status_transition(self):
        t = self.manager.create_tenant(name="BadTransition")
        self.manager.set_tenant_status(t.tenant_id, TenantStatus.ACTIVE)
        with self.assertRaises(ValueError):
            self.manager.set_tenant_status(t.tenant_id, TenantStatus.PROVISIONING)

    def test_get_tenant_status(self):
        t = self.manager.create_tenant(name="StatusCheck")
        self.assertEqual(self.manager.get_tenant_status(t.tenant_id), TenantStatus.PROVISIONING)

    def test_get_tenant_status_not_found(self):
        self.assertIsNone(self.manager.get_tenant_status("bad_id"))

    def test_activate_tenant(self):
        t = self.manager.create_tenant(name="ActivateMe")
        self.manager.activate_tenant(t.tenant_id)
        self.assertEqual(self.manager.get_tenant_status(t.tenant_id), TenantStatus.ACTIVE)

    def test_suspend_tenant(self):
        t = self.manager.create_tenant(name="SuspendMe")
        self.manager.activate_tenant(t.tenant_id)
        self.manager.suspend_tenant(t.tenant_id, "Billing issue")
        self.assertEqual(self.manager.get_tenant_status(t.tenant_id), TenantStatus.SUSPENDED)

    def test_get_tenants_by_status(self):
        t1 = self.manager.create_tenant(name="ActiveT")
        t2 = self.manager.create_tenant(name="TrialT")
        self.manager.activate_tenant(t1.tenant_id)
        self.manager.set_tenant_status(t2.tenant_id, TenantStatus.TRIAL)
        self.assertEqual(len(self.manager.get_tenants_by_status(TenantStatus.ACTIVE)), 1)
        self.assertEqual(len(self.manager.get_tenants_by_status(TenantStatus.TRIAL)), 1)

    def test_deprovisioned_cannot_transition(self):
        t = self.manager.create_tenant(name="DeadTenant")
        self.manager.activate_tenant(t.tenant_id)
        self.manager.delete_tenant(t.tenant_id, hard=False)  # DEPROVISIONED
        with self.assertRaises(ValueError):
            self.manager.set_tenant_status(t.tenant_id, TenantStatus.ACTIVE)

    # --- Config ---

    def test_get_config(self):
        t = self.manager.create_tenant(name="ConfigTest", config={"max_users": 100})
        self.assertEqual(self.manager.get_config(t.tenant_id, "max_users"), 100)

    def test_get_config_default(self):
        t = self.manager.create_tenant(name="ConfigTest2")
        self.assertEqual(self.manager.get_config(t.tenant_id, "missing", default=42), 42)

    def test_set_config(self):
        t = self.manager.create_tenant(name="SetConfig")
        self.assertTrue(self.manager.set_config(t.tenant_id, "theme", "light"))
        self.assertEqual(self.manager.get_config(t.tenant_id, "theme"), "light")

    def test_set_config_not_found(self):
        self.assertFalse(self.manager.set_config("bad_id", "key", "value"))

    def test_get_all_config(self):
        t = self.manager.create_tenant(name="FullConfig", config={"a": 1, "b": 2})
        self.assertEqual(self.manager.get_all_config(t.tenant_id), {"a": 1, "b": 2})

    def test_feature_flags(self):
        t = self.manager.create_tenant(name="FeatureTest")
        self.manager.enable_feature(t.tenant_id, "beta")
        self.assertTrue(self.manager.has_feature(t.tenant_id, "beta"))
        self.manager.disable_feature(t.tenant_id, "beta")
        self.assertFalse(self.manager.has_feature(t.tenant_id, "beta"))

    def test_feature_flag_not_found(self):
        self.assertFalse(self.manager.enable_feature("bad_id", "x"))
        self.assertFalse(self.manager.disable_feature("bad_id", "x"))
        self.assertFalse(self.manager.has_feature("bad_id", "x"))

    # --- Rate Limiting ---

    def test_rate_limit_allows_within_limit(self):
        t = self.manager.create_tenant(name="RateTest")
        self.manager.activate_tenant(t.tenant_id)
        for _ in range(10):
            self.assertTrue(self.manager.check_rate_limit(t.tenant_id))
            self.manager.release_rate_limit(t.tenant_id)

    def test_rate_limit_concurrent_blocking(self):
        t = self.manager.create_tenant(name="ConcurrentTest", rate_limit=RateLimitConfig(concurrent_limit=3))
        for _ in range(3):
            self.assertTrue(self.manager.check_rate_limit(t.tenant_id))
        self.assertFalse(self.manager.check_rate_limit(t.tenant_id))
        self.manager.release_rate_limit(t.tenant_id)
        self.assertTrue(self.manager.check_rate_limit(t.tenant_id))

    def test_rate_limit_disabled(self):
        t = self.manager.create_tenant(name="NoLimit", rate_limit=RateLimitConfig(enabled=False))
        for _ in range(100):
            self.assertTrue(self.manager.check_rate_limit(t.tenant_id))

    def test_rate_limit_not_found(self):
        self.assertFalse(self.manager.check_rate_limit("bad_id"))

    def test_get_rate_limit_status(self):
        t = self.manager.create_tenant(name="RateStatus")
        self.manager.check_rate_limit(t.tenant_id)
        self.manager.release_rate_limit(t.tenant_id)
        status = self.manager.get_rate_limit_status(t.tenant_id)
        self.assertIsNotNone(status)
        self.assertIn("requests_per_second", status)
        self.assertIn("concurrent", status)
        self.assertTrue(status["enabled"])

    def test_set_rate_limit_config(self):
        t = self.manager.create_tenant(name="RateConfig")
        updated = self.manager.set_rate_limit_config(t.tenant_id, RateLimitConfig(requests_per_second=500))
        self.assertEqual(updated.rate_limit.requests_per_second, 500)

    # --- Events ---

    def test_event_hooks(self):
        events = []
        self.manager.on("tenant_created", lambda t: events.append(("created", t.name)))
        self.manager.on("tenant_status_changed", lambda t, old, reason: events.append(("status", t.name, reason)))
        t = self.manager.create_tenant(name="EventTest")
        self.manager.activate_tenant(t.tenant_id)
        self.assertIn(("created", "EventTest"), events)
        self.assertTrue(any(e[0] == "status" for e in events))

    def test_event_hook_removal(self):
        calls = []
        cb = lambda t: calls.append(t.name)
        self.manager.on("tenant_created", cb)
        self.manager.create_tenant(name="First")
        self.assertEqual(len(calls), 1)
        self.manager.off("tenant_created", cb)
        self.manager.create_tenant(name="Second")
        self.assertEqual(len(calls), 1)

    # --- Misc ---

    def test_cleanup(self):
        self.manager.create_tenant(name="BeforeCleanup")
        self.manager.cleanup()
        _, total = self.manager.list_tenants()
        self.assertEqual(total, 0)

    def test_created_at_is_set(self):
        before = datetime.utcnow()
        t = self.manager.create_tenant(name="CreatedAt")
        self.assertIsNotNone(t.created_at)
        self.assertGreaterEqual(t.created_at, before)

    def test_updated_at_changes(self):
        t = self.manager.create_tenant(name="TimestampTest")
        original = t.updated_at
        time.sleep(0.001)
        self.manager.update_tenant(t.tenant_id, name="NewTimestamp")
        updated = self.manager.get_tenant(t.tenant_id)
        self.assertGreater(updated.updated_at, original)


if __name__ == "__main__":
    unittest.main()