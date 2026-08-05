"""ENI MCP Tools Module — FastMCP-style tool registry & MCP serving layer.

A dependency-free (stdlib-only) Model Context Protocol tool gateway: a
thread-safe registry of callable tools (``@tool`` decorating sync or async
handlers) whose schemas are auto-derived from type hints, plus an MCP/JSON-RPC
wire layer (``tools/list`` / ``tools/call``) so an external gateway can serve
it over HTTP/SSE later.

The module is a registered Platform Kernel module implementing the standard
lifecycle (``initialize`` / ``health_check`` / ``shutdown``) and the event-bus
wiring contract (``set_event_bus``).

Version: 1.0.0
Python: 3.11+
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from enterprise.platform_kernel import (
    Event,
    EventBus,
    EventPriority,
    HealthStatus,
    Module,
    module,
)

from .mcp_tools import (
    MemoryTransport,
    StdioTransport,
    Tool,
    ToolCallError,
    ToolRegistry,
    ToolServer,
    Transport,
    ValidationError,
    register_builtin_tools,
    tool,
)

__version__ = "1.0.0"
__module__ = "mcp_tools"

__all__ = [
    "__version__",
    "MCPToolGatewayModule",
    # Core framework
    "Tool",
    "ToolRegistry",
    "ToolServer",
    "ToolCallError",
    "ValidationError",
    "tool",
    "register_builtin_tools",
    # Pluggable transports
    "Transport",
    "StdioTransport",
    "MemoryTransport",
    # Factory
    "create_mcp_tools_module",
]

_logger = logging.getLogger("enterprise.mcp_tools")


@module(name="mcp_tools", version="1.0.0")
class MCPToolGatewayModule(Module):
    """Enterprise MCP Tools Module — FastMCP-style tool registry & serving layer.

    Wraps a :class:`~.ToolRegistry` behind the Platform Kernel module
    lifecycle and exposes a small public facade (``register_tool`` /
    ``list_tools`` / ``call_tool`` / ``get_tool`` / ``unregister_tool``).
    Tools may be sync or async callables; MCP-shaped responses are produced by
    :meth:`ToolRegistry.handle_request`.

    Configuration (dict passed to ``__init__``):
        max_tools (int): Maximum number of tools the registry will hold
            (default 1000).
        tags (list[str]): Extra tags applied to every built-in demo tool.

    Events published (when an event bus is wired via ``set_event_bus``):
        - mcp_tools.tool.called  — a tool was executed through the module.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._registry: ToolRegistry | None = None
        self._event_bus: EventBus | None = None
        self._lock = threading.RLock()
        self._max_tools: int = int(self._config.get("max_tools", 1000) or 1000)
        self._tags: list[str] = list(self._config.get("tags", []) or [])

    # -- Properties ---------------------------------------------------------

    @property
    def registry(self) -> ToolRegistry | None:
        """Return the active ToolRegistry (None before initialization)."""
        with self._lock:
            return self._registry

    @property
    def max_tools(self) -> int:
        """Configured maximum number of tools."""
        return self._max_tools

    # -- Lifecycle ----------------------------------------------------------

    async def initialize(self) -> None:
        """Build the ToolRegistry and register the built-in demo tools."""
        with self._lock:
            self._status = HealthStatus.STARTING

        _logger.info(
            "MCP tools initializing (max_tools=%s, tags=%s)", self._max_tools, self._tags
        )
        try:
            registry = ToolRegistry(max_tools=self._max_tools)
            registry.initialize()
            if self._tags:
                for entry in registry.list():
                    registered = registry.get(entry["name"])
                    if registered is not None:
                        merged = list(dict.fromkeys(registered.tags + self._tags))
                        registered.tags = merged
            with self._lock:
                self._registry = registry
                self._status = HealthStatus.HEALTHY
            _logger.info("MCP tools initialized: %d tool(s)", registry.count())
        except Exception as exc:  # noqa: BLE001 - lifecycle must report UNHEALTHY
            _logger.exception("Failed to initialize mcp_tools: %s", exc)
            with self._lock:
                self._status = HealthStatus.UNHEALTHY
            raise

    async def health_check(self) -> HealthStatus:
        """A healthy registry is built and non-empty.

        Returns:
            HEALTHY if the registry is initialized, UNKNOWN otherwise.
        """
        with self._lock:
            if self._registry is not None and self._status is HealthStatus.HEALTHY:
                return HealthStatus.HEALTHY
            if self._status is HealthStatus.UNHEALTHY:
                return HealthStatus.UNHEALTHY
            self._status = HealthStatus.UNKNOWN
            return self._status

    async def shutdown(self) -> None:
        """Gracefully shut down the module, releasing the registry."""
        with self._lock:
            self._status = HealthStatus.STOPPING
            _logger.info("Shutting down mcp_tools module...")
            self._registry = None
            self._status = HealthStatus.HEALTHY

    # -- Event Bus Wiring ---------------------------------------------------

    def set_event_bus(self, event_bus: EventBus) -> None:
        """Wire the platform EventBus into this module.

        Called by the Platform Kernel after module discovery but before
        ``initialize()``. If an event bus is already active it is replaced
        gracefully.
        """
        with self._lock:
            self._event_bus = event_bus

    # -- Public facade ------------------------------------------------------

    def register_tool(self, tool_or_decorator: Any, name: str | None = None) -> Tool:
        """Register a Tool (or a decorated/bare callable) and return the Tool.

        Raises:
            ValueError: if the tool name is already registered.
        """
        registry = self._require_registry()
        registered = registry.register(tool_or_decorator, name=name)
        self._emit(
            "mcp_tools.tool.registered",
            {"name": registered.name, "version": registered.version},
        )
        return registered

    def list_tools(self) -> list[dict[str, Any]]:
        """Return JSON-serializable dicts describing every registered tool."""
        return self._require_registry().list_tools()

    def get_tool(self, name: str) -> Tool | None:
        """Return the :class:`Tool` registered under ``name`` (or None)."""
        return self._require_registry().get(name)

    def unregister_tool(self, name: str) -> bool:
        """Remove a tool by name. Returns True if it was removed."""
        removed = self._require_registry().unregister(name)
        if removed:
            self._emit("mcp_tools.tool.unregistered", {"name": name})
        return removed

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Execute the tool named ``name`` with ``arguments``.

        Emits ``mcp_tools.tool.called`` on the event bus when available. Async
        handlers are awaited transparently.
        """
        registry = self._require_registry()
        result = registry.call(name, arguments=arguments)
        self._emit(
            "mcp_tools.tool.called",
            {"name": name, "arguments": arguments or {}},
        )
        return result

    async def call_tool_async(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> Any:
        """Asynchronously execute the tool named ``name`` with ``arguments``."""
        registry = self._require_registry()
        result = await registry.acall(name, arguments=arguments)
        self._emit(
            "mcp_tools.tool.called",
            {"name": name, "arguments": arguments or {}},
        )
        return result

    async def handle_request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        request_id: Any = None,
    ) -> dict[str, Any]:
        """Serve an MCP request (``tools/list`` / ``tools/call``) as JSON-RPC."""
        registry = self._require_registry()
        if method == "tools/call":
            name = (params or {}).get("name")
            if isinstance(name, str):
                self._emit("mcp_tools.tool.called", {"name": name, "method": method})
        return await registry.handle_request(method, params=params, request_id=request_id)

    # -- Helpers ------------------------------------------------------------

    def _require_registry(self) -> ToolRegistry:
        """Return the active registry or raise if not initialized."""
        registry = self.registry
        if registry is None:
            raise RuntimeError("mcp_tools module is not initialized")
        return registry

    def _emit(self, topic: str, payload: dict[str, Any]) -> None:
        """Publish an event on the wired bus (no-op if none is set)."""
        with self._lock:
            bus = self._event_bus
        if bus is None:
            return
        try:
            bus.publish(
                Event.create(
                    topic,
                    source=self.name,
                    payload=payload,
                    priority=EventPriority.NORMAL,
                )
            )
        except Exception as exc:  # noqa: BLE001 - defensive
            _logger.warning("Failed to publish event %s: %s", topic, exc)


def create_mcp_tools_module(
    config: dict[str, Any] | None = None,
) -> MCPToolGatewayModule:
    """Create (but do not initialize) an :class:`MCPToolGatewayModule`.

    Args:
        config: Optional dict. Supported keys:
            - ``max_tools`` (int): max tools the registry holds (default 1000).
            - ``tags`` (list[str]): extra tags applied to every built-in tool.

    Returns:
        An uninitialized :class:`MCPToolGatewayModule`. Call ``await
        initialize()`` (e.g. via the Platform Kernel lifecycle) before use.
    """
    return MCPToolGatewayModule(config=config or {})
