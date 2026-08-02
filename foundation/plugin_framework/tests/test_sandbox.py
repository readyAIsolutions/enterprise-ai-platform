"""
Comprehensive unit tests for the SandboxExecutor and related classes.

Tests cover:
- Sandbox configuration and resource limits
- Execution with timeout handling
- Import restrictions
- Filesystem access controls
- Network access checks
- Workspace isolation
- Error handling
"""

import os
import unittest
import tempfile

from enterprise.foundation.plugin_framework.sandbox import (
    SandboxConfig,
    SandboxExecutor,
    SandboxResult,
    SandboxError,
    TimeoutError,
    RestrictedImportError,
    ResourceLimitExceededError,
    ImportGuard,
)
from enterprise.foundation.plugin_framework.security import (
    PluginPermissionProfile,
    Permission,
    PermissionDeniedError,
)


class TestSandboxConfig(unittest.TestCase):
    """Tests for SandboxConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = SandboxConfig()
        self.assertEqual(config.max_memory_mb, 256)
        self.assertEqual(config.max_cpu_time_sec, 60)
        self.assertEqual(config.max_execution_time_sec, 30)
        self.assertFalse(config.allow_network)
        self.assertTrue(config.allow_builtins)

    def test_custom_config(self):
        """Test custom configuration."""
        config = SandboxConfig(
            max_memory_mb=128,
            max_cpu_time_sec=30,
            allow_network=True,
            allowed_hosts=["localhost"],
            allowed_ports={8080, 443},
            allowed_paths=["/tmp"],
        )
        self.assertEqual(config.max_memory_mb, 128)
        self.assertTrue(config.allow_network)
        self.assertIn("localhost", config.allowed_hosts)
        self.assertIn(8080, config.allowed_ports)
        self.assertIn("/tmp", config.allowed_paths)

    def test_from_permission_profile_basic(self):
        """Test creating config from a basic permission profile."""
        profile = PluginPermissionProfile(
            plugin_name="test",
            permissions=Permission.FS_READ | Permission.NET_DNS,
            allowed_paths=["/data"],
            max_memory_mb=512,
        )
        config = SandboxConfig.from_permission_profile(profile)
        self.assertEqual(config.max_memory_mb, 512)
        self.assertIn("/data", config.allowed_paths)

    def test_from_permission_profile_network(self):
        """Test config from profile with network permissions."""
        profile = PluginPermissionProfile(
            plugin_name="test",
            permissions=Permission.NET_OUTBOUND | Permission.NET_DNS,
            allowed_hosts=["api.example.com"],
            allowed_ports={443},
        )
        config = SandboxConfig.from_permission_profile(profile)
        self.assertTrue(config.allow_network)
        self.assertTrue(config.allow_dns)
        self.assertIn("api.example.com", config.allowed_hosts)


class TestImportGuard(unittest.TestCase):
    """Tests for ImportGuard."""

    def test_allowed_import_passes(self):
        """Test that imports of allowed modules pass through."""
        config = SandboxConfig(allowed_modules={"json", "math"})
        guard = ImportGuard(config, "test_plugin")

        # json and math should pass (returns None = pass through)
        result = guard.find_spec("json")
        self.assertIsNone(result)

    def test_blocked_module_raises(self):
        """Test that blocked modules raise RestrictedImportError."""
        config = SandboxConfig(
            blocked_modules={"ctypes"},
            allowed_modules=set(),  # Empty = all allowed except blocked
        )
        guard = ImportGuard(config, "test_plugin")

        with self.assertRaises(RestrictedImportError):
            guard.find_spec("ctypes")

    def test_module_not_in_allowed_raises(self):
        """Test that modules not in allowed list raise error.

        Uses a nonexistent module name to avoid sys.modules caching issues.
        """
        config = SandboxConfig(allowed_modules={"json"})
        guard = ImportGuard(config, "test_plugin")

        with self.assertRaises(RestrictedImportError):
            guard.find_spec("some_never_imported_module")

    def test_parent_module_allowed(self):
        """Test that submodules of allowed modules pass."""
        config = SandboxConfig(allowed_modules={"json"})
        guard = ImportGuard(config, "test_plugin")

        # json.decoder is a submodule of json; should pass
        result = guard.find_spec("json.decoder")
        self.assertIsNone(result)


class TestSandboxExecutorExecution(unittest.TestCase):
    """Tests for SandboxExecutor execution."""

    def setUp(self):
        self.config = SandboxConfig(
            max_execution_time_sec=5,
            max_memory_mb=1024,
        )
        self.executor = SandboxExecutor(self.config, "test_plugin")

    def test_execute_simple_function(self):
        """Test executing a simple function."""
        result = self.executor.execute(lambda x, y: x + y, 10, 20)
        self.assertTrue(result.success)
        self.assertEqual(result.result, 30)
        self.assertGreater(result.execution_time_sec, 0)

    def test_execute_with_kwargs(self):
        """Test execution with keyword arguments."""
        result = self.executor.execute(
            lambda greeting, name: f"{greeting}, {name}!",
            greeting="Hello",
            name="World",
        )
        self.assertTrue(result.success)
        self.assertEqual(result.result, "Hello, World!")

    def test_execute_returns_sandbox_result(self):
        """Test that execute always returns a SandboxResult."""
        result = self.executor.execute(lambda: 42)
        self.assertIsInstance(result, SandboxResult)

    def test_execute_exception_captured(self):
        """Test that exceptions in the function are captured in result."""
        result = self.executor.execute(lambda: 1 / 0)
        self.assertFalse(result.success)
        self.assertIsInstance(result.error, ZeroDivisionError)

    def test_execute_with_timeout(self):
        """Test that functions exceeding timeout are stopped."""
        import time

        def slow_func():
            time.sleep(10)
            return "done"

        config = SandboxConfig(max_execution_time_sec=1)
        executor = SandboxExecutor(config, "test_plugin")

        result = executor.execute(slow_func)
        self.assertFalse(result.success)
        self.assertIsInstance(result.error, TimeoutError)

    def test_execute_fast_function_no_timeout(self):
        """Test that fast functions return normally."""
        result = self.executor.execute(lambda: "fast")
        self.assertTrue(result.success)
        self.assertEqual(result.result, "fast")


class TestSandboxExecutorFilesystem(unittest.TestCase):
    """Tests for filesystem access control."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_read_allowed_path(self):
        """Test reading from an allowed path."""
        # Create a file in allowed path
        test_file = os.path.join(self.tmp_dir, "allowed.txt")
        with open(test_file, "w") as f:
            f.write("secret data")

        config = SandboxConfig(allowed_paths=[self.tmp_dir])
        executor = SandboxExecutor(config, "test_plugin")

        def read_func():
            with open(test_file, "r") as f:
                return f.read()

        result = executor.execute(read_func)
        self.assertTrue(result.success)
        self.assertEqual(result.result, "secret data")

    def test_read_denied_path(self):
        """Test reading from a non-allowed path is denied."""
        denied_dir = os.path.join(self.tmp_dir, "denied")
        os.makedirs(denied_dir)
        secret_file = os.path.join(denied_dir, "secret.txt")
        with open(secret_file, "w") as f:
            f.write("top secret")

        allowed_dir = os.path.join(self.tmp_dir, "allowed")
        os.makedirs(allowed_dir)

        config = SandboxConfig(allowed_paths=[allowed_dir])
        executor = SandboxExecutor(config, "test_plugin")

        def read_func():
            with open(secret_file, "r") as f:
                return f.read()

        result = executor.execute(read_func)
        self.assertFalse(result.success)
        self.assertIsInstance(result.error, PermissionDeniedError)

    def test_write_allowed_path(self):
        """Test writing to an allowed writable path."""
        writable_dir = os.path.join(self.tmp_dir, "writable")
        os.makedirs(writable_dir)

        config = SandboxConfig(
            allowed_paths=[writable_dir],
            writable_paths=[writable_dir],
        )
        executor = SandboxExecutor(config, "test_plugin")

        output_file = os.path.join(writable_dir, "output.txt")

        def write_func():
            with open(output_file, "w") as f:
                f.write("plugin output")

        result = executor.execute(write_func)
        self.assertTrue(result.success)
        self.assertTrue(os.path.exists(output_file))

    def test_write_denied_path(self):
        """Test writing to a non-writable path is denied."""
        writable_dir = os.path.join(self.tmp_dir, "writable")
        os.makedirs(writable_dir)
        deny_dir = os.path.join(self.tmp_dir, "readonly")
        os.makedirs(deny_dir)

        config = SandboxConfig(
            allowed_paths=[writable_dir, deny_dir],
            writable_paths=[writable_dir],
        )
        executor = SandboxExecutor(config, "test_plugin")

        deny_file = os.path.join(deny_dir, "cannot_write.txt")

        def write_func():
            with open(deny_file, "w") as f:
                f.write("should fail")

        result = executor.execute(write_func)
        self.assertFalse(result.success)
        self.assertIsInstance(result.error, PermissionDeniedError)

    def test_check_filesystem_access(self):
        """Test the check_filesystem_access method."""
        writable_dir = os.path.join(self.tmp_dir, "writable")
        os.makedirs(writable_dir)

        config = SandboxConfig(
            allowed_paths=[writable_dir],
            writable_paths=[writable_dir],
        )
        executor = SandboxExecutor(config, "test_plugin")

        self.assertTrue(executor.check_filesystem_access(writable_dir, "r"))
        self.assertTrue(executor.check_filesystem_access(writable_dir, "w"))
        self.assertFalse(executor.check_filesystem_access("/etc/passwd", "r"))


class TestSandboxExecutorNetwork(unittest.TestCase):
    """Tests for network access control."""

    def test_network_allowed(self):
        """Test network check when network is allowed."""
        config = SandboxConfig(
            allow_network=True,
            allowed_hosts=["localhost", "api.example.com"],
            allowed_ports={80, 443},
        )
        executor = SandboxExecutor(config, "test_plugin")

        self.assertTrue(executor.check_network_access("localhost", 80))
        self.assertTrue(executor.check_network_access("api.example.com", 443))

    def test_network_denied_by_default(self):
        """Test that network is denied by default."""
        config = SandboxConfig()
        executor = SandboxExecutor(config, "test_plugin")

        self.assertFalse(executor.check_network_access("localhost", 80))

    def test_network_host_not_allowed(self):
        """Test that unknown hosts are denied."""
        config = SandboxConfig(
            allow_network=True,
            allowed_hosts=["localhost"],
        )
        executor = SandboxExecutor(config, "test_plugin")

        self.assertFalse(executor.check_network_access("evil.com", 80))

    def test_network_port_not_allowed(self):
        """Test that unknown ports are denied."""
        config = SandboxConfig(
            allow_network=True,
            allowed_hosts=["localhost"],
            allowed_ports={443},
        )
        executor = SandboxExecutor(config, "test_plugin")

        self.assertFalse(executor.check_network_access("localhost", 22))


class TestSandboxExecutorWorkspace(unittest.TestCase):
    """Tests for workspace isolation."""

    def tearDown(self):
        import shutil
        # Clean up any leftover workspaces
        for d in os.listdir(tempfile.gettempdir()):
            if d.startswith("sandbox_test"):
                path = os.path.join(tempfile.gettempdir(), d)
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)

    def test_create_isolated_workspace(self):
        """Test creating an isolated workspace."""
        config = SandboxConfig()
        executor = SandboxExecutor(config, "test_plugin")

        workspace = executor.create_isolated_workspace()
        self.assertTrue(os.path.isdir(workspace))
        self.assertIn(workspace, config.allowed_paths)
        self.assertIn(workspace, config.writable_paths)

        executor.cleanup_workspace()
        self.assertFalse(os.path.exists(workspace))


class TestSandboxExecutorErrorHandling(unittest.TestCase):
    """Tests for error handling in the sandbox."""

    def test_restricted_import_in_sandbox(self):
        """Test that importing a restricted module in sandbox errors."""
        config = SandboxConfig(
            allowed_modules={"json"},
            blocked_modules={"some_blocked_lib"},
        )
        executor = SandboxExecutor(config, "test_plugin")

        def import_restricted():
            # Try importing something not in allowed_modules
            import this_module_does_not_exist  # noqa: F401
            return "imported"

        result = executor.execute(import_restricted)
        self.assertFalse(result.success)
        self.assertIsInstance(result.error, RestrictedImportError)

    def test_sandbox_result_warnings(self):
        """Test that SandboxResult captures warnings properly."""
        config = SandboxConfig()
        executor = SandboxExecutor(config, "test_plugin")

        result = executor.execute(lambda: 42)
        self.assertIsInstance(result.warnings, list)
        self.assertTrue(result.success)


class TestSandboxExecutorProperties(unittest.TestCase):
    """Tests for property accessors."""

    def test_config_property(self):
        """Test config property."""
        config = SandboxConfig(max_memory_mb=512)
        executor = SandboxExecutor(config, "myplugin")
        self.assertEqual(executor.config.max_memory_mb, 512)

    def test_plugin_name_property(self):
        """Test plugin_name property."""
        executor = SandboxExecutor(SandboxConfig(), "special_plugin")
        self.assertEqual(executor.plugin_name, "special_plugin")


if __name__ == "__main__":
    unittest.main()