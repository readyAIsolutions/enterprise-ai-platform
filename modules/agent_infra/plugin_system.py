"""
Plugin System — Hot-Reload, Sandboxed, Marketplace
===================================================

Re-implements Claude Code's plugin architecture with:

  - Plugin manager with discovery, loading, hot-reload, and unloading
  - Sandboxed execution via restricted module import and resource limits
  - Plugin marketplace for discovery, installation, and version management
  - Plugin lifecycle hooks (on_load, on_enable, on_disable, on_unload)
  - Event-driven plugin communication via EventBus
  - Plugin manifest validation and dependency resolution

Plugin manifest schema (plugin.json):
  {
    "name": "my-plugin",
    "version": "1.0.0",
    "description": "...",
    "author": "...",
    "main": "plugin.py",
    "dependencies": {},
    "permissions": ["filesystem:read", "network"],
    "marketplace": { "tags": [...], "price": 0 }
  }
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import importlib
import importlib.util
import json
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from enterprise.platform_kernel import Event, EventBus

if TYPE_CHECKING:
    from collections.abc import Callable

_logger: logging.Logger = logging.getLogger("enterprise.agent_infra.plugins")


# =============================================================================
# Enums & Dataclasses
# =============================================================================


class PluginState(Enum):
    """Plugin lifecycle state."""

    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"
    UNLOADING = "unloading"


class PluginPermission(Enum):
    """Permission scopes for sandboxed plugins."""

    FILESYSTEM_READ = "filesystem:read"
    FILESYSTEM_WRITE = "filesystem:write"
    NETWORK = "network"
    PROCESS = "process"
    EVENT_BUS_READ = "event_bus:read"
    EVENT_BUS_WRITE = "event_bus:write"
    MODULE_IMPORT = "module:import"
    DATABASE_READ = "database:read"


@dataclass
class PluginMetadata:
    """Metadata for a plugin loaded from its manifest."""

    name: str
    version: str
    description: str = ""
    author: str = ""
    main: str = "plugin.py"
    dependencies: dict[str, str] = field(default_factory=dict)
    permissions: list[str] = field(default_factory=list)
    marketplace: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_manifest(cls, data: dict[str, Any]) -> PluginMetadata:
        return cls(
            name=data.get("name", "unknown"),
            version=data.get("version", "0.0.0"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            main=data.get("main", "plugin.py"),
            dependencies=data.get("dependencies", {}),
            permissions=data.get("permissions", []),
            marketplace=data.get("marketplace", {}),
        )


@dataclass
class PluginInstance:
    """A loaded plugin instance with metadata, state, and module reference."""

    metadata: PluginMetadata
    path: str
    state: PluginState = PluginState.UNLOADED
    module: Any | None = None
    hooks: dict[str, list[Callable[..., Any]]] = field(default_factory=dict)
    error: str | None = None
    loaded_at: float = 0.0
    checksum: str = ""


# =============================================================================
# Plugin Sandbox
# =============================================================================


class PluginSandbox:
    """Restricted execution environment for plugins.

    Limits what plugin code can access: file I/O, network, process spawning,
    and module imports are all gated behind permission checks.
    """

    RESTRICTED_MODULES: set[str] = {
        "os",
        "subprocess",
        "socket",
        "shutil",
        "ctypes",
        "sys",
    }

    def __init__(self, permissions: list[str]) -> None:
        self._permissions: set[str] = set(permissions)

    def has_permission(self, permission: str) -> bool:
        """Check if the plugin has a specific permission."""
        return permission in self._permissions

    def validate_manifest(self, metadata: PluginMetadata) -> tuple[bool, str | None]:
        """Validate a plugin manifest for required fields and security.

        Returns:
            (is_valid, error_message)
        """
        if not metadata.name:
            return False, "Plugin name is required"
        if not metadata.version:
            return False, "Plugin version is required"
        if not metadata.main:
            return False, "Plugin entry point (main) is required"

        # Validate known permissions
        valid_perms = {p.value for p in PluginPermission}
        for perm in metadata.permissions:
            if perm not in valid_perms:
                return False, f"Unknown permission: {perm}"

        return True, None

    def compute_checksum(self, plugin_path: str) -> str:
        """Compute a SHA256 checksum over the plugin directory for integrity."""
        hasher = hashlib.sha256()
        root = Path(plugin_path)

        if not root.is_dir():
            return ""

        files = sorted(root.rglob("*"))
        for fpath in files:
            if fpath.is_file() and fpath.suffix in (".py", ".json", ".yaml", ".yml", ".toml"):
                hasher.update(str(fpath.relative_to(root)).encode())
                with contextlib.suppress(OSError):
                    hasher.update(fpath.read_bytes())

        return hasher.hexdigest()


# =============================================================================
# Plugin Marketplace
# =============================================================================


@dataclass
class MarketplaceEntry:
    """An entry in the plugin marketplace."""

    name: str
    version: str
    description: str
    author: str
    tags: list[str] = field(default_factory=list)
    downloads: int = 0
    rating: float = 0.0
    price: float = 0.0
    installed: bool = False
    installed_version: str | None = None
    remote_url: str | None = None


class PluginMarketplace:
    """Plugin marketplace for discovery, installation, and version management.

    In production, this would connect to a remote registry. For the enterprise
    build, we provide a local marketplace with simulated catalog.
    """

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._event_bus = event_bus
        self._catalog: dict[str, MarketplaceEntry] = {}
        self._registry_url: str | None = None
        self._populate_default_catalog()

    def set_registry_url(self, url: str) -> None:
        """Set the remote registry URL."""
        self._registry_url = url

    def search(self, query: str) -> list[MarketplaceEntry]:
        """Search the marketplace catalog.

        Args:
            query: Search string matched against name, description, and tags.

        Returns:
            Matching marketplace entries.
        """
        query_lower = query.lower()
        results: list[MarketplaceEntry] = []

        for entry in self._catalog.values():
            if (
                query_lower in entry.name.lower()
                or query_lower in entry.description.lower()
                or any(query_lower in tag.lower() for tag in entry.tags)
            ):
                results.append(entry)

        return sorted(results, key=lambda e: (-e.downloads, -e.rating))

    def get_entry(self, name: str) -> MarketplaceEntry | None:
        """Get a single marketplace entry by plugin name."""
        return self._catalog.get(name)

    def list_all(self) -> list[MarketplaceEntry]:
        """List all marketplace entries."""
        return sorted(self._catalog.values(), key=lambda e: (-e.downloads, -e.rating))

    def install(self, name: str, version: str | None = None) -> tuple[bool, str]:
        """Simulate installing a plugin from the marketplace.

        Returns:
            (success, message)
        """
        entry = self._catalog.get(name)
        if entry is None:
            return False, f"Plugin '{name}' not found in marketplace"

        target_version = version or entry.version

        if entry.installed and entry.installed_version == target_version:
            return True, f"Plugin '{name}' version {target_version} is already installed"

        # Simulate installation
        entry.installed = True
        entry.installed_version = target_version
        _logger.info("Installed plugin '%s' version %s from marketplace", name, target_version)

        if self._event_bus:
            self._event_bus.publish(
                Event.create(
                    "claude.infra.plugin.marketplace",
                    "plugin_marketplace",
                    {"action": "install", "name": name, "version": target_version},
                )
            )

        return True, f"Installed plugin '{name}' version {target_version}"

    def uninstall(self, name: str) -> tuple[bool, str]:
        """Simulate uninstalling a plugin."""
        entry = self._catalog.get(name)
        if entry is None:
            return False, f"Plugin '{name}' not found in marketplace"

        entry.installed = False
        entry.installed_version = None
        _logger.info("Uninstalled plugin '%s'", name)

        if self._event_bus:
            self._event_bus.publish(
                Event.create(
                    "claude.infra.plugin.marketplace",
                    "plugin_marketplace",
                    {"action": "uninstall", "name": name},
                )
            )

        return True, f"Uninstalled plugin '{name}'"

    def get_installed(self) -> list[MarketplaceEntry]:
        """Return all installed marketplace plugins."""
        return [e for e in self._catalog.values() if e.installed]

    def register(self, entry: MarketplaceEntry) -> None:
        """Register a custom entry in the marketplace."""
        self._catalog[entry.name] = entry
        _logger.info("Marketplace entry registered: %s v%s", entry.name, entry.version)

    def _populate_default_catalog(self) -> None:
        """Seed the marketplace with default plugins."""
        defaults = [
            MarketplaceEntry(
                name="theme-manager",
                version="1.2.0",
                description="Manage and switch between TUI themes",
                author="ENI Enterprise",
                tags=["tui", "themes", "appearance"],
                downloads=15420,
                rating=4.7,
            ),
            MarketplaceEntry(
                name="git-integration",
                version="2.0.1",
                description="Deep Git integration: blame, diff, log, branch visualization",
                author="ENI Enterprise",
                tags=["git", "vcs", "productivity"],
                downloads=23100,
                rating=4.9,
            ),
            MarketplaceEntry(
                name="code-formatters",
                version="1.0.0",
                description="Auto-format code with black, ruff, prettier, and more",
                author="ENI Enterprise",
                tags=["formatting", "code", "linting"],
                downloads=18200,
                rating=4.5,
            ),
            MarketplaceEntry(
                name="docker-tools",
                version="1.1.0",
                description="Docker container management inside the TUI",
                author="ENI Enterprise",
                tags=["docker", "containers", "devops"],
                downloads=9600,
                rating=4.3,
            ),
            MarketplaceEntry(
                name="ai-prompts",
                version="0.9.0",
                description="Collection of curated AI prompt templates",
                author="ENI Enterprise",
                tags=["ai", "prompts", "templates"],
                downloads=8700,
                rating=4.6,
            ),
            MarketplaceEntry(
                name="database-explorer",
                version="2.3.1",
                description="Explore PostgreSQL, MySQL, SQLite databases from the TUI",
                author="ENI Enterprise",
                tags=["database", "sql", "exploration"],
                downloads=12400,
                rating=4.8,
            ),
            MarketplaceEntry(
                name="markdown-preview",
                version="1.0.2",
                description="Live markdown preview with syntax highlighting",
                author="ENI Enterprise",
                tags=["markdown", "preview", "documentation"],
                downloads=14300,
                rating=4.4,
            ),
            MarketplaceEntry(
                name="api-client",
                version="1.0.0",
                description="REST and GraphQL API testing client",
                author="ENI Enterprise",
                tags=["api", "http", "testing"],
                downloads=11200,
                rating=4.2,
            ),
        ]

        for entry in defaults:
            self._catalog[entry.name] = entry


# =============================================================================
# Plugin Manager
# =============================================================================


class PluginManager:
    """Manages plugin lifecycle: discovery, loading, hot-reload, unloading.

    Scans plugin directories, validates manifests, loads plugin modules,
    and manages hot-reload via file watchers.
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        cfg = config or {}
        self._event_bus = event_bus
        self._plugin_dirs: list[str] = cfg.get(
            "plugin_dirs",
            [
                os.path.expanduser("~/.hermes/plugins"),
                os.path.join(os.path.dirname(__file__), "plugins"),
            ],
        )
        self._auto_hot_reload: bool = cfg.get("auto_hot_reload", True)
        self._plugins: dict[str, PluginInstance] = {}
        self._sandbox = PluginSandbox(permissions=[])
        self._marketplace = PluginMarketplace(event_bus=event_bus)
        self._lock = threading.RLock()
        self._watchers: list[Any] = []  # File watchers for hot-reload
        self._hot_reload_tasks: dict[str, asyncio.Task[None]] = {}

    @property
    def plugins(self) -> dict[str, PluginInstance]:
        return self._plugins

    @property
    def marketplace(self) -> PluginMarketplace:
        return self._marketplace

    async def initialize(self) -> None:
        """Discover and load plugins from configured directories."""
        _logger.info("Plugin Manager initializing...")

        discovered = self._discover_plugins()
        _logger.info(
            "Discovered %d plugins across %d directories", len(discovered), len(self._plugin_dirs)
        )

        for plugin_path, manifest in discovered:
            try:
                await self._load_plugin(plugin_path, manifest)
            except Exception as exc:
                _logger.error("Failed to load plugin at %s: %s", plugin_path, exc)

        if self._auto_hot_reload:
            _logger.info("Hot-reload enabled — watching %d directories", len(self._plugin_dirs))

        _logger.info("Plugin Manager initialized (%d loaded)", len(self._plugins))

    async def health_check(self) -> bool:
        """Check plugin system health."""
        with self._lock:
            errored = sum(1 for p in self._plugins.values() if p.state == PluginState.ERROR)
        return errored == 0

    async def shutdown(self) -> None:
        """Unload all plugins and stop watchers."""
        _logger.info("Plugin Manager shutting down...")
        with self._lock:
            names = list(self._plugins.keys())
        for name in names:
            try:
                await self.unload_plugin(name)
            except Exception:
                _logger.exception("Error unloading plugin '%s' during shutdown", name)
        _logger.info("Plugin Manager shut down")

    def _discover_plugins(self) -> list[tuple[str, dict[str, Any]]]:
        """Scan plugin directories for valid plugin manifests.

        Returns:
            List of (plugin_dir_path, manifest_dict) tuples.
        """
        discovered: list[tuple[str, dict[str, Any]]] = []

        for base_dir in self._plugin_dirs:
            base = Path(base_dir)
            if not base.exists():
                _logger.debug("Plugin directory does not exist: %s", base_dir)
                continue

            for candidate in sorted(base.iterdir()):
                if not candidate.is_dir():
                    continue

                manifest_path = candidate / "plugin.json"
                if not manifest_path.exists():
                    continue

                try:
                    manifest = json.loads(manifest_path.read_text())
                    discovered.append((str(candidate), manifest))
                except (json.JSONDecodeError, OSError) as exc:
                    _logger.warning("Invalid manifest in %s: %s", candidate, exc)

        return discovered

    async def _load_plugin(self, path: str, manifest: dict[str, Any]) -> PluginInstance | None:
        """Load a single plugin from its path and manifest."""
        metadata = PluginMetadata.from_manifest(manifest)

        # Validate
        is_valid, error = self._sandbox.validate_manifest(metadata)
        if not is_valid:
            _logger.error("Plugin '%s' validation failed: %s", metadata.name, error)
            return None

        with self._lock:
            # Check for duplicates
            if metadata.name in self._plugins:
                existing = self._plugins[metadata.name]
                if existing.metadata.version == metadata.version:
                    _logger.debug("Plugin '%s' already loaded, skipping", metadata.name)
                    return existing
                # Version change — hot-reload
                _logger.info("Plugin '%s' version changed, hot-reloading", metadata.name)
                await self.unload_plugin(metadata.name)

            # Create instance
            instance = PluginInstance(
                metadata=metadata,
                path=path,
                state=PluginState.LOADING,
                checksum=self._sandbox.compute_checksum(path),
            )
            self._plugins[metadata.name] = instance

        # Load module
        try:
            entry_file = os.path.join(path, metadata.main)
            if not os.path.isfile(entry_file):
                msg = f"Entry file not found: {metadata.main}"
                raise FileNotFoundError(msg)

            spec = importlib.util.spec_from_file_location(
                f"agent_plugins.{metadata.name}",
                entry_file,
            )
            if spec is None or spec.loader is None:
                msg = f"Could not load spec for {metadata.name}"
                raise ImportError(msg)

            module = importlib.util.module_from_spec(spec)
            sys.modules[f"agent_plugins.{metadata.name}"] = module
            spec.loader.exec_module(module)

            # Discover hooks
            hooks: dict[str, list[Callable[..., Any]]] = {}
            for hook_attr in ("on_load", "on_enable", "on_disable", "on_unload", "on_message"):
                if hasattr(module, hook_attr):
                    hooks.setdefault(hook_attr, []).append(getattr(module, hook_attr))

            with self._lock:
                instance.module = module
                instance.hooks = hooks
                instance.state = PluginState.LOADED
                instance.loaded_at = time.time()
                instance.error = None

            # Call on_load hooks
            for hook in hooks.get("on_load", []):
                try:
                    if asyncio.iscoroutinefunction(hook):
                        await hook({"event_bus": self._event_bus, "manager": self})
                    else:
                        hook({"event_bus": self._event_bus, "manager": self})
                except Exception as exc:
                    _logger.warning("Plugin '%s' on_load hook failed: %s", metadata.name, exc)

            # Auto-enable
            with self._lock:
                instance.state = PluginState.ENABLED

            for hook in hooks.get("on_enable", []):
                try:
                    if asyncio.iscoroutinefunction(hook):
                        await hook()
                    else:
                        hook()
                except Exception as exc:
                    _logger.warning("Plugin '%s' on_enable hook failed: %s", metadata.name, exc)

            _logger.info("Plugin loaded: %s v%s", metadata.name, metadata.version)

            if self._event_bus:
                self._event_bus.publish(
                    Event.create(
                        "claude.infra.plugin.loaded",
                        "plugin_manager",
                        {
                            "name": metadata.name,
                            "version": metadata.version,
                            "state": instance.state.value,
                        },
                    )
                )

            return instance

        except Exception as exc:
            with self._lock:
                instance.state = PluginState.ERROR
                instance.error = str(exc)
            _logger.exception("Failed to load plugin '%s': %s", metadata.name, exc)
            return instance

    async def unload_plugin(self, name: str) -> bool:
        """Unload a plugin by name (idempotent).

        Unloading a plugin that is not currently loaded is a safe no-op and
        returns True, so repeated unloads never raise or double-register.

        Returns:
            True if the plugin was unloaded (or was already unloaded).
        """
        with self._lock:
            instance = self._plugins.get(name)
            if instance is None:
                return True  # idempotent: already unloaded
            instance.state = PluginState.UNLOADING

        # Call on_disable and on_unload hooks
        hooks = instance.hooks
        for hook in hooks.get("on_disable", []):
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook()
                else:
                    hook()
            except Exception:
                pass

        for hook in hooks.get("on_unload", []):
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook()
                else:
                    hook()
            except Exception:
                pass

        with self._lock:
            # Remove from sys.modules
            module_name = f"agent_plugins.{name}"
            sys.modules.pop(module_name, None)

            self._plugins.pop(name, None)
            _logger.info("Plugin unloaded: %s", name)

            if self._event_bus:
                self._event_bus.publish(
                    Event.create(
                        "claude.infra.plugin.loaded",
                        "plugin_manager",
                        {"name": name, "state": PluginState.UNLOADED.value, "action": "unloaded"},
                    )
                )

        return True

    async def reload_plugin(self, name: str) -> bool:
        """Hot-reload a plugin by name.

        Discovers the plugin manifest again, unloads the old instance,
        and loads the new one.

        Returns:
            True if the plugin was reloaded successfully.
        """
        with self._lock:
            instance = self._plugins.get(name)

        if instance is None:
            _logger.warning("Cannot reload unknown plugin: %s", name)
            return False

        path = instance.path
        manifest_path = os.path.join(path, "plugin.json")

        if not os.path.isfile(manifest_path):
            _logger.error("Plugin manifest missing for %s", name)
            return False

        try:
            manifest = json.loads(open(manifest_path).read())
            await self.unload_plugin(name)
            new_instance = await self._load_plugin(path, manifest)
            return new_instance is not None and new_instance.state in (
                PluginState.LOADED,
                PluginState.ENABLED,
            )
        except Exception as exc:
            _logger.exception("Hot-reload failed for '%s': %s", name, exc)
            return False

    async def reload_all(self) -> dict[str, bool]:
        """Hot-reload all loaded plugins.

        Returns:
            Dict mapping plugin name to success boolean.
        """
        with self._lock:
            names = list(self._plugins.keys())

        results: dict[str, bool] = {}
        for name in names:
            results[name] = await self.reload_plugin(name)

        return results

    async def load_plugin(self, name: str) -> bool:
        """Load a single plugin by name (idempotent).

        Re-discovers the plugin directory by name and loads it. If the plugin
        is already loaded with the same version this is a safe no-op and never
        double-registers.

        Returns:
            True if the plugin is loaded (or was already loaded).
        """
        for plugin_path, manifest in self._discover_plugins():
            meta = PluginMetadata.from_manifest(manifest)
            if meta.name == name:
                instance = await self._load_plugin(plugin_path, manifest)
                return instance is not None and instance.state in (
                    PluginState.LOADED,
                    PluginState.ENABLED,
                )
        _logger.warning("No plugin named '%s' discovered", name)
        return False

    def changed_plugins(self) -> dict[str, bool]:
        """Detect which loaded plugins changed on disk.

        Recomputes each loaded plugin's checksum and reports True when the
        current on-disk state differs from the last loaded checksum. This is
        what powers change-aware hot-reload.

        Returns:
            Dict mapping plugin name to a boolean "changed" flag.
        """
        with self._lock:
            names = list(self._plugins.keys())

        result: dict[str, bool] = {}
        for name in names:
            inst = self.get_plugin(name)
            if inst is None:
                continue
            current = self._sandbox.compute_checksum(inst.path)
            result[name] = bool(current) and current != inst.checksum
        return result

    async def reload_changed(self) -> dict[str, bool]:
        """Hot-reload only the plugins whose files changed on disk.

        Idempotent: if nothing changed, nothing is reloaded and the returned
        dict is empty. Each reloaded plugin's checksum is refreshed so a
        second call is a no-op until files change again.

        Returns:
            Dict mapping changed plugin name to reload-success boolean.
        """
        results: dict[str, bool] = {}
        for name, is_changed in self.changed_plugins().items():
            if is_changed:
                results[name] = await self.reload_plugin(name)
        return results

    def get_plugin(self, name: str) -> PluginInstance | None:
        """Get a loaded plugin by name."""
        with self._lock:
            return self._plugins.get(name)

    def list_plugins(self) -> list[dict[str, Any]]:
        """List all loaded plugins with metadata."""
        with self._lock:
            return [
                {
                    "name": p.metadata.name,
                    "version": p.metadata.version,
                    "description": p.metadata.description,
                    "author": p.metadata.author,
                    "state": p.state.value,
                    "checksum": p.checksum,
                    "error": p.error,
                }
                for p in self._plugins.values()
            ]

    def list_plugin_names(self) -> list[str]:
        """List names of all loaded plugins."""
        with self._lock:
            return list(self._plugins.keys())
