"""
HooksEngine — 25+ Lifecycle Hooks with Plugin System
======================================================

Part of the Claude Code Core enterprise module. Provides a hook-based
extension system for intercepting and modifying behavior at 25+ lifecycle
points. Supports synchronous and asynchronous hooks, priority ordering,
and a plugin manifest system.

Classes:
  HookType — enum of 25+ lifecycle hook points
  HookPriority — priority levels for hook ordering
  HookResult — result returned by a hook execution
  PluginManifest — metadata for a hook plugin
  HookPlugin — a plugin with registered hooks
  HooksEngine — orchestrates hook registration and execution
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Union

logger = logging.getLogger("enterprise.agent.hooks_engine")

try:
    from enterprise.platform_kernel import HealthStatus
except ImportError:
    from platform_kernel import HealthStatus


# =============================================================================
# Enums
# =============================================================================


class HookType(Enum):
    """25+ lifecycle hook points."""
    # Session lifecycle
    SESSION_START = "session.start"
    SESSION_END = "session.end"
    SESSION_PAUSE = "session.pause"
    SESSION_RESUME = "session.resume"

    # Query lifecycle
    QUERY_PRE_PROCESS = "query.pre_process"
    QUERY_POST_PROCESS = "query.post_process"
    QUERY_PRE_SEND = "query.pre_send"
    QUERY_POST_RECEIVE = "query.post_receive"

    # Tool lifecycle
    TOOL_PRE_EXECUTE = "tool.pre_execute"
    TOOL_POST_EXECUTE = "tool.post_execute"
    TOOL_ON_ERROR = "tool.on_error"
    TOOL_VALIDATE_INPUT = "tool.validate_input"
    TOOL_VALIDATE_OUTPUT = "tool.validate_output"

    # Context lifecycle
    CONTEXT_PRE_COMPRESS = "context.pre_compress"
    CONTEXT_POST_COMPRESS = "context.post_compress"
    CONTEXT_ENTRY_ADDED = "context.entry_added"
    CONTEXT_ENTRY_REMOVED = "context.entry_removed"

    # State lifecycle
    STATE_PRE_SAVE = "state.pre_save"
    STATE_POST_LOAD = "state.post_load"
    STATE_MERGE_CONFLICT = "state.merge_conflict"

    # Model lifecycle
    MODEL_PRE_ROUTE = "model.pre_route"
    MODEL_POST_ROUTE = "model.post_route"
    MODEL_ON_FALLBACK = "model.on_fallback"
    MODEL_STREAM_TOKEN = "model.stream_token"

    # Module lifecycle
    MODULE_INIT = "module.init"
    MODULE_SHUTDOWN = "module.shutdown"
    MODULE_HEALTH_CHECK = "module.health_check"

    # Error handling
    ERROR_GLOBAL = "error.global"
    ERROR_RECOVERY = "error.recovery"


class HookPriority(Enum):
    """Priority levels for hook execution order."""
    HIGHEST = 0
    HIGH = 25
    NORMAL = 50
    LOW = 75
    LOWEST = 100


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class HookResult:
    """Result returned by a hook execution.

    Attributes:
        hook_type: The hook point that was triggered.
        plugin_id: The plugin that handled the hook.
        data: Result data from the hook.
        modified: Whether the hook modified the input data.
        prevent_default: Whether to prevent default behavior.
        error: Error message if the hook failed.
    """
    hook_type: HookType
    plugin_id: str
    data: Any = None
    modified: bool = False
    prevent_default: bool = False
    error: Optional[str] = None


@dataclass
class PluginManifest:
    """Metadata manifest for a hook plugin.

    Attributes:
        plugin_id: Unique plugin identifier.
        name: Human-readable plugin name.
        version: Version string.
        author: Plugin author.
        description: Plugin description.
        hooks: Hook types this plugin registers for.
        priority: Default priority for all hooks.
        dependencies: Plugin IDs this plugin depends on.
    """
    plugin_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    version: str = "1.0.0"
    author: str = ""
    description: str = ""
    hooks: List[HookType] = field(default_factory=list)
    priority: HookPriority = HookPriority.NORMAL
    dependencies: List[str] = field(default_factory=list)


# =============================================================================
# HookPlugin
# =============================================================================


class HookPlugin:
    """A plugin with registered hook handlers.

    Plugins register callbacks for specific hook types. Handlers can be
    synchronous or asynchronous functions that receive context data and
    optionally modify it.

    Usage::

        plugin = HookPlugin(manifest)
        plugin.register(HookType.QUERY_PRE_PROCESS, my_handler, priority=HookPriority.HIGH)
    """

    def __init__(self, manifest: PluginManifest) -> None:
        self.manifest = manifest
        self._handlers: Dict[HookType, List[tuple[int, Callable[..., Any]]]] = (
            defaultdict(list)
        )
        self._enabled = True
        self.registered_at: datetime = datetime.now(timezone.utc)

    def register(self, hook_type: HookType,
                 handler: Union[Callable[..., Any], Callable[..., Awaitable[Any]]],
                 priority: Optional[HookPriority] = None) -> None:
        """Register a handler for a hook type.

        Args:
            hook_type: The hook point to listen for.
            handler: Sync or async function. Receives (context_data, **kwargs).
            priority: Execution priority (default: manifest priority).
        """
        prio = (priority or self.manifest.priority).value
        self._handlers[hook_type].append((prio, handler))
        self._handlers[hook_type].sort(key=lambda x: x[0])

    def unregister(self, hook_type: HookType, handler: Callable[..., Any]) -> bool:
        """Unregister a handler from a hook type.

        Returns:
            True if the handler was found and removed.
        """
        for i, (prio, h) in enumerate(self._handlers[hook_type]):
            if h is handler:
                self._handlers[hook_type].pop(i)
                return True
        return False

    def get_handlers(self, hook_type: HookType) -> List[Callable[..., Any]]:
        """Get all registered handlers for a hook type, ordered by priority."""
        return [h for _, h in self._handlers[hook_type]]

    def has_handler(self, hook_type: HookType) -> bool:
        """Check if any handler is registered for a hook type."""
        return len(self._handlers[hook_type]) > 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    @property
    def registered_hook_types(self) -> Set[HookType]:
        return set(self._handlers.keys())


# =============================================================================
# HooksEngine
# =============================================================================


class HooksEngine:
    """Orchestrates hook registration, ordering, and execution.

    Manages the lifecycle of all hook plugins and provides methods to
    trigger hooks at specific points. Supports sync and async handlers,
    priority ordering, default-prevention, and error isolation.

    Usage::

        engine = HooksEngine()
        await engine.initialize()
        plugin = HookPlugin(manifest)
        engine.register_plugin(plugin)
        results = await engine.trigger(HookType.QUERY_PRE_PROCESS, data={"query": "hello"})
        await engine.shutdown()
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self._config = config or {}
        self._plugins: Dict[str, HookPlugin] = {}
        self._status = HealthStatus.UNKNOWN
        self._trigger_count: Dict[HookType, int] = defaultdict(int)

    async def initialize(self) -> None:
        self._status = HealthStatus.HEALTHY
        logger.info("HooksEngine initialized")

    async def health_check(self) -> bool:
        return self._status == HealthStatus.HEALTHY

    async def shutdown(self) -> None:
        self._plugins.clear()
        self._trigger_count.clear()
        self._status = HealthStatus.UNKNOWN
        logger.info("HooksEngine shut down")

    def register_plugin(self, plugin: HookPlugin) -> None:
        """Register a hook plugin.

        Args:
            plugin: The HookPlugin to register.
        """
        self._plugins[plugin.manifest.plugin_id] = plugin
        logger.debug("Registered plugin %s (%d hook types)",
                     plugin.manifest.name, len(plugin.registered_hook_types))

    def unregister_plugin(self, plugin_id: str) -> bool:
        """Unregister a plugin by ID.

        Returns:
            True if the plugin was found and removed.
        """
        if plugin_id in self._plugins:
            del self._plugins[plugin_id]
            return True
        return False

    def get_plugin(self, plugin_id: str) -> Optional[HookPlugin]:
        """Get a registered plugin by ID."""
        return self._plugins.get(plugin_id)

    async def trigger(self, hook_type: HookType,
                      data: Any = None,
                      **kwargs: Any) -> List[HookResult]:
        """Trigger all handlers for a hook type.

        Executes handlers in priority order. Each handler receives
        (data, **kwargs). If a handler returns a result with
        prevent_default=True, downstream handlers are skipped.

        Args:
            hook_type: The hook point to trigger.
            data: Arbitrary context data passed to handlers.
            **kwargs: Additional keyword arguments.

        Returns:
            List of HookResult, one per executed handler.
        """
        self._trigger_count[hook_type] += 1
        results: List[HookResult] = []

        # Collect all handlers from all plugins, ordered by priority
        handlers: List[tuple[int, str, Callable[..., Any]]] = []
        for plugin_id, plugin in self._plugins.items():
            if not plugin.enabled:
                continue
            for priority, handler in plugin._handlers.get(hook_type, []):
                handlers.append((priority, plugin_id, handler))

        handlers.sort(key=lambda x: x[0])

        for priority, plugin_id, handler in handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    result_data = await handler(data, **kwargs)
                else:
                    loop = asyncio.get_event_loop()
                    result_data = await loop.run_in_executor(
                        None, functools.partial(handler, data, **kwargs)
                    )

                modified = result_data is not None and result_data is not data
                prevent = False
                if isinstance(result_data, dict):
                    prevent = result_data.get("__prevent_default__", False)

                results.append(HookResult(
                    hook_type=hook_type,
                    plugin_id=plugin_id,
                    data=result_data,
                    modified=modified,
                    prevent_default=prevent,
                ))

                if prevent:
                    logger.debug("Hook %s prevented default by plugin %s",
                                 hook_type.value, plugin_id)
                    break

            except Exception as exc:
                logger.error("Hook %s handler in plugin %s failed: %s",
                             hook_type.value, plugin_id, exc)
                results.append(HookResult(
                    hook_type=hook_type,
                    plugin_id=plugin_id,
                    error=str(exc),
                ))

        return results

    def trigger_sync(self, hook_type: HookType,
                     data: Any = None,
                     **kwargs: Any) -> List[HookResult]:
        """Synchronous wrapper for triggering hooks.

        Only executes synchronous handlers. Async handlers are skipped.
        """
        self._trigger_count[hook_type] += 1
        results: List[HookResult] = []

        handlers: List[tuple[int, str, Callable[..., Any]]] = []
        for plugin_id, plugin in self._plugins.items():
            if not plugin.enabled:
                continue
            for priority, handler in plugin._handlers.get(hook_type, []):
                if not inspect.iscoroutinefunction(handler):
                    handlers.append((priority, plugin_id, handler))

        handlers.sort(key=lambda x: x[0])

        for priority, plugin_id, handler in handlers:
            try:
                result_data = handler(data, **kwargs)
                modified = result_data is not None and result_data is not data
                prevent = False
                if isinstance(result_data, dict):
                    prevent = result_data.get("__prevent_default__", False)

                results.append(HookResult(
                    hook_type=hook_type,
                    plugin_id=plugin_id,
                    data=result_data,
                    modified=modified,
                    prevent_default=prevent,
                ))

                if prevent:
                    break

            except Exception as exc:
                logger.error("Hook %s sync handler failed: %s", hook_type.value, exc)
                results.append(HookResult(
                    hook_type=hook_type,
                    plugin_id=plugin_id,
                    error=str(exc),
                ))

        return results

    def get_trigger_stats(self) -> Dict[str, int]:
        """Get trigger count statistics for each hook type."""
        return {k.value: v for k, v in self._trigger_count.items()}

    @property
    def plugin_count(self) -> int:
        return len(self._plugins)

    @property
    def plugins(self) -> Dict[str, HookPlugin]:
        return dict(self._plugins)

    @property
    def status(self) -> HealthStatus:
        return self._status