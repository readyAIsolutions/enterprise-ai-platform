"""
Plugin Manager for the Eni Builder Plugin Framework.

Core orchestrator responsible for plugin lifecycle management:
registration, loading, initialization, starting, stopping, and unloading.
Handles dependency resolution between plugins and provides an event hook
system for inter-plugin communication.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type

from .interface import (
    PluginBase,
    PluginMetadata,
    PluginState,
    PluginVersion,
    EventCallback,
    PluginInterfaceError,
    IncompatibleVersionError,
)
from .registry import PluginRegistry, RegistryEntry
from .sandbox import SandboxConfig, SandboxExecutor
from .security import PluginSecurity, PluginPermissionProfile, Permission

logger = logging.getLogger(__name__)


@dataclass
class DependencyNode:
    """Node in the plugin dependency graph.

    Used for topological sorting during dependency resolution.
    """

    plugin_name: str
    metadata: PluginMetadata
    dependencies: List[str] = field(default_factory=list)
    dependents: List[str] = field(default_factory=list)
    """Plugins that depend on this one."""
    visited: bool = False
    in_stack: bool = False
    """For cycle detection during topological sort."""


@dataclass
class LifecycleEvent:
    """Records a lifecycle transition event for a plugin.

    Used for audit trails and debugging.
    """

    plugin_name: str
    from_state: PluginState
    to_state: PluginState
    timestamp: str = ""
    success: bool = True
    error: Optional[str] = None
    duration_ms: float = 0.0


@dataclass
class LoadResult:
    """Result of loading a plugin."""

    plugin_name: str
    success: bool
    instance: Optional[PluginBase] = None
    error: Optional[str] = None
    dependencies_resolved: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class PluginManagerError(Exception):
    """Base exception for plugin manager errors."""

    pass


class DependencyError(PluginManagerError):
    """Raised when plugin dependencies cannot be satisfied."""

    def __init__(
        self,
        plugin_name: str,
        missing_deps: List[str],
        cycle_deps: Optional[List[str]] = None,
    ) -> None:
        self.plugin_name = plugin_name
        self.missing_deps = missing_deps
        self.cycle_deps = cycle_deps or []
        msg = f"Plugin '{plugin_name}' has unsatisfied dependencies: {missing_deps}"
        if cycle_deps:
            msg += f" (dependency cycle: {cycle_deps})"
        super().__init__(msg)


class LifecycleError(PluginManagerError):
    """Raised when an invalid lifecycle transition is attempted."""

    def __init__(self, plugin_name: str, current: PluginState, attempted: str) -> None:
        self.plugin_name = plugin_name
        self.current_state = current
        self.attempted = attempted
        super().__init__(
            f"Plugin '{plugin_name}' in state {current.value} cannot transition to {attempted}"
        )


class PluginManager:
    """Central manager for plugin lifecycle and coordination.

    Responsibilities:
    - Plugin registration via the PluginRegistry
    - Lifecycle management (load, init, start, stop, unload)
    - Dependency resolution and topological loading
    - Event hooks for inter-plugin communication
    - Integration with security and sandbox systems

    Usage:
        registry = PluginRegistry()
        security = PluginSecurity()
        manager = PluginManager(registry, security)

        # Register plugins
        manager.register(MyPluginClass)

        # Load and start
        manager.load_all()
        manager.start_all()

        # Use plugins
        result = manager.execute_capability("search", query="hello")

        # Shutdown
        manager.stop_all()
        manager.unload_all()
    """

    # Valid lifecycle transitions for state machine
    VALID_TRANSITIONS: Dict[PluginState, Set[PluginState]] = {
        PluginState.REGISTERED: {PluginState.LOADED, PluginState.UNREGISTERED},
        PluginState.LOADED: {PluginState.INITIALIZED, PluginState.ERROR, PluginState.UNLOADED},
        PluginState.INITIALIZED: {PluginState.RUNNING, PluginState.ERROR, PluginState.UNLOADED},
        PluginState.RUNNING: {PluginState.STOPPING, PluginState.ERROR},
        PluginState.STOPPING: {PluginState.STOPPED, PluginState.ERROR},
        PluginState.STOPPED: {PluginState.RUNNING, PluginState.UNLOADED, PluginState.ERROR},
        PluginState.ERROR: {PluginState.REGISTERED},  # Recovery path
        PluginState.UNREGISTERED: {PluginState.REGISTERED},
        PluginState.UNLOADED: set(),  # Terminal state
    }

    def __init__(
        self,
        registry: Optional[PluginRegistry] = None,
        security: Optional[PluginSecurity] = None,
    ) -> None:
        """Initialize the PluginManager.

        Args:
            registry: PluginRegistry instance. Creates one if not provided.
            security: PluginSecurity instance. Creates one if not provided.
        """
        self._registry = registry or PluginRegistry()
        self._security = security or PluginSecurity()
        self._instances: Dict[str, PluginBase] = {}
        self._sandboxes: Dict[str, SandboxExecutor] = {}
        self._lifecycle_history: List[LifecycleEvent] = []

        # Event hooks: event_name -> list of (plugin_name, callback)
        self._event_hooks: Dict[str, List[Tuple[str, EventCallback]]] = defaultdict(list)

        # Global event listeners (not tied to a specific plugin)
        self._global_listeners: List[EventCallback] = []

    @property
    def registry(self) -> PluginRegistry:
        """Get the plugin registry."""
        return self._registry

    @property
    def security(self) -> PluginSecurity:
        """Get the security manager."""
        return self._security

    # ---- Registration ----

    def register(self, plugin_class: Type[PluginBase]) -> RegistryEntry:
        """Register a plugin class with the framework.

        Args:
            plugin_class: A class that subclasses PluginBase.

        Returns:
            The RegistryEntry for the registered plugin.
        """
        # Register with the registry
        entry = self._registry.register(plugin_class)

        # Create a default security profile
        self._security.register_profile(
            PluginPermissionProfile(plugin_name=entry.name)
        )

        logger.info(f"Registered plugin: {entry.name} v{entry.version}")
        self._emit_event("plugin:registered", {"plugin_name": entry.name})

        return entry

    def unregister(self, plugin_name: str) -> None:
        """Unregister a plugin, stopping and unloading it first if needed.

        Args:
            plugin_name: Name of the plugin to unregister.

        Raises:
            KeyError: If the plugin is not registered.
        """
        # Ensure plugin is stopped and unloaded
        state = self.get_plugin_state(plugin_name)
        if state in (PluginState.RUNNING, PluginState.INITIALIZED):
            self.stop(plugin_name)
        if state not in (PluginState.UNREGISTERED, PluginState.UNLOADED):
            self.unload(plugin_name)

        self._registry.unregister(plugin_name)
        self._security.remove_profile(plugin_name)
        self._instances.pop(plugin_name, None)
        self._sandboxes.pop(plugin_name, None)

        logger.info(f"Unregistered plugin: {plugin_name}")
        self._emit_event("plugin:unregistered", {"plugin_name": plugin_name})

    # ---- Lifecycle: Load ----

    def load(self, plugin_name: str) -> LoadResult:
        """Load a single plugin: import module, create instance, call on_load().

        Args:
            plugin_name: Name of the plugin to load.

        Returns:
            A LoadResult describing the outcome.

        Raises:
            KeyError: If the plugin is not registered.
            DependencyError: If dependencies cannot be satisfied.
            LifecycleError: If the plugin is not in a loadable state.
        """
        import time

        start = time.time()
        entry = self._registry.get_entry(plugin_name)

        # Validate state
        if entry.state not in (PluginState.REGISTERED, PluginState.ERROR):
            raise LifecycleError(plugin_name, entry.state, "load")

        # Resolve dependencies first
        deps, missing = self._registry.resolve_dependencies(plugin_name)

        # Auto-load dependencies that are registered but not yet loaded
        all_dep_names = set(deps)
        for dep_name, _, _ in missing:
            if self._registry.is_registered(dep_name):
                all_dep_names.add(dep_name)

        for dep_name in all_dep_names:
            if self._registry.is_registered(dep_name):
                dep_state = self.get_plugin_state(dep_name)
                if dep_state == PluginState.REGISTERED:
                    logger.info(f"Auto-loading dependency '{dep_name}' for '{plugin_name}'")
                    self.load(dep_name)

        # Re-check
        deps, missing = self._registry.resolve_dependencies(plugin_name)
        optional_missing = {
            dep: ver for dep, ver in entry.metadata.optional_dependencies.items()
            if not self._registry.is_registered(dep)
        }
        # Only fail on hard dependencies
        hard_missing = [
            (dep, ver, reason) for dep, ver, reason in missing
            if dep not in optional_missing
        ]
        if hard_missing:
            raise DependencyError(
                plugin_name=plugin_name,
                missing_deps=[f"{d} ({v})" for d, v, _ in hard_missing],
            )

        # Create instance
        try:
            instance = entry.plugin_class()
        except Exception as e:
            result = LoadResult(
                plugin_name=plugin_name,
                success=False,
                error=f"Failed to instantiate plugin: {e}",
            )
            entry.state = PluginState.ERROR
            entry.instance = None
            self._record_lifecycle(
                plugin_name, PluginState.REGISTERED, PluginState.ERROR,
                success=False, error=str(e),
            )
            return result

        # Update registry entry
        entry.instance = instance
        entry.state = PluginState.LOADED
        self._instances[plugin_name] = instance

        # Call on_load()
        try:
            instance.on_load()
            entry.state = PluginState.INITIALIZED
        except Exception as e:
            entry.state = PluginState.ERROR
            result = LoadResult(
                plugin_name=plugin_name,
                success=False,
                instance=instance,
                error=f"on_load() failed: {e}",
            )
            self._record_lifecycle(
                plugin_name, PluginState.LOADED, PluginState.ERROR,
                success=False, error=str(e),
            )
            return result

        # Create sandbox
        profile = self._security.get_profile(plugin_name)
        sandbox_config = SandboxConfig.from_permission_profile(profile)
        self._sandboxes[plugin_name] = SandboxExecutor(
            config=sandbox_config,
            plugin_name=plugin_name,
            security=self._security,
        )

        elapsed = (time.time() - start) * 1000
        self._record_lifecycle(
            plugin_name, PluginState.LOADED, PluginState.INITIALIZED,
            success=True, duration_ms=elapsed,
        )

        logger.info(f"Loaded plugin: {plugin_name}")
        self._emit_event("plugin:loaded", {"plugin_name": plugin_name})

        return LoadResult(
            plugin_name=plugin_name,
            success=True,
            instance=instance,
            dependencies_resolved=deps,
        )

    def load_all(self, respect_priority: bool = True) -> List[LoadResult]:
        """Load all registered plugins in dependency order.

        Args:
            respect_priority: If True, load higher priority plugins first
                              within each dependency level.

        Returns:
            List of LoadResult for each plugin.
        """
        results: List[LoadResult] = []

        # Compute load order using topological sort
        try:
            load_order = self._compute_load_order(respect_priority)
        except DependencyError as e:
            logger.error(f"Dependency resolution failed: {e}")
            # Try to load what we can anyway
            load_order = list(self._registry.list_plugins())

        for plugin_name in load_order:
            if self.get_plugin_state(plugin_name) in (
                PluginState.UNLOADED,
                PluginState.REGISTERED,
                PluginState.ERROR,
            ):
                try:
                    result = self.load(plugin_name)
                    results.append(result)
                except Exception as e:
                    results.append(LoadResult(
                        plugin_name=plugin_name,
                        success=False,
                        error=str(e),
                    ))

        return results

    # ---- Lifecycle: Start ----

    def start(self, plugin_name: str) -> bool:
        """Start a loaded plugin, transitioning it to RUNNING state.

        Args:
            plugin_name: Name of the plugin to start.

        Returns:
            True if started successfully.

        Raises:
            KeyError: If the plugin is not registered.
            LifecycleError: If the plugin is not in a startable state.
        """
        entry = self._registry.get_entry(plugin_name)
        instance = self._instances.get(plugin_name)

        if not instance:
            raise LifecycleError(plugin_name, entry.state, "start (no instance)")

        if entry.state not in (PluginState.INITIALIZED, PluginState.STOPPED):
            raise LifecycleError(plugin_name, entry.state, "start")

        try:
            instance.on_start()
            # on_start should set state to RUNNING; validate
            if instance.state != PluginState.RUNNING:
                logger.warning(
                    f"Plugin '{plugin_name}' on_start() did not transition to RUNNING "
                    f"(state is {instance.state.value}); forcing transition"
                )
                instance._state = PluginState.RUNNING
            entry.state = PluginState.RUNNING
        except Exception as e:
            entry.state = PluginState.ERROR
            self._record_lifecycle(
                plugin_name, PluginState.INITIALIZED, PluginState.ERROR,
                success=False, error=str(e),
            )
            logger.error(f"Failed to start plugin '{plugin_name}': {e}")
            return False

        self._record_lifecycle(
            plugin_name, PluginState.INITIALIZED, PluginState.RUNNING,
            success=True,
        )

        logger.info(f"Started plugin: {plugin_name}")
        self._emit_event("plugin:started", {"plugin_name": plugin_name})
        return True

    def start_all(self) -> Dict[str, bool]:
        """Start all initialized plugins.

        Returns:
            Dict mapping plugin name to success status.
        """
        results: Dict[str, bool] = {}
        for name in self._registry.list_plugins():
            state = self.get_plugin_state(name)
            if state in (PluginState.INITIALIZED, PluginState.STOPPED):
                results[name] = self.start(name)
        return results

    # ---- Lifecycle: Stop ----

    def stop(self, plugin_name: str) -> bool:
        """Stop a running plugin, transitioning it to STOPPED state.

        Args:
            plugin_name: Name of the plugin to stop.

        Returns:
            True if stopped successfully.

        Raises:
            KeyError: If the plugin is not registered.
            LifecycleError: If the plugin is not in a stoppable state.
        """
        entry = self._registry.get_entry(plugin_name)
        instance = self._instances.get(plugin_name)

        if not instance:
            return True  # Nothing to stop

        if entry.state != PluginState.RUNNING:
            # Already stopped or never started
            return True

        try:
            instance.on_stop()
            # on_stop sets state to STOPPING; validate
            if instance.state == PluginState.STOPPING:
                instance._state = PluginState.STOPPED
            entry.state = PluginState.STOPPED
        except Exception as e:
            entry.state = PluginState.ERROR
            self._record_lifecycle(
                plugin_name, PluginState.RUNNING, PluginState.ERROR,
                success=False, error=str(e),
            )
            logger.error(f"Failed to stop plugin '{plugin_name}': {e}")
            return False

        self._record_lifecycle(
            plugin_name, PluginState.RUNNING, PluginState.STOPPED,
            success=True,
        )

        logger.info(f"Stopped plugin: {plugin_name}")
        self._emit_event("plugin:stopped", {"plugin_name": plugin_name})
        return True

    def stop_all(self) -> Dict[str, bool]:
        """Stop all running plugins in reverse dependency order.

        Returns:
            Dict mapping plugin name to success status.
        """
        # Reverse of load order (dependent plugins stop first)
        try:
            stop_order = list(reversed(self._compute_load_order()))
        except DependencyError:
            stop_order = list(self._registry.list_plugins())

        results: Dict[str, bool] = {}
        for name in stop_order:
            if self.get_plugin_state(name) == PluginState.RUNNING:
                results[name] = self.stop(name)
        return results

    # ---- Lifecycle: Unload ----

    def unload(self, plugin_name: str) -> bool:
        """Unload a stopped plugin, calling on_unload() and releasing resources.

        Args:
            plugin_name: Name of the plugin to unload.

        Returns:
            True if unloaded successfully.

        Raises:
            KeyError: If the plugin is not registered.
        """
        entry = self._registry.get_entry(plugin_name)
        instance = self._instances.get(plugin_name)

        if not instance:
            return True

        if entry.state == PluginState.RUNNING:
            self.stop(plugin_name)

        try:
            instance.on_unload()
        except Exception as e:
            logger.error(f"Error during on_unload for '{plugin_name}': {e}")

        # Clean up sandbox workspace
        sandbox = self._sandboxes.pop(plugin_name, None)
        if sandbox:
            sandbox.cleanup_workspace()

        entry.state = PluginState.UNLOADED
        entry.instance = None
        self._instances.pop(plugin_name, None)

        self._record_lifecycle(
            plugin_name, PluginState.STOPPED, PluginState.UNLOADED,
            success=True,
        )

        logger.info(f"Unloaded plugin: {plugin_name}")
        self._emit_event("plugin:unloaded", {"plugin_name": plugin_name})
        return True

    def unload_all(self) -> Dict[str, bool]:
        """Unload all plugins.

        Returns:
            Dict mapping plugin name to success status.
        """
        results: Dict[str, bool] = {}
        for name in list(self._registry.list_plugins()):
            results[name] = self.unload(name)
        return results

    # ---- State Queries ----

    def get_plugin_state(self, plugin_name: str) -> PluginState:
        """Get the current lifecycle state of a plugin.

        Args:
            plugin_name: Name of the plugin.

        Returns:
            The current PluginState.

        Raises:
            KeyError: If the plugin is not registered.
        """
        return self._registry.get_entry(plugin_name).state

    def get_plugin_instance(self, plugin_name: str) -> Optional[PluginBase]:
        """Get the instance of a loaded plugin.

        Args:
            plugin_name: Name of the plugin.

        Returns:
            The PluginBase instance, or None if not loaded.
        """
        return self._instances.get(plugin_name)

    def is_plugin_running(self, plugin_name: str) -> bool:
        """Check if a plugin is in the RUNNING state.

        Args:
            plugin_name: Name of the plugin.

        Returns:
            True if running.
        """
        try:
            return self.get_plugin_state(plugin_name) == PluginState.RUNNING
        except KeyError:
            return False

    def get_running_plugins(self) -> List[str]:
        """Get names of all currently running plugins.

        Returns:
            List of running plugin names.
        """
        return [
            name for name in self._registry.list_plugins()
            if self.get_plugin_state(name) == PluginState.RUNNING
        ]

    def get_sandbox(self, plugin_name: str) -> Optional[SandboxExecutor]:
        """Get the sandbox executor for a plugin.

        Args:
            plugin_name: Name of the plugin.

        Returns:
            The SandboxExecutor, or None if not loaded.
        """
        return self._sandboxes.get(plugin_name)

    # ---- Event Hooks ----

    def subscribe(
        self,
        event_name: str,
        plugin_name: str,
        callback: EventCallback,
    ) -> None:
        """Subscribe a plugin to receive a specific event.

        Args:
            event_name: Name of the event to subscribe to.
            plugin_name: Name of the subscribing plugin.
            callback: Callback function (event_name, event_data) -> None.
        """
        self._event_hooks[event_name].append((plugin_name, callback))

    def unsubscribe(
        self,
        event_name: str,
        plugin_name: str,
    ) -> None:
        """Unsubscribe a plugin from a specific event.

        Args:
            event_name: Name of the event.
            plugin_name: Name of the plugin to unsubscribe.
        """
        self._event_hooks[event_name] = [
            (pn, cb) for pn, cb in self._event_hooks[event_name]
            if pn != plugin_name
        ]

    def subscribe_global(self, callback: EventCallback) -> None:
        """Register a global event listener (not tied to a plugin).

        Args:
            callback: Callback function for all events.
        """
        self._global_listeners.append(callback)

    def unsubscribe_global(self, callback: EventCallback) -> None:
        """Remove a global event listener.

        Args:
            callback: The callback to remove.
        """
        if callback in self._global_listeners:
            self._global_listeners.remove(callback)

    def emit_event(self, event_name: str, event_data: Any = None) -> int:
        """Emit an event to all subscribers.

        Args:
            event_name: Name of the event.
            event_data: Optional event payload.

        Returns:
            Number of listeners notified.
        """
        return self._emit_event(event_name, event_data)

    def _emit_event(self, event_name: str, event_data: Any = None) -> int:
        """Internal event emission with error handling.

        Args:
            event_name: Name of the event.
            event_data: Optional event payload.

        Returns:
            Number of listeners notified.
        """
        count = 0

        # Notify global listeners
        for listener in self._global_listeners:
            try:
                listener(event_name, event_data)
                count += 1
            except Exception as e:
                logger.error(f"Global listener error for event '{event_name}': {e}")

        # Notify plugin-specific listeners
        for plugin_name, callback in self._event_hooks.get(event_name, []):
            try:
                callback(event_name, event_data)
                count += 1
            except Exception as e:
                logger.error(
                    f"Plugin '{plugin_name}' listener error for event '{event_name}': {e}"
                )

        return count

    def get_event_subscriptions(self) -> Dict[str, List[str]]:
        """Get a mapping of event names to subscribed plugin names.

        Returns:
            Dict of event_name -> list of plugin names.
        """
        return {
            event: [pn for pn, _ in subscribers]
            for event, subscribers in self._event_hooks.items()
        }

    # ---- Capability Execution ----

    def execute_capability(
        self,
        capability: str,
        *args: Any,
        preferred_plugin: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        """Execute a capability through an available plugin.

        Finds a plugin that provides the given capability and executes it.
        Optionally prefers a specific plugin if multiple are available.

        Args:
            capability: Name of the capability to execute.
            *args: Positional arguments for the capability.
            preferred_plugin: Optional name of a preferred plugin.
            **kwargs: Keyword arguments for the capability.

        Returns:
            The result of the capability execution.

        Raises:
            ValueError: If no plugin provides the capability.
            RuntimeError: If the plugin is not running.
        """
        entries = self._registry.find_by_capability(capability)

        if not entries:
            raise ValueError(f"No plugin provides capability '{capability}'")

        # Select the appropriate plugin
        selected: Optional[RegistryEntry] = None
        if preferred_plugin:
            for e in entries:
                if e.name == preferred_plugin:
                    selected = e
                    break

        if selected is None:
            # Pick the first running one, or first available
            for e in entries:
                if self.is_plugin_running(e.name):
                    selected = e
                    break
            if selected is None:
                selected = entries[0]

        instance = self.get_plugin_instance(selected.name)
        if not instance:
            raise RuntimeError(
                f"Plugin '{selected.name}' is not loaded"
            )

        if not self.is_plugin_running(selected.name):
            raise RuntimeError(
                f"Plugin '{selected.name}' is not running (state: {self.get_plugin_state(selected.name).value})"
            )

        # Execute with sandbox if available
        sandbox = self.get_sandbox(selected.name)
        if sandbox:
            result = sandbox.execute(
                instance.execute, capability, *args, **kwargs
            )
            if not result.success:
                raise RuntimeError(
                    f"Sandboxed execution of '{capability}' failed: {result.error}"
                )
            return result.result
        else:
            return instance.execute(capability, *args, **kwargs)

    def execute_capability_all(
        self,
        capability: str,
        *args: Any,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Execute a capability on ALL plugins that provide it.

        Args:
            capability: Name of the capability.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            Dict mapping plugin name to result (or exception).
        """
        results: Dict[str, Any] = {}
        entries = self._registry.find_by_capability(capability)

        for entry in entries:
            if not self.is_plugin_running(entry.name):
                results[entry.name] = RuntimeError(
                    f"Plugin not running (state: {self.get_plugin_state(entry.name).value})"
                )
                continue

            try:
                results[entry.name] = self.execute_capability(
                    capability, *args, preferred_plugin=entry.name, **kwargs
                )
            except Exception as e:
                results[entry.name] = e

        return results

    # ---- Dependency Resolution ----

    def _compute_load_order(self, respect_priority: bool = True) -> List[str]:
        """Compute the order in which plugins should be loaded.

        Uses topological sort based on dependency graph. Detects cycles.

        Args:
            respect_priority: If True, sort by priority within dependency levels.

        Returns:
            List of plugin names in load order.

        Raises:
            DependencyError: If a dependency cycle is detected.
        """
        entries = self._registry.get_all_entries()

        # Build adjacency list
        graph: Dict[str, DependencyNode] = {}
        for name, entry in entries.items():
            node = DependencyNode(
                plugin_name=name,
                metadata=entry.metadata,
                dependencies=[],
            )
            graph[name] = node

        # Populate dependencies (only hard deps of registered plugins)
        for name, entry in entries.items():
            node = graph[name]
            node.dependencies = [
                dep for dep in entry.metadata.dependencies
                if dep in graph
            ]
            # Update dependents
            for dep in node.dependencies:
                graph[dep].dependents.append(name)

        # Topological sort using Kahn's algorithm (BFS-based)
        # Build in-degree counts (number of unresolved dependencies)
        in_degree: Dict[str, int] = {}
        adjacency: Dict[str, List[str]] = defaultdict(list)
        for name in graph:
            in_degree[name] = len(graph[name].dependencies)
            for dep in graph[name].dependencies:
                adjacency[dep].append(name)

        # Start with nodes that have no dependencies
        queue: List[str] = [n for n, deg in in_degree.items() if deg == 0]
        if respect_priority:
            queue.sort(key=lambda n: -graph[n].metadata.load_priority)
        else:
            queue.sort()

        result: List[str] = []
        while queue:
            node = queue.pop(0)
            result.append(node)
            for dependent in adjacency.get(node, []):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
                    if respect_priority:
                        queue.sort(key=lambda n: -graph[n].metadata.load_priority)

        # Check for cycles: if we can't resolve all nodes, there's a cycle
        if len(result) != len(graph):
            # Find nodes in the cycle for error message
            cycle_nodes = [n for n in graph if n not in result]
            raise DependencyError(
                plugin_name=cycle_nodes[0] if cycle_nodes else "unknown",
                missing_deps=[],
                cycle_deps=cycle_nodes,
            )

        return result

    def resolve_dependencies(self, plugin_name: str) -> Tuple[List[str], List[Tuple[str, str, str]]]:
        """Resolve dependencies for a plugin via the registry.

        Args:
            plugin_name: Name of the plugin.

        Returns:
            Tuple of (satisfied, missing) dependencies.
        """
        return self._registry.resolve_dependencies(plugin_name)

    def get_dependency_graph(self) -> Dict[str, List[str]]:
        """Get the full dependency graph of registered plugins.

        Returns:
            Dict mapping plugin name to list of dependency plugin names.
        """
        entries = self._registry.get_all_entries()
        graph: Dict[str, List[str]] = {}
        for name, entry in entries.items():
            graph[name] = list(entry.metadata.dependencies.keys())
        return graph

    def check_plugin_health(self, plugin_name: str) -> Dict[str, Any]:
        """Perform a health check on a plugin.

        Args:
            plugin_name: Name of the plugin.

        Returns:
            Dict with health status information.
        """
        health: Dict[str, Any] = {
            "plugin_name": plugin_name,
            "registered": self._registry.is_registered(plugin_name),
            "state": None,
            "has_instance": False,
            "has_sandbox": False,
            "dependencies_satisfied": [],
            "dependencies_missing": [],
            "error": None,
        }

        if health["registered"]:
            entry = self._registry.get_entry(plugin_name)
            health["state"] = entry.state.value
            health["has_instance"] = plugin_name in self._instances
            health["has_sandbox"] = plugin_name in self._sandboxes

            satisfied, missing = self._registry.resolve_dependencies(plugin_name)
            health["dependencies_satisfied"] = satisfied
            health["dependencies_missing"] = [
                {"name": d, "required": v, "reason": r} for d, v, r in missing
            ]

        return health

    def get_health_summary(self) -> Dict[str, Any]:
        """Get a summary of the entire plugin framework's health.

        Returns:
            Dict with overall health status.
        """
        return {
            "total_plugins": self._registry.count(),
            "running_plugins": len(self.get_running_plugins()),
            "plugins_by_state": self._count_by_state(),
            "event_subscriptions": len(self._event_hooks),
            "lifecycle_events": len(self._lifecycle_history),
        }

    def _count_by_state(self) -> Dict[str, int]:
        """Count plugins in each lifecycle state.

        Returns:
            Dict mapping state name to count.
        """
        counts: Dict[str, int] = defaultdict(int)
        for name in self._registry.list_plugins():
            state = self.get_plugin_state(name)
            counts[state.value] += 1
        return dict(counts)

    # ---- Audit / History ----

    def _record_lifecycle(
        self,
        plugin_name: str,
        from_state: PluginState,
        to_state: PluginState,
        success: bool = True,
        error: Optional[str] = None,
        duration_ms: float = 0.0,
    ) -> None:
        """Record a lifecycle transition event.

        Args:
            plugin_name: Name of the plugin.
            from_state: State before the transition.
            to_state: State after the transition.
            success: Whether the transition succeeded.
            error: Error message if the transition failed.
            duration_ms: Duration of the transition in milliseconds.
        """
        import datetime
        event = LifecycleEvent(
            plugin_name=plugin_name,
            from_state=from_state,
            to_state=to_state,
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            success=success,
            error=error,
            duration_ms=duration_ms,
        )
        self._lifecycle_history.append(event)

    def get_lifecycle_history(
        self,
        plugin_name: Optional[str] = None,
        limit: int = 50,
    ) -> List[LifecycleEvent]:
        """Get lifecycle transition history.

        Args:
            plugin_name: Optional filter by plugin name.
            limit: Maximum number of events to return (most recent first).

        Returns:
            List of LifecycleEvent objects.
        """
        events = self._lifecycle_history
        if plugin_name:
            events = [e for e in events if e.plugin_name == plugin_name]
        return events[-limit:]

    def clear_history(self) -> None:
        """Clear all lifecycle history."""
        self._lifecycle_history.clear()

    # ---- Convenience ----

    def get_plugin_sandbox_config(self, plugin_name: str) -> Optional[SandboxConfig]:
        """Get the sandbox configuration for a loaded plugin.

        Args:
            plugin_name: Name of the plugin.

        Returns:
            The SandboxConfig if a sandbox exists, None otherwise.
        """
        sandbox = self._sandboxes.get(plugin_name)
        if sandbox:
            return sandbox.config
        return None

    def update_sandbox_config(self, plugin_name: str, config: SandboxConfig) -> None:
        """Update the sandbox configuration for a plugin.

        Args:
            plugin_name: Name of the plugin.
            config: New sandbox configuration.
        """
        self._sandboxes[plugin_name] = SandboxExecutor(
            config=config,
            plugin_name=plugin_name,
            security=self._security,
        )

    def __repr__(self) -> str:
        return (
            f"<PluginManager(plugins={self._registry.count()}, "
            f"running={len(self.get_running_plugins())}>"
        )