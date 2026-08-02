"""
Eni Builder Plugin Framework.

A comprehensive enterprise plugin system supporting:
- Plugin lifecycle management (load, init, start, stop, unload)
- Dependency resolution with topological sorting
- Sandboxed execution with resource limits and access controls
- Security model with granular permissions and signing stubs
- Capability-based plugin discovery and registry
- Event hooks for inter-plugin communication

Usage:
    from enterprise.foundation.plugin_framework import (
        PluginManager,
        PluginRegistry,
        PluginSecurity,
        PluginBase,
        PluginMetadata,
        PluginVersion,
        PluginCapability,
        PluginState,
        SandboxConfig,
        SandboxExecutor,
    )

    registry = PluginRegistry()
    security = PluginSecurity()
    manager = PluginManager(registry, security)

    manager.register(MyPluginClass)
    manager.load_all()
    manager.start_all()

    result = manager.execute_capability("search", query="hello")
"""

from enterprise.foundation.plugin_framework.interface import (
    PluginBase,
    PluginCapability,
    PluginMetadata,
    PluginState,
    PluginVersion,
    EventCallback,
    PluginConstructor,
    PluginInterfaceError,
    IncompatibleVersionError,
)

from enterprise.foundation.plugin_framework.registry import (
    PluginRegistry,
    RegistryEntry,
    CapabilitySearchResult,
    CompatibilityRecord,
)

from enterprise.foundation.plugin_framework.security import (
    PluginSecurity,
    PluginPermissionProfile,
    PluginSignature,
    Permission,
    SigningStatus,
    AccessRequest,
    AccessDecision,
    PluginSecurityError,
    PermissionDeniedError,
)

from enterprise.foundation.plugin_framework.sandbox import (
    SandboxConfig,
    SandboxExecutor,
    SandboxResult,
    ImportGuard,
    SandboxError,
    ResourceLimitExceededError,
    TimeoutError,
    RestrictedImportError,
    NetworkBlockedError,
)

from enterprise.foundation.plugin_framework.manager import (
    PluginManager,
    LoadResult,
    LifecycleEvent,
    DependencyNode,
    PluginManagerError,
    DependencyError,
    LifecycleError,
)

__all__ = [
    # Interface
    "PluginBase",
    "PluginCapability",
    "PluginMetadata",
    "PluginState",
    "PluginVersion",
    "EventCallback",
    "PluginConstructor",
    "PluginInterfaceError",
    "IncompatibleVersionError",
    # Registry
    "PluginRegistry",
    "RegistryEntry",
    "CapabilitySearchResult",
    "CompatibilityRecord",
    # Security
    "PluginSecurity",
    "PluginPermissionProfile",
    "PluginSignature",
    "Permission",
    "SigningStatus",
    "AccessRequest",
    "AccessDecision",
    "PluginSecurityError",
    "PermissionDeniedError",
    # Sandbox
    "SandboxConfig",
    "SandboxExecutor",
    "SandboxResult",
    "ImportGuard",
    "SandboxError",
    "ResourceLimitExceededError",
    "TimeoutError",
    "RestrictedImportError",
    "NetworkBlockedError",
    # Manager
    "PluginManager",
    "LoadResult",
    "LifecycleEvent",
    "DependencyNode",
    "PluginManagerError",
    "DependencyError",
    "LifecycleError",
]

__version__ = "1.0.0"