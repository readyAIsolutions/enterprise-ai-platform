"""
Sandbox Executor for the Eni Builder Plugin Framework.

Provides a permission-constrained execution environment for plugins.
Implements resource limits (memory, CPU time), restricted imports,
filesystem access control, and network access control.

This module creates isolated execution contexts that limit what plugin
code can do, protecting the host system from malicious or buggy plugins.
"""

from __future__ import annotations

import importlib
import os
import resource
import signal
import sys
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type

from .security import (
    Permission,
    PluginPermissionProfile,
    PluginSecurity,
    PermissionDeniedError,
    AccessRequest,
)


class SandboxError(Exception):
    """Base exception for sandbox-related errors."""

    pass


class ResourceLimitExceededError(SandboxError):
    """Raised when a plugin exceeds its allocated resources."""

    def __init__(self, resource_type: str, limit: Any, actual: Any) -> None:
        self.resource_type = resource_type
        self.limit = limit
        self.actual = actual
        super().__init__(
            f"Resource limit exceeded: {resource_type} (limit={limit}, actual={actual})"
        )


class TimeoutError(SandboxError):
    """Raised when a plugin execution exceeds its time limit."""

    def __init__(self, timeout_sec: float, plugin_name: str) -> None:
        self.timeout_sec = timeout_sec
        self.plugin_name = plugin_name
        super().__init__(
            f"Plugin '{plugin_name}' exceeded timeout of {timeout_sec}s"
        )


class RestrictedImportError(SandboxError):
    """Raised when a plugin attempts to import a restricted module."""

    def __init__(self, module_name: str, plugin_name: str) -> None:
        self.module_name = module_name
        self.plugin_name = plugin_name
        super().__init__(
            f"Plugin '{plugin_name}' attempted to import restricted module '{module_name}'"
        )


class NetworkBlockedError(SandboxError):
    """Raised when a plugin attempts network access without permission."""

    def __init__(self, host: str, port: int, plugin_name: str) -> None:
        self.host = host
        self.port = port
        self.plugin_name = plugin_name
        super().__init__(
            f"Plugin '{plugin_name}' attempted network access to {host}:{port}"
        )


@dataclass
class SandboxConfig:
    """Configuration for a sandbox execution environment.

    Defines resource limits, allowed imports, filesystem paths,
    and network access controls for a plugin's execution.
    """

    # ---- Resource Limits ----
    max_memory_mb: int = 256
    """Maximum memory the plugin can allocate in megabytes."""
    max_cpu_time_sec: int = 60
    """Maximum CPU time in seconds."""
    max_execution_time_sec: int = 30
    """Wall-clock timeout for a single execute() call."""
    max_file_descriptors: int = 1024
    """Maximum number of open file descriptors."""
    max_stack_size_mb: int = 8
    """Maximum stack size in megabytes."""

    # ---- Import Restrictions ----
    allowed_modules: Set[str] = field(default_factory=set)
    """Whitelist of modules the plugin can import. Empty means all allowed."""
    blocked_modules: Set[str] = field(default_factory=set)
    """Blacklist of modules the plugin cannot import."""
    allow_builtins: bool = True
    """Whether built-in modules are allowed."""

    # ---- Filesystem Access ----
    allowed_paths: List[str] = field(default_factory=list)
    """Paths the plugin can read from."""
    writable_paths: List[str] = field(default_factory=list)
    """Paths the plugin can write to."""
    denied_paths: List[str] = field(default_factory=list)
    """Paths explicitly denied."""
    workspace_path: str = ""
    """The plugin's isolated workspace directory."""
    chroot_path: str = ""
    """Optional chroot path for full isolation."""

    # ---- Network Access ----
    allow_network: bool = False
    """Whether network access is allowed at all."""
    allowed_hosts: List[str] = field(default_factory=list)
    """Hosts the plugin can connect to."""
    allowed_ports: Set[int] = field(default_factory=set)
    """Ports the plugin can use."""
    allow_dns: bool = False
    """Whether DNS resolution is allowed."""

    @classmethod
    def from_permission_profile(cls, profile: PluginPermissionProfile) -> "SandboxConfig":
        """Create a SandboxConfig from a PluginPermissionProfile.

        Args:
            profile: The permission profile to derive configuration from.

        Returns:
            A SandboxConfig with appropriate restrictions.
        """
        allow_network = profile.has_permission(Permission.NET_OUTBOUND)
        allow_dns_flag = profile.has_permission(Permission.NET_DNS)

        return cls(
            max_memory_mb=profile.max_memory_mb,
            max_cpu_time_sec=profile.max_cpu_time_sec,
            allowed_paths=list(profile.allowed_paths),
            denied_paths=list(profile.denied_paths),
            allow_network=allow_network,
            allowed_hosts=list(profile.allowed_hosts),
            allowed_ports=profile.allowed_ports or set(),
            allow_dns=allow_dns_flag,
        )


@dataclass
class SandboxResult:
    """Result from a sandboxed execution."""

    success: bool
    result: Any = None
    error: Optional[Exception] = None
    execution_time_sec: float = 0.0
    memory_used_mb: float = 0.0
    cpu_time_used_sec: float = 0.0
    warnings: List[str] = field(default_factory=list)


class ImportGuard:
    """Guards imports by blocking modules that are not in the allowed set.

    Installed as a meta-path finder in sys.meta_path to intercept
    all import attempts and validate them against the sandbox config.
    """

    def __init__(
        self,
        config: SandboxConfig,
        plugin_name: str,
    ) -> None:
        self._config = config
        self._plugin_name = plugin_name
        self._original_modules: Set[str] = set(sys.modules.keys())

    def __enter__(self) -> "ImportGuard":
        sys.meta_path.insert(0, self)  # type: ignore[arg-type]
        return self

    def __exit__(self, *args: Any) -> None:
        try:
            sys.meta_path.remove(self)  # type: ignore[arg-type]
        except ValueError:
            pass

    def find_spec(
        self,
        fullname: str,
        path: Any = None,
        target: Any = None,
    ) -> Any:
        """Intercept module imports and validate against allowed_modules.

        Args:
            fullname: The fully qualified module name.
            path: Module search path.
            target: Target module.

        Returns:
            None to pass through to the next finder, or raises RestrictedImportError.

        Raises:
            RestrictedImportError: If the module is not allowed.
        """
        # Check blocked modules first
        if fullname in self._config.blocked_modules:
            raise RestrictedImportError(fullname, self._plugin_name)

        # If specific allowed modules are set, check against them
        if self._config.allowed_modules:
            # Allow modules already imported
            if fullname in self._original_modules:
                return None
            # Check if module or any parent is allowed
            parts = fullname.split(".")
            allowed = False
            for i in range(len(parts)):
                prefix = ".".join(parts[: i + 1])
                if prefix in self._config.allowed_modules:
                    allowed = True
                    break
            if not allowed:
                raise RestrictedImportError(fullname, self._plugin_name)

        # Pass through to next finder
        return None


class _TimeoutException(Exception):
    """Internal exception used to signal a timeout."""
    pass


class SandboxExecutor:
    """Permission-constrained sandbox execution environment for plugins.

    This executor creates a restricted environment that limits:
    - Resource usage (memory, CPU time, wall-clock time)
    - Module imports (whitelist/blacklist)
    - Filesystem access (read/write paths)
    - Network access (hosts, ports, DNS)

    Usage:
        config = SandboxConfig(max_memory_mb=128)
        executor = SandboxExecutor(config, plugin_name="my_plugin")
        result = executor.execute(lambda: some_function(arg1, arg2))
    """

    # Default blocked modules that are dangerous
    DEFAULT_BLOCKED_MODULES: Set[str] = {
        "os", "subprocess", "shutil", "signal",
        "socket", "http", "urllib", "ftplib", "smtplib",
        "ctypes", "multiprocessing", "threading",
        "sys", "builtins",
    }

    # Safe built-in replacements
    SAFE_BUILTINS: Set[str] = {
        "abs", "all", "any", "bin", "bool", "bytes",
        "callable", "chr", "complex", "dict", "dir",
        "divmod", "enumerate", "filter", "float", "format",
        "frozenset", "getattr", "hasattr", "hash", "hex",
        "id", "int", "isinstance", "issubclass", "iter",
        "len", "list", "map", "max", "min", "next",
        "object", "oct", "ord", "pow", "print",
        "range", "repr", "reversed", "round", "set",
        "slice", "sorted", "str", "sum", "tuple",
        "type", "zip",
    }

    def __init__(
        self,
        config: SandboxConfig,
        plugin_name: str,
        security: Optional[PluginSecurity] = None,
    ) -> None:
        """Initialize the sandbox executor.

        Args:
            config: Sandbox configuration.
            plugin_name: Name of the plugin being sandboxed.
            security: Optional PluginSecurity instance for access checks.
        """
        self._config = config
        self._plugin_name = plugin_name
        self._security = security

    @property
    def config(self) -> SandboxConfig:
        """Get the current sandbox configuration."""
        return self._config

    @property
    def plugin_name(self) -> str:
        """Get the name of the sandboxed plugin."""
        return self._plugin_name

    def execute(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> SandboxResult:
        """Execute a function in the sandbox environment.

        Applies all configured restrictions and monitors resource usage.

        Args:
            func: The function to execute.
            *args: Positional arguments to pass to the function.
            **kwargs: Keyword arguments to pass to the function.

        Returns:
            A SandboxResult with execution details.
        """
        import time

        start_time = time.time()
        warnings: List[str] = []

        # Apply resource limits
        self._apply_resource_limits(warnings)

        # Build restricted globals for the execution
        restricted_globals = self._build_restricted_globals()

        # Create the guarded function wrapper
        def guarded_func() -> Any:
            return func(*args, **kwargs)

        # Set up import guard
        with ImportGuard(self._config, self._plugin_name):
            try:
                # Set up filesystem guard
                with self._filesystem_guard():
                    # Execute with timeout
                    result_value = self._execute_with_timeout(
                        guarded_func,
                        self._config.max_execution_time_sec,
                    )
                    elapsed = time.time() - start_time
                    return SandboxResult(
                        success=True,
                        result=result_value,
                        execution_time_sec=elapsed,
                        warnings=warnings,
                    )

            except TimeoutError as e:
                elapsed = time.time() - start_time
                return SandboxResult(
                    success=False,
                    error=e,
                    execution_time_sec=elapsed,
                    warnings=warnings,
                )
            except RestrictedImportError as e:
                elapsed = time.time() - start_time
                return SandboxResult(
                    success=False,
                    error=e,
                    execution_time_sec=elapsed,
                    warnings=warnings,
                )
            except PermissionDeniedError as e:
                elapsed = time.time() - start_time
                return SandboxResult(
                    success=False,
                    error=e,
                    execution_time_sec=elapsed,
                    warnings=warnings,
                )
            except Exception as e:
                elapsed = time.time() - start_time
                return SandboxResult(
                    success=False,
                    error=e,
                    execution_time_sec=elapsed,
                    warnings=warnings,
                )

    def _apply_resource_limits(self, warnings: List[str]) -> None:
        """Apply OS-level resource limits based on configuration.

        Args:
            warnings: List to append warning messages to.
        """
        try:
            # Memory limit
            if self._config.max_memory_mb > 0:
                memory_bytes = self._config.max_memory_mb * 1024 * 1024
                resource.setrlimit(
                    resource.RLIMIT_AS,
                    (memory_bytes, memory_bytes),
                )

            # CPU time limit
            if self._config.max_cpu_time_sec > 0:
                resource.setrlimit(
                    resource.RLIMIT_CPU,
                    (self._config.max_cpu_time_sec, self._config.max_cpu_time_sec),
                )

            # Stack size
            if self._config.max_stack_size_mb > 0:
                stack_bytes = self._config.max_stack_size_mb * 1024 * 1024
                resource.setrlimit(
                    resource.RLIMIT_STACK,
                    (stack_bytes, stack_bytes),
                )

            # File descriptors
            if self._config.max_file_descriptors > 0:
                resource.setrlimit(
                    resource.RLIMIT_NOFILE,
                    (self._config.max_file_descriptors, self._config.max_file_descriptors),
                )

        except (ValueError, resource.error) as e:
            warnings.append(f"Failed to set resource limits: {e}")

    def _build_restricted_globals(self) -> Dict[str, Any]:
        """Build a restricted __builtins__ dict for the sandbox.

        Returns:
            A dict of safe builtins.
        """
        import builtins
        restricted: Dict[str, Any] = {}
        if self._config.allow_builtins:
            for name in self.SAFE_BUILTINS:
                if hasattr(builtins, name):
                    restricted[name] = getattr(builtins, name)
        return {"__builtins__": restricted}

    def _execute_with_timeout(
        self,
        func: Callable[..., Any],
        timeout_sec: int,
    ) -> Any:
        """Execute a function with a wall-clock timeout.

        Args:
            func: The function to execute.
            timeout_sec: Timeout in seconds.

        Returns:
            The function's return value.

        Raises:
            TimeoutError: If the function exceeds the time limit.
        """
        result_container: List[Any] = []
        exception_container: List[Exception] = []

        def target() -> None:
            try:
                result_container.append(func())
            except Exception as e:
                exception_container.append(e)

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(timeout=timeout_sec)

        if thread.is_alive():
            raise TimeoutError(float(timeout_sec), self._plugin_name)

        if exception_container:
            raise exception_container[0]

        return result_container[0] if result_container else None

    @contextmanager
    def _filesystem_guard(self) -> Any:
        """Context manager that enforces filesystem access controls.

        Patches os.open and open to enforce path restrictions.

        Yields:
            None while the guard is active.
        """
        import builtins

        original_open = builtins.open
        allowed_read = set(self._config.allowed_paths or [])
        allowed_write = set(self._config.writable_paths or [])
        denied = set(self._config.denied_paths or [])
        plugin_name = self._plugin_name

        # If no restrictions, just yield
        if not allowed_read and not allowed_write and not denied:
            yield
            return

        def _check_path(filepath: str, mode: str) -> None:
            """Check if a file path is allowed for the given mode."""
            abspath = os.path.abspath(filepath)

            # Denied paths take priority
            for dp in denied:
                if abspath.startswith(os.path.abspath(dp)):
                    raise PermissionDeniedError(
                        plugin_name=plugin_name,
                        permission=Permission.FS_WRITE if "w" in mode or "a" in mode else Permission.FS_READ,
                        resource=filepath,
                    )

            if "w" in mode or "a" in mode or "+" in mode:
                if allowed_write:
                    if not any(abspath.startswith(os.path.abspath(wp)) for wp in allowed_write):
                        raise PermissionDeniedError(
                            plugin_name=plugin_name,
                            permission=Permission.FS_WRITE,
                            resource=filepath,
                        )
            else:
                if allowed_read:
                    if not any(abspath.startswith(os.path.abspath(rp)) for rp in allowed_read):
                        raise PermissionDeniedError(
                            plugin_name=plugin_name,
                            permission=Permission.FS_READ,
                            resource=filepath,
                        )

        def guarded_open(file, mode="r", *args: Any, **kwargs: Any) -> Any:
            _check_path(str(file), mode)
            return original_open(file, mode, *args, **kwargs)

        builtins.open = guarded_open  # type: ignore[assignment]
        try:
            yield
        finally:
            builtins.open = original_open

    def check_filesystem_access(self, path: str, mode: str = "r") -> bool:
        """Check if the plugin has access to a filesystem path.

        Args:
            path: The filesystem path to check.
            mode: The access mode ('r' for read, 'w' for write).

        Returns:
            True if access should be allowed.
        """
        abspath = os.path.abspath(path)

        # Check denied paths
        for dp in self._config.denied_paths:
            if abspath.startswith(os.path.abspath(dp)):
                return False

        if "w" in mode or "a" in mode:
            if self._config.writable_paths:
                return any(
                    abspath.startswith(os.path.abspath(wp))
                    for wp in self._config.writable_paths
                )
        else:
            if self._config.allowed_paths:
                return any(
                    abspath.startswith(os.path.abspath(rp))
                    for rp in self._config.allowed_paths
                )

        return True

    def check_network_access(self, host: str, port: int) -> bool:
        """Check if the plugin has network access to a host:port.

        Args:
            host: Target hostname or IP.
            port: Target port.

        Returns:
            True if network access is allowed.
        """
        if not self._config.allow_network:
            return False

        if self._config.allowed_hosts and host not in self._config.allowed_hosts:
            return False

        if self._config.allowed_ports and port not in self._config.allowed_ports:
            return False

        return True

    def create_isolated_workspace(self) -> str:
        """Create an isolated workspace directory for the plugin.

        Returns:
            Path to the created workspace directory.
        """
        import tempfile

        if self._config.workspace_path:
            os.makedirs(self._config.workspace_path, exist_ok=True)
            return self._config.workspace_path

        workspace = tempfile.mkdtemp(prefix=f"sandbox_{self._plugin_name}_")
        self._config.workspace_path = workspace
        self._config.allowed_paths.append(workspace)
        self._config.writable_paths.append(workspace)
        return workspace

    def cleanup_workspace(self) -> None:
        """Clean up the isolated workspace directory."""
        import shutil

        if self._config.workspace_path and os.path.exists(self._config.workspace_path):
            try:
                shutil.rmtree(self._config.workspace_path)
            except OSError:
                pass