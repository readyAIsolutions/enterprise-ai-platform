"""
Tests for RBACManager - roles, permissions, assignments, access checks.
"""

import unittest
from datetime import datetime, timedelta

from ..rbac import (
    RBACManager,
    Role,
    Permission,
    RoleAssignment,
    AccessResult,
)


class TestRBACManager(unittest.TestCase):

    def setUp(self):
        self.rbac = RBACManager()

    # --- Permissions ---

    def test_create_permission(self):
        perm = self.rbac.create_permission("custom:action", "custom", "action", "Custom action")
        self.assertEqual(perm.permission_id, "custom:action")
        self.assertEqual(perm.resource, "custom")
        self.assertEqual(perm.action, "action")

    def test_create_duplicate_permission(self):
        self.rbac.create_permission("dup:perm", "d", "p", "")
        with self.assertRaises(ValueError):
            self.rbac.create_permission("dup:perm", "d", "p", "")

    def test_get_permission(self):
        self.rbac.create_permission("get:me", "g", "m", "")
        self.assertIsNotNone(self.rbac.get_permission("get:me"))
        self.assertIsNone(self.rbac.get_permission("nonexistent"))

    def test_list_permissions(self):
        initial = len(self.rbac.list_permissions())
        self.rbac.create_permission("new:a", "n", "a", "")
        self.rbac.create_permission("new:b", "n", "b", "")
        self.assertEqual(len(self.rbac.list_permissions()), initial + 2)

    def test_delete_permission(self):
        self.rbac.create_permission("del:me", "d", "m", "")
        self.assertTrue(self.rbac.delete_permission("del:me"))
        self.assertIsNone(self.rbac.get_permission("del:me"))

    def test_delete_permission_removes_from_role(self):
        self.rbac.create_permission("temp:perm", "t", "p", "")
        role = self.rbac.create_role("temp_role", "Temp", permissions={"temp:perm"})
        self.assertIn("temp:perm", role.permissions)
        self.rbac.delete_permission("temp:perm")
        self.assertNotIn("temp:perm", role.permissions)

    # --- Roles ---

    def test_builtin_roles_exist(self):
        self.assertIsNotNone(self.rbac.get_role("admin"))
        self.assertIsNotNone(self.rbac.get_role("editor"))
        self.assertIsNotNone(self.rbac.get_role("viewer"))
        self.assertIsNotNone(self.rbac.get_role("auditor"))

    def test_builtin_roles_are_system(self):
        self.assertTrue(self.rbac.get_role("admin").is_system_role)
        self.assertTrue(self.rbac.get_role("editor").is_system_role)
        self.assertTrue(self.rbac.get_role("viewer").is_system_role)
        self.assertTrue(self.rbac.get_role("auditor").is_system_role)

    def test_create_role(self):
        perm_id = "c:act"
        self.rbac.create_permission(perm_id, "c", "act", "")
        role = self.rbac.create_role("custom", "Custom Role", permissions={perm_id}, priority=30)
        self.assertEqual(role.role_id, "custom")
        self.assertEqual(role.priority, 30)
        self.assertIn(perm_id, role.permissions)

    def test_create_role_invalid_permission(self):
        with self.assertRaises(ValueError):
            self.rbac.create_role("bad", "Bad", permissions={"nonexistent:perm"})

    def test_create_duplicate_role(self):
        self.rbac.create_role("dup_role", "Dup")
        with self.assertRaises(ValueError):
            self.rbac.create_role("dup_role", "Dup")

    def test_get_role(self):
        self.assertIsNotNone(self.rbac.get_role("admin"))
        self.assertIsNone(self.rbac.get_role("ghost"))

    def test_list_roles(self):
        roles = self.rbac.list_roles()
        self.assertGreaterEqual(len(roles), 4)  # At least built-in 4

    def test_update_role_permissions(self):
        role = self.rbac.create_role("updatable", "Updatable")
        self.rbac.update_role_permissions("updatable", add_permissions={"tenant:read"})
        self.assertIn("tenant:read", self.rbac.get_role("updatable").permissions)
        self.rbac.update_role_permissions("updatable", remove_permissions={"tenant:read"})
        self.assertNotIn("tenant:read", self.rbac.get_role("updatable").permissions)

    def test_update_system_role_raises(self):
        with self.assertRaises(ValueError):
            self.rbac.update_role_permissions("admin", add_permissions={"some:perm"})

    def test_delete_role(self):
        role = self.rbac.create_role("del_role", "Del")
        self.assertTrue(self.rbac.delete_role("del_role"))
        self.assertIsNone(self.rbac.get_role("del_role"))

    def test_delete_system_role_raises(self):
        with self.assertRaises(ValueError):
            self.rbac.delete_role("admin")

    def test_delete_role_removes_assignments(self):
        role = self.rbac.create_role("assign_del", "AD")
        self.rbac.assign_role("t1", "u1", "assign_del")
        self.rbac.delete_role("assign_del")
        self.assertEqual(len(self.rbac.get_user_roles("t1", "u1")), 0)

    # --- Role Assignment ---

    def test_assign_role(self):
        assignment = self.rbac.assign_role("t1", "u1", "admin", assigned_by="system")
        self.assertIsNotNone(assignment)
        self.assertEqual(assignment.tenant_id, "t1")
        self.assertEqual(assignment.user_id, "u1")
        self.assertEqual(assignment.role_id, "admin")

    def test_assign_role_invalid(self):
        with self.assertRaises(ValueError):
            self.rbac.assign_role("t1", "u1", "nonexistent_role")

    def test_get_user_roles(self):
        self.rbac.assign_role("t1", "u1", "admin")
        self.rbac.assign_role("t1", "u1", "viewer")
        roles = self.rbac.get_user_roles("t1", "u1")
        self.assertEqual(len(roles), 2)
        # Admin has higher priority, should be first
        self.assertEqual(roles[0].name, "admin")

    def test_get_user_roles_tenant_isolation(self):
        self.rbac.assign_role("t1", "u1", "admin")
        self.rbac.assign_role("t2", "u1", "viewer")
        t1_roles = self.rbac.get_user_roles("t1", "u1")
        t2_roles = self.rbac.get_user_roles("t2", "u1")
        self.assertEqual(len(t1_roles), 1)
        self.assertEqual(t1_roles[0].name, "admin")
        self.assertEqual(len(t2_roles), 1)
        self.assertEqual(t2_roles[0].name, "viewer")

    def test_revoke_role(self):
        self.rbac.assign_role("t1", "u1", "editor")
        self.assertTrue(self.rbac.revoke_role("t1", "u1", "editor"))
        self.assertEqual(len(self.rbac.get_user_roles("t1", "u1")), 0)

    def test_revoke_role_not_found(self):
        self.assertFalse(self.rbac.revoke_role("t1", "u1", "admin"))

    def test_revoke_all_roles(self):
        self.rbac.assign_role("t1", "u1", "editor")
        self.rbac.assign_role("t1", "u1", "viewer")
        count = self.rbac.revoke_all_roles("t1", "u1")
        self.assertEqual(count, 2)
        self.assertEqual(len(self.rbac.get_user_roles("t1", "u1")), 0)

    def test_get_user_assignments(self):
        self.rbac.assign_role("t1", "u1", "admin")
        assignments = self.rbac.get_user_assignments("t1", "u1")
        self.assertEqual(len(assignments), 1)
        self.assertEqual(assignments[0].role_id, "admin")

    def test_get_tenant_users(self):
        self.rbac.assign_role("t1", "u1", "admin")
        self.rbac.assign_role("t1", "u2", "editor")
        self.rbac.assign_role("t2", "u3", "viewer")
        t1_users = self.rbac.get_tenant_users("t1")
        self.assertEqual(t1_users, {"u1", "u2"})

    def test_role_expiration(self):
        past = datetime.utcnow() - timedelta(days=1)
        self.rbac.assign_role("t1", "u1", "editor", expires_at=past)
        roles = self.rbac.get_user_roles("t1", "u1")
        self.assertEqual(len(roles), 0)

    # --- Access Checks ---

    def test_admin_has_full_access(self):
        self.rbac.assign_role("t1", "u_admin", "admin")
        self.assertEqual(
            self.rbac.check_access("t1", "u_admin", "tenant:admin"),
            AccessResult.ALLOWED,
        )
        self.assertEqual(
            self.rbac.check_access("t1", "u_admin", "workspace:delete"),
            AccessResult.ALLOWED,
        )

    def test_viewer_read_only(self):
        self.rbac.assign_role("t1", "u_viewer", "viewer")
        self.assertEqual(
            self.rbac.check_access("t1", "u_viewer", "tenant:read"),
            AccessResult.ALLOWED,
        )
        self.assertEqual(
            self.rbac.check_access("t1", "u_viewer", "tenant:write"),
            AccessResult.DENIED,
        )

    def test_editor_can_write(self):
        self.rbac.assign_role("t1", "u_editor", "editor")
        self.assertEqual(
            self.rbac.check_access("t1", "u_editor", "workspace:write"),
            AccessResult.ALLOWED,
        )
        self.assertEqual(
            self.rbac.check_access("t1", "u_editor", "workspace:delete"),
            AccessResult.DENIED,
        )

    def test_auditor_can_read_audit(self):
        self.rbac.assign_role("t1", "u_auditor", "auditor")
        self.assertEqual(
            self.rbac.check_access("t1", "u_auditor", "audit:read"),
            AccessResult.ALLOWED,
        )
        self.assertEqual(
            self.rbac.check_access("t1", "u_auditor", "workspace:write"),
            AccessResult.DENIED,
        )

    def test_no_role_insufficient(self):
        self.assertEqual(
            self.rbac.check_access("t1", "stranger", "tenant:read"),
            AccessResult.INSUFFICIENT_ROLE,
        )

    def test_nonexistent_permission(self):
        self.rbac.assign_role("t1", "u1", "admin")
        self.assertEqual(
            self.rbac.check_access("t1", "u1", "ghost:perm"),
            AccessResult.NOT_FOUND,
        )

    def test_check_access_bulk(self):
        self.rbac.assign_role("t1", "u1", "editor")
        results = self.rbac.check_access_bulk("t1", "u1", [
            "tenant:read", "tenant:write", "tenant:delete",
        ])
        self.assertEqual(results["tenant:read"], AccessResult.ALLOWED)
        self.assertEqual(results["tenant:write"], AccessResult.ALLOWED)
        self.assertEqual(results["tenant:delete"], AccessResult.DENIED)

    def test_has_role(self):
        self.rbac.assign_role("t1", "u1", "admin")
        self.assertTrue(self.rbac.has_role("t1", "u1", "admin"))
        self.assertFalse(self.rbac.has_role("t1", "u1", "editor"))

    def test_is_admin(self):
        self.rbac.assign_role("t1", "u_admin", "admin")
        self.rbac.assign_role("t1", "u_editor", "editor")
        self.assertTrue(self.rbac.is_admin("t1", "u_admin"))
        self.assertFalse(self.rbac.is_admin("t1", "u_editor"))

    def test_get_effective_permissions(self):
        self.rbac.assign_role("t1", "u1", "editor")
        perms = self.rbac.get_effective_permissions("t1", "u1")
        self.assertIn("tenant:read", perms)
        self.assertIn("tenant:write", perms)
        self.assertNotIn("tenant:admin", perms)

    def test_effective_permissions_union(self):
        self.rbac.assign_role("t1", "u1", "viewer")
        self.rbac.assign_role("t1", "u1", "auditor")
        perms = self.rbac.get_effective_permissions("t1", "u1")
        self.assertIn("file:read", perms)        # from viewer
        self.assertIn("audit:read", perms)       # from auditor

    # --- Cleanup ---

    def test_cleanup_clears_assignments(self):
        self.rbac.assign_role("t1", "u1", "admin")
        self.assertEqual(len(self.rbac.get_user_roles("t1", "u1")), 1)
        self.rbac.cleanup()
        self.assertEqual(len(self.rbac.get_user_roles("t1", "u1")), 0)

    def test_cleanup_preserves_builtins(self):
        self.rbac.cleanup()
        self.assertIsNotNone(self.rbac.get_role("admin"))
        self.assertIsNotNone(self.rbac.get_permission("tenant:read"))


if __name__ == "__main__":
    unittest.main()