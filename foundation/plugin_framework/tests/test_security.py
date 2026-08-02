"""
Comprehensive unit tests for the PluginSecurity module.

Tests cover:
- Permission model (flags, granting, revoking)
- Plugin permission profiles
- Access control decisions and enforcement
- Plugin signing and verification stubs
- Audit logging
- Trusted signer management
"""

import unittest
import hashlib

from enterprise.foundation.plugin_framework.security import (
    PluginSecurity,
    PluginPermissionProfile,
    Permission,
    SigningStatus,
    AccessRequest,
    AccessDecision,
    PluginSecurityError,
    PermissionDeniedError,
    PluginSignature,
)


class TestPermissionFlags(unittest.TestCase):
    """Tests for Permission flag enum."""

    def test_permission_none(self):
        """Test Permission.NONE is zero."""
        self.assertEqual(Permission.NONE.value, 0)

    def test_permission_combination(self):
        """Test combining permissions with |."""
        combined = Permission.FS_READ | Permission.FS_WRITE
        self.assertTrue(combined & Permission.FS_READ)
        self.assertTrue(combined & Permission.FS_WRITE)
        self.assertFalse(combined & Permission.NET_OUTBOUND)

    def test_permission_contains(self):
        """Test that combined flags contain individual flags."""
        perms = Permission.FS_READ | Permission.NET_DNS
        self.assertIn(Permission.FS_READ, perms)  # Using bool check
        self.assertTrue(perms & Permission.FS_READ)

    def test_fs_all_convenience(self):
        """Test FS_ALL contains all filesystem permissions."""
        self.assertTrue(Permission.FS_ALL & Permission.FS_READ)
        self.assertTrue(Permission.FS_ALL & Permission.FS_WRITE)
        self.assertTrue(Permission.FS_ALL & Permission.FS_DELETE)
        self.assertTrue(Permission.FS_ALL & Permission.FS_EXECUTE)

    def test_net_all_convenience(self):
        """Test NET_ALL contains all network permissions."""
        self.assertTrue(Permission.NET_ALL & Permission.NET_OUTBOUND)
        self.assertTrue(Permission.NET_ALL & Permission.NET_INBOUND)
        self.assertTrue(Permission.NET_ALL & Permission.NET_DNS)

    def test_all_convenience(self):
        """Test ALL contains everything."""
        self.assertTrue(Permission.ALL & Permission.FS_READ)
        self.assertTrue(Permission.ALL & Permission.NET_OUTBOUND)
        self.assertTrue(Permission.ALL & Permission.DATA_READ)


class TestPluginPermissionProfile(unittest.TestCase):
    """Tests for PluginPermissionProfile."""

    def test_default_profile(self):
        """Test default permission profile."""
        profile = PluginPermissionProfile(plugin_name="test")
        self.assertEqual(profile.plugin_name, "test")
        self.assertEqual(profile.permissions, Permission.NONE)
        self.assertEqual(profile.max_memory_mb, 256)
        self.assertEqual(profile.max_cpu_time_sec, 60)

    def test_has_permission(self):
        """Test checking permissions."""
        profile = PluginPermissionProfile(
            plugin_name="test",
            permissions=Permission.FS_READ | Permission.NET_DNS,
        )
        self.assertTrue(profile.has_permission(Permission.FS_READ))
        self.assertTrue(profile.has_permission(Permission.NET_DNS))
        self.assertFalse(profile.has_permission(Permission.FS_WRITE))
        self.assertFalse(profile.has_permission(Permission.NET_OUTBOUND))

    def test_has_permission_combined(self):
        """Test has_permission with combined flags."""
        profile = PluginPermissionProfile(
            plugin_name="test",
            permissions=Permission.FS_READ | Permission.FS_WRITE,
        )
        self.assertTrue(profile.has_permission(
            Permission.FS_READ | Permission.FS_WRITE
        ))
        self.assertFalse(profile.has_permission(
            Permission.FS_READ | Permission.FS_DELETE
        ))

    def test_grant_permission(self):
        """Test granting permissions."""
        profile = PluginPermissionProfile(plugin_name="test")
        profile.grant(Permission.FS_READ)
        self.assertTrue(profile.has_permission(Permission.FS_READ))

        profile.grant(Permission.NET_OUTBOUND)
        self.assertTrue(profile.has_permission(Permission.FS_READ))
        self.assertTrue(profile.has_permission(Permission.NET_OUTBOUND))

    def test_revoke_permission(self):
        """Test revoking permissions."""
        profile = PluginPermissionProfile(
            plugin_name="test",
            permissions=Permission.FS_READ | Permission.FS_WRITE,
        )
        profile.revoke(Permission.FS_WRITE)
        self.assertTrue(profile.has_permission(Permission.FS_READ))
        self.assertFalse(profile.has_permission(Permission.FS_WRITE))

    def test_custom_resource_limits(self):
        """Test custom resource limit values."""
        profile = PluginPermissionProfile(
            plugin_name="test",
            max_memory_mb=512,
            max_cpu_time_sec=120,
            max_file_size_mb=200,
        )
        self.assertEqual(profile.max_memory_mb, 512)
        self.assertEqual(profile.max_cpu_time_sec, 120)
        self.assertEqual(profile.max_file_size_mb, 200)

    def test_allowed_denied_paths(self):
        """Test allowed and denied paths."""
        profile = PluginPermissionProfile(
            plugin_name="test",
            allowed_paths=["/data", "/tmp"],
            denied_paths=["/etc"],
            allowed_hosts=["localhost"],
            denied_hosts=["evil.com"],
        )
        self.assertIn("/data", profile.allowed_paths)
        self.assertIn("/etc", profile.denied_paths)
        self.assertIn("localhost", profile.allowed_hosts)
        self.assertIn("evil.com", profile.denied_hosts)


class TestPluginSecurityProfileManagement(unittest.TestCase):
    """Tests for PluginSecurity profile management."""

    def setUp(self):
        self.security = PluginSecurity()

    def test_register_profile(self):
        """Test registering a permission profile."""
        profile = PluginPermissionProfile(plugin_name="plugin_a")
        self.security.register_profile(profile)
        retrieved = self.security.get_profile("plugin_a")
        self.assertEqual(retrieved.plugin_name, "plugin_a")

    def test_register_duplicate_raises(self):
        """Test registering duplicate profile raises ValueError."""
        self.security.register_profile(
            PluginPermissionProfile(plugin_name="plugin_a")
        )
        with self.assertRaises(ValueError):
            self.security.register_profile(
                PluginPermissionProfile(plugin_name="plugin_a")
            )

    def test_get_profile_default(self):
        """Test getting default profile for unregistered plugin."""
        profile = self.security.get_profile("unknown")
        self.assertEqual(profile.plugin_name, "unknown")
        self.assertTrue(profile.has_permission(Permission.FS_READ_RESTRICTED))

    def test_update_profile(self):
        """Test updating an existing profile."""
        self.security.register_profile(
            PluginPermissionProfile(plugin_name="plugin_a")
        )
        updated = PluginPermissionProfile(
            plugin_name="plugin_a",
            permissions=Permission.FS_READ | Permission.NET_DNS,
        )
        self.security.update_profile(updated)
        profile = self.security.get_profile("plugin_a")
        self.assertTrue(profile.has_permission(Permission.FS_READ))

    def test_update_nonexistent_raises(self):
        """Test updating nonexistent profile raises KeyError."""
        with self.assertRaises(KeyError):
            self.security.update_profile(
                PluginPermissionProfile(plugin_name="ghost")
            )

    def test_remove_profile(self):
        """Test removing a profile."""
        self.security.register_profile(
            PluginPermissionProfile(plugin_name="plugin_a")
        )
        self.security.remove_profile("plugin_a")
        # Should now get default
        profile = self.security.get_profile("plugin_a")
        self.assertEqual(profile.plugin_name, "plugin_a")
        # Default permissions
        self.assertTrue(profile.has_permission(Permission.FS_READ_RESTRICTED))

    def test_remove_nonexistent_no_error(self):
        """Test removing nonexistent profile doesn't raise."""
        self.security.remove_profile("nope")  # Should not raise

    def test_set_default_permissions(self):
        """Test setting default permissions."""
        self.security.set_default_permissions(
            Permission.FS_READ | Permission.FS_WRITE
        )
        profile = self.security.get_profile("new_plugin")
        self.assertTrue(profile.has_permission(Permission.FS_READ))
        self.assertTrue(profile.has_permission(Permission.FS_WRITE))


class TestPluginSecurityAccessControl(unittest.TestCase):
    """Tests for access control decision-making."""

    def setUp(self):
        self.security = PluginSecurity()
        self.security.register_profile(PluginPermissionProfile(
            plugin_name="reader",
            permissions=Permission.FS_READ_RESTRICTED,
            allowed_paths=["/data", "/tmp"],
        ))
        self.security.register_profile(PluginPermissionProfile(
            plugin_name="full_access",
            permissions=Permission.FS_ALL | Permission.NET_ALL,
            allowed_paths=["/"],
            denied_paths=["/etc/secret"],
        ))

    def test_check_access_granted(self):
        """Test access is granted with proper permissions."""
        request = AccessRequest(
            plugin_name="reader",
            permission=Permission.FS_READ_RESTRICTED,
            resource="/data/file.txt",
        )
        decision = self.security.check_access(request)
        self.assertTrue(decision.allowed)

    def test_check_access_denied_no_permission(self):
        """Test access denied when plugin lacks permission."""
        request = AccessRequest(
            plugin_name="reader",
            permission=Permission.FS_WRITE,
            resource="/data/file.txt",
        )
        decision = self.security.check_access(request)
        self.assertFalse(decision.allowed)
        self.assertIn("FS_WRITE", decision.reason)

    def test_check_access_path_allowed(self):
        """Test access with path in allowed list."""
        request = AccessRequest(
            plugin_name="reader",
            permission=Permission.FS_READ_RESTRICTED,
            resource="/data/file.txt",
        )
        decision = self.security.check_access(request)
        self.assertTrue(decision.allowed)

    def test_check_access_path_not_allowed(self):
        """Test access with path not in allowed list."""
        request = AccessRequest(
            plugin_name="reader",
            permission=Permission.FS_READ_RESTRICTED,
            resource="/secret/file.txt",
        )
        decision = self.security.check_access(request)
        self.assertFalse(decision.allowed)

    def test_check_access_path_denied(self):
        """Test access denied for explicitly denied paths."""
        request = AccessRequest(
            plugin_name="full_access",
            permission=Permission.FS_READ_RESTRICTED,
            resource="/etc/secret/key.pem",
        )
        decision = self.security.check_access(request)
        self.assertFalse(decision.allowed)

    def test_assert_access_granted(self):
        """Test assert_access passes when allowed."""
        request = AccessRequest(
            plugin_name="reader",
            permission=Permission.FS_READ_RESTRICTED,
            resource="/data/file.txt",
        )
        self.security.assert_access(request)  # Should not raise

    def test_assert_access_denied(self):
        """Test assert_access raises when denied."""
        request = AccessRequest(
            plugin_name="reader",
            permission=Permission.FS_WRITE,
        )
        with self.assertRaises(PermissionDeniedError) as ctx:
            self.security.assert_access(request)
        self.assertEqual(ctx.exception.plugin_name, "reader")

    def test_access_decision_dataclass(self):
        """Test AccessDecision dataclass."""
        decision = AccessDecision(
            allowed=True,
            reason="Granted",
            audit_id="abc123",
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "Granted")
        self.assertEqual(decision.audit_id, "abc123")


class TestPluginSecuritySigning(unittest.TestCase):
    """Tests for plugin signing and verification."""

    def setUp(self):
        self.security = PluginSecurity()

    def test_sign_plugin(self):
        """Test signing a plugin."""
        content = b"plugin source code here"
        signature = self.security.sign_plugin("test_plugin", content, "org.nous")
        self.assertIsInstance(signature, PluginSignature)
        self.assertEqual(signature.signer_id, "org.nous")
        self.assertEqual(signature.algorithm, "sha256-rsa")
        self.assertNotEqual(signature.signature_hex, "")

    def test_verify_plugin_not_signed(self):
        """Test verifying unsigned plugin."""
        status = self.security.verify_plugin("test_plugin", b"content")
        self.assertEqual(status, SigningStatus.NOT_SIGNED)

    def test_verify_plugin_verified(self):
        """Test verifying a signed plugin."""
        content = b"plugin content"
        self.security.sign_plugin("test_plugin", content, "org.nous")
        self.security.add_trusted_signer("org.nous")

        status = self.security.verify_plugin("test_plugin", content)
        self.assertEqual(status, SigningStatus.VERIFIED)

    def test_verify_plugin_untrusted_signer(self):
        """Test verifying a plugin signed by untrusted signer."""
        content = b"plugin content"
        self.security.sign_plugin("test_plugin", content, "evil.corp")

        status = self.security.verify_plugin("test_plugin", content)
        self.assertEqual(status, SigningStatus.UNTRUSTED_SIGNER)

    def test_verify_plugin_tampered(self):
        """Test verifying tampered content."""
        original_content = b"original content"
        self.security.sign_plugin("test_plugin", original_content, "org.nous")
        self.security.add_trusted_signer("org.nous")

        tampered = b"tampered content"
        status = self.security.verify_plugin("test_plugin", tampered)
        self.assertEqual(status, SigningStatus.VERIFICATION_FAILED)

    def test_has_valid_signature(self):
        """Test has_valid_signature convenience method."""
        content = b"valid content"
        self.security.sign_plugin("test_plugin", content, "org.nous")
        self.security.add_trusted_signer("org.nous")

        self.assertTrue(self.security.has_valid_signature("test_plugin", content))

    def test_has_valid_signature_false(self):
        """Test has_valid_signature returns False for unsigned."""
        self.assertFalse(
            self.security.has_valid_signature("unknown", b"anything")
        )


class TestPluginSecurityTrustedSigners(unittest.TestCase):
    """Tests for trusted signer management."""

    def setUp(self):
        self.security = PluginSecurity()

    def test_add_trusted_signer(self):
        """Test adding a trusted signer."""
        self.security.add_trusted_signer("org.nous")
        self.assertTrue(self.security.is_signer_trusted("org.nous"))

    def test_remove_trusted_signer(self):
        """Test removing a trusted signer."""
        self.security.add_trusted_signer("org.nous")
        self.security.remove_trusted_signer("org.nous")
        self.assertFalse(self.security.is_signer_trusted("org.nous"))

    def test_remove_nonexistent_no_error(self):
        """Test removing nonexistent trusted signer doesn't raise."""
        self.security.remove_trusted_signer("nobody")

    def test_is_signer_trusted_default(self):
        """Test default trust state is False."""
        self.assertFalse(self.security.is_signer_trusted("random"))

    def test_multiple_signers(self):
        """Test multiple trusted signers."""
        self.security.add_trusted_signer("org.a")
        self.security.add_trusted_signer("org.b")
        self.assertTrue(self.security.is_signer_trusted("org.a"))
        self.assertTrue(self.security.is_signer_trusted("org.b"))


class TestPluginSecurityAudit(unittest.TestCase):
    """Tests for audit logging."""

    def setUp(self):
        self.security = PluginSecurity()
        self.security.register_profile(PluginPermissionProfile(
            plugin_name="test",
            permissions=Permission.FS_READ,
        ))

    def test_audit_log_entries(self):
        """Test audit log captures access decisions."""
        request1 = AccessRequest(
            plugin_name="test",
            permission=Permission.FS_READ,
        )
        request2 = AccessRequest(
            plugin_name="test",
            permission=Permission.FS_WRITE,
        )

        self.security.check_access(request1)
        self.security.check_access(request2)

        log = self.security.get_audit_log()
        self.assertEqual(len(log), 2)
        self.assertTrue(log[0].allowed)
        self.assertFalse(log[1].allowed)

    def test_audit_log_limit(self):
        """Test audit log respects limit parameter."""
        for i in range(10):
            self.security.check_access(AccessRequest(
                plugin_name="test",
                permission=Permission.FS_READ,
            ))

        log = self.security.get_audit_log(limit=5)
        self.assertEqual(len(log), 5)

    def test_clear_audit_log(self):
        """Test clearing the audit log."""
        self.security.check_access(AccessRequest(
            plugin_name="test",
            permission=Permission.FS_READ,
        ))
        self.security.clear_audit_log()
        log = self.security.get_audit_log()
        self.assertEqual(len(log), 0)


class TestPluginSignature(unittest.TestCase):
    """Tests for PluginSignature class."""

    def test_default_signature(self):
        """Test default signature values."""
        sig = PluginSignature()
        self.assertEqual(sig.verify(b"content"), SigningStatus.NOT_SIGNED)

    def test_custom_signature(self):
        """Test custom signature."""
        content = b"test content"
        content_hash = hashlib.sha256(content).hexdigest()

        sig = PluginSignature(
            signer_id="org.nous",
            signature_hex=content_hash,
            algorithm="sha256-rsa",
        )
        status = sig.verify(content)
        self.assertEqual(status, SigningStatus.VERIFIED)

    def test_signature_mismatch(self):
        """Test signature verification failure."""
        content = b"original content"
        content_hash = hashlib.sha256(content).hexdigest()

        sig = PluginSignature(
            signer_id="org.nous",
            signature_hex=content_hash,
        )
        # Verify with different content
        status = sig.verify(b"different content")
        self.assertEqual(status, SigningStatus.VERIFICATION_FAILED)


class TestPluginSecurityErrorMessages(unittest.TestCase):
    """Tests for error message formatting."""

    def test_permission_denied_error_format(self):
        """Test PermissionDeniedError message formatting."""
        err = PermissionDeniedError(
            plugin_name="bad_plugin",
            permission=Permission.NET_OUTBOUND,
            resource="evil.com:666",
        )
        self.assertIn("bad_plugin", str(err))
        self.assertIn("NET_OUTBOUND", str(err))
        self.assertIn("evil.com:666", str(err))

    def test_permission_denied_error_no_resource(self):
        """Test PermissionDeniedError without resource."""
        err = PermissionDeniedError(
            plugin_name="bad_plugin",
            permission=Permission.FS_WRITE,
        )
        self.assertIn("bad_plugin", str(err))
        self.assertIn("FS_WRITE", str(err))

    def test_plugin_security_error_base(self):
        """Test base PluginSecurityError."""
        err = PluginSecurityError("generic error")
        self.assertIsInstance(err, Exception)


if __name__ == "__main__":
    unittest.main()