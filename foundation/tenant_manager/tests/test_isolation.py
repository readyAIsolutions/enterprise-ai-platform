"""
Tests for TenantIsolation - data isolation, quotas, cross-tenant access, encryption.
"""

import unittest

from ..isolation import (
    TenantIsolation,
    ResourceQuota,
    IsolationPolicy,
    QuotaUsage,
)


class TestTenantIsolation(unittest.TestCase):

    def setUp(self):
        self.isolation = TenantIsolation()

    # --- Policy ---

    def test_default_policy_is_strict(self):
        self.assertEqual(
            self.isolation.get_isolation_policy("any_tenant"),
            IsolationPolicy.STRICT,
        )

    def test_set_and_get_policy(self):
        self.isolation.set_isolation_policy("t1", IsolationPolicy.LOGICAL)
        self.assertEqual(
            self.isolation.get_isolation_policy("t1"), IsolationPolicy.LOGICAL
        )

    # --- Quotas ---

    def test_set_and_get_quota(self):
        quota = ResourceQuota(max_storage_bytes=1024, max_users=10)
        self.isolation.set_resource_quota("t1", quota)
        retrieved = self.isolation.get_resource_quota("t1")
        self.assertEqual(retrieved.max_storage_bytes, 1024)
        self.assertEqual(retrieved.max_users, 10)

    def test_default_quota(self):
        quota = self.isolation.get_resource_quota("unknown")
        self.assertEqual(quota.max_storage_bytes, 10 * 1024 * 1024 * 1024)

    def test_check_quota_within_limit(self):
        self.isolation.set_resource_quota("t1", ResourceQuota(max_users=5))
        self.isolation.get_quota_usage("t1")  # ensure initialized
        for _ in range(5):
            self.assertTrue(self.isolation.check_quota("t1", "users"))

    def test_check_quota_exceeded(self):
        self.isolation.set_resource_quota("t1", ResourceQuota(max_users=2))
        self.isolation.track_usage("t1", "users", 2)
        self.assertFalse(self.isolation.check_quota("t1", "users"))

    def test_track_usage(self):
        self.isolation.set_resource_quota("t1", ResourceQuota(max_storage_bytes=2000))
        self.assertTrue(self.isolation.track_usage("t1", "storage", 500))
        self.assertTrue(self.isolation.track_usage("t1", "storage", 500))
        usage = self.isolation.get_quota_usage("t1")
        self.assertEqual(usage.storage_bytes_used, 1000)

    def test_track_usage_quota_exceeded(self):
        self.isolation.set_resource_quota("t1", ResourceQuota(max_api_calls_per_day=5))
        for _ in range(5):
            self.assertTrue(self.isolation.track_usage("t1", "api_calls"))
        self.assertFalse(self.isolation.track_usage("t1", "api_calls"))

    def test_release_usage(self):
        self.isolation.set_resource_quota("t1", ResourceQuota(max_concurrent_sessions=10))
        self.isolation.track_usage("t1", "sessions", 5)
        self.isolation.release_usage("t1", "sessions", 3)
        usage = self.isolation.get_quota_usage("t1")
        self.assertEqual(usage.concurrent_sessions, 2)

    def test_release_usage_floor_zero(self):
        self.isolation.set_resource_quota("t1", ResourceQuota(max_storage_bytes=1000))
        self.isolation.track_usage("t1", "storage", 100)
        self.isolation.release_usage("t1", "storage", 200)
        usage = self.isolation.get_quota_usage("t1")
        self.assertEqual(usage.storage_bytes_used, 0)

    def test_custom_resource_quota(self):
        quota = ResourceQuota(custom_limits={"widgets": 10})
        self.isolation.set_resource_quota("t1", quota)
        self.assertTrue(self.isolation.track_usage("t1", "widgets", 5))
        self.assertFalse(self.isolation.check_quota("t1", "widgets", 6))

    def test_get_quota_exceeded_resources(self):
        quota = ResourceQuota(max_users=2, max_workspaces=1)
        self.isolation.set_resource_quota("t1", quota)
        self.isolation.track_usage("t1", "users", 1)
        self.isolation.track_usage("t1", "users", 1)
        self.isolation.track_usage("t1", "users", 1)  # this one exceeds, won't be counted
        self.isolation.track_usage("t1", "workspaces", 1)
        exceeded = self.isolation.get_quota_exceeded_resources("t1")
        self.assertIn("users", exceeded)

    # --- Cross-Tenant Access ---

    def test_register_and_check_data_access(self):
        self.isolation.register_data_ownership("t1", "data_123")
        self.assertTrue(self.isolation.check_data_access("t1", "data_123"))
        self.assertFalse(self.isolation.check_data_access("t2", "data_123"))

    def test_unregistered_data_allowed(self):
        self.assertTrue(self.isolation.check_data_access("t1", "unregistered_data"))

    def test_cross_tenant_attempts_logged(self):
        self.isolation.register_data_ownership("t1", "data_456")
        self.isolation.check_data_access("t2", "data_456")
        attempts = self.isolation.get_cross_tenant_access_attempts("t2")
        self.assertIn("data_456", attempts)

    def test_isolate_data(self):
        wrapped = self.isolation.isolate_data("t1", "secret payload")
        self.assertEqual(wrapped["tenant_id"], "t1")
        self.assertEqual(wrapped["payload"], "secret payload")
        self.assertIn("data_id", wrapped)
        self.assertTrue(self.isolation.check_data_access("t1", wrapped["data_id"]))

    def test_validate_tenant_access_same_tenant(self):
        self.assertTrue(self.isolation.validate_tenant_access("t1", "t1"))

    def test_validate_tenant_access_strict_denies(self):
        self.isolation.set_isolation_policy("t1", IsolationPolicy.STRICT)
        self.assertFalse(self.isolation.validate_tenant_access("t1", "t2"))

    def test_validate_tenant_access_shared_allows(self):
        self.isolation.set_isolation_policy("t1", IsolationPolicy.SHARED)
        self.assertTrue(self.isolation.validate_tenant_access("t1", "t2"))

    # --- Encryption ---

    def test_generate_and_get_key(self):
        key = self.isolation.generate_encryption_key("t1")
        self.assertEqual(len(key), 32)
        self.assertEqual(self.isolation.get_encryption_key("t1"), key)

    def test_get_key_not_found(self):
        self.assertIsNone(self.isolation.get_encryption_key("unknown"))

    def test_encrypt_decrypt_roundtrip(self):
        self.isolation.generate_encryption_key("t1")
        plaintext = "Hello, secure world!"
        ciphertext = self.isolation.encrypt_data("t1", plaintext)
        self.assertNotEqual(ciphertext, plaintext)
        decrypted = self.isolation.decrypt_data("t1", ciphertext)
        self.assertEqual(decrypted, plaintext)

    def test_encrypt_without_key(self):
        with self.assertRaises(ValueError):
            self.isolation.encrypt_data("t1", "data")

    def test_decrypt_without_key(self):
        with self.assertRaises(ValueError):
            self.isolation.decrypt_data("t1", "bogus")

    def test_decrypt_tampered_data(self):
        self.isolation.generate_encryption_key("t1")
        ciphertext = self.isolation.encrypt_data("t1", "original")
        # Tamper with ciphertext
        tampered = ciphertext[:-1] + ("A" if ciphertext[-1] != "A" else "B")
        with self.assertRaises(ValueError):
            self.isolation.decrypt_data("t1", tampered)

    def test_encrypt_different_tenants_different_keys(self):
        self.isolation.generate_encryption_key("t1")
        self.isolation.generate_encryption_key("t2")
        ct1 = self.isolation.encrypt_data("t1", "data")
        ct2 = self.isolation.encrypt_data("t2", "data")
        self.assertNotEqual(ct1, ct2)

    def test_rotate_key(self):
        old_key = self.isolation.generate_encryption_key("t1")
        new_key = self.isolation.rotate_encryption_key("t1")
        self.assertNotEqual(old_key, new_key)
        self.assertEqual(self.isolation.get_encryption_key("t1"), new_key)

    def test_revoke_key(self):
        self.isolation.generate_encryption_key("t1")
        self.isolation.revoke_encryption_key("t1")
        self.assertIsNone(self.isolation.get_encryption_key("t1"))

    # --- Cross-tenant encryption isolation ---

    def test_cross_tenant_cannot_decrypt(self):
        self.isolation.generate_encryption_key("t1")
        self.isolation.generate_encryption_key("t2")
        ct = self.isolation.encrypt_data("t1", "secret")
        with self.assertRaises(ValueError):
            self.isolation.decrypt_data("t2", ct)

    # --- Cleanup ---

    def test_cleanup(self):
        self.isolation.set_isolation_policy("t1", IsolationPolicy.LOGICAL)
        self.isolation.set_resource_quota("t1", ResourceQuota(max_users=5))
        self.isolation.generate_encryption_key("t1")
        self.isolation.cleanup()
        self.assertEqual(self.isolation.get_isolation_policy("t1"), IsolationPolicy.STRICT)
        self.assertIsNone(self.isolation.get_encryption_key("t1"))


if __name__ == "__main__":
    unittest.main()