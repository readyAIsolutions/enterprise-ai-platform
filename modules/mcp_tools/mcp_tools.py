"""MCP Tools Core — a FastMCP-style tool framework (stdlib only).

This is the pure-logic heart of the ``mcp_tools`` Platform Kernel module. It
provides a Model Context Protocol (MCP) style tool registry and serving layer
with zero external dependencies:

* ``tool`` — decorator that turns a plain sync/async callable into a
  :class:`Tool`, auto-deriving a JSON Schema ``input_schema`` from its type
  hints (``str``/``int``/``float``/``bool``/``Optional``/``list[...]``/
  ``dict[...]``). Defaulted parameters are marked ``required: false``.
* ``Tool`` — dataclass describing a single callable tool.
* ``ToolRegistry`` — thread-safe registry with ``register`` / ``unregister`` /
  ``get`` / ``list`` / ``count``, duplicate-name rejection, and input
  validation before dispatch.
* ``ToolCallError`` / ``ValidationError`` — typed error hierarchy.
* MCP wire compatibility — ``initialize`` / ``list_tools`` / ``tools`` and an
  async ``handle_request`` returning JSON-RPC 2.0 shaped responses for the
  MCP ``tools/list`` and ``tools/call`` methods, so a gateway can serve it over
  HTTP/SSE later without changes.

No external packages are required. Works on Python 3.11+.

Version: 1.0.0
"""

from __future__ import annotations

import abc
import asyncio
import inspect
import json
import logging
import os
import sys
import threading
import time
import types
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Union, get_args, get_origin, get_type_hints

__all__ = [
    "Tool",
    "ToolRegistry",
    "ToolServer",
    "ToolCallError",
    "ValidationError",
    "tool",
    "register_builtin_tools",
    "Transport",
    "StdioTransport",
    "MemoryTransport",
]

_logger = logging.getLogger("enterprise.mcp_tools")

_PRIMITIVE_JSON: dict[type, str] = {
    str: "string",
    bool: "boolean",
    int: "integer",
    float: "number",
}

_UNION_ORIGINS: tuple[Any, ...] = (Union, types.UnionType)

_JSONRPC_VERSION = "2.0"


# =========================================================================
# Errors
# =========================================================================


class ToolCallError(Exception):
    """Raised when a tool cannot be found or fails to execute."""


class ValidationError(ToolCallError):
    """Raised when tool arguments fail input-schema validation."""


# =========================================================================
# Schema derivation
# =========================================================================


def _is_none_type(annotation: Any) -> bool:
    """Return True if ``annotation`` is the ``None`` type."""
    return annotation is type(None) or annotation is None


def _derive_type(annotation: Any) -> dict[str, Any]:
    """Map a Python type annotation onto a minimal JSON Schema fragment.

    Supports primitives, ``Optional[T]`` / ``T | None``, ``list[T]`` and
    ``dict``. Unknown/forward types degrade to ``"any"`` so tool decorators
    never fail on exotic annotations.
    """
    if annotation is Any or annotation is inspect.Parameter.empty:
        return {"type": "any"}

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin in _UNION_ORIGINS:
        non_none = [a for a in args if not _is_none_type(a)]
        if len(non_none) == 1:
            return _derive_type(non_none[0])
        if non_none:
            return {"type": "any"}
        return {"type": "null"}

    if origin in (list,):
        item_type: dict[str, Any] = {}
        if args:
            item_type = _derive_type(args[0])
        return {"type": "array", "items": item_type}

    if origin in (dict,):
        return {"type": "object"}

    if annotation in _PRIMITIVE_JSON:
        return {"type": _PRIMITIVE_JSON[annotation]}

    name = getattr(annotation, "__name__", str(annotation))
    if name in _PRIMITIVE_JSON.values():
        return {"type": name}
    return {"type": "any"}


def _annotation_is_optional(annotation: Any) -> bool:
    """Return True if ``annotation`` includes ``None`` (i.e. is optional)."""
    origin = get_origin(annotation)
    if origin in _UNION_ORIGINS:
        return any(_is_none_type(a) for a in get_args(annotation))
    return False


def _derive_input_schema(func: Callable[..., Any]) -> dict[str, Any]:
    """Build a JSON Schema ``object`` from a callable's signature + hints.

    Each parameter becomes a property. A parameter is ``required: false`` if
    it has a default value OR is typed as ``Optional``. Required parameter
    names are also listed in the top-level ``required`` array for MCP
    compatibility.
    """
    hints = _safe_type_hints(func)
    sig = inspect.signature(func)
    properties: dict[str, Any] = {}
    required: list[str] = []

    for param in sig.parameters.values():
        if param.name in ("self", "cls"):
            continue
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        annotation = hints.get(param.name, Any)
        prop = _derive_type(annotation)
        doc = _doc_for(func, param.name)
        if doc:
            prop["description"] = doc
        has_default = param.default is not inspect.Parameter.empty
        if has_default:
            prop.setdefault("default", param.default)
        if _annotation_is_optional(annotation):
            prop["nullable"] = True
        is_required = not has_default and not _annotation_is_optional(annotation)
        prop["required"] = is_required
        properties[param.name] = prop
        if is_required:
            required.append(param.name)

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "required": required,
    }
    return schema


def _safe_type_hints(func: Callable[..., Any]) -> dict[str, Any]:
    """Return resolved type hints, falling back to ``Any`` on failure."""
    try:
        return dict(get_type_hints(func))
    except Exception:  # noqa: BLE001 - hints are best-effort
        return {}


def _doc_for(func: Callable[..., Any], param_name: str) -> str:
    """Pull a short parameter description from the docstring if present."""
    doc = inspect.getdoc(func) or ""
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped.startswith(f":param {param_name}:"):
            return stripped.split(":", 2)[-1].strip()
        if stripped.startswith(f":{param_name}:"):
            return stripped.split(":", 2)[-1].strip()
    return ""


def _derive_output_schema(func: Callable[..., Any]) -> dict[str, Any]:
    """Derive a minimal output schema from the return annotation."""
    hints = _safe_type_hints(func)
    ret = hints.get("return")
    if ret is None or ret is inspect.Signature.empty:
        return {"type": "any"}
    schema = _derive_type(ret)
    schema.setdefault("description", "Tool handler return value")
    return schema


# =========================================================================
# Tool
# =========================================================================


@dataclass
class Tool:
    """A single MCP-style callable tool.

    Attributes:
        name: Unique tool name used for dispatch.
        description: Human-readable description of the tool's purpose.
        input_schema: JSON Schema describing accepted ``arguments``.
        output_schema: JSON Schema describing the handler return value.
        handler: The underlying sync or async callable.
        tags: Arbitrary string tags for discovery/grouping.
        version: Tool version string.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    handler: Callable[..., Any]
    tags: list[str] = field(default_factory=list)
    version: str = "1.0.0"

    @classmethod
    def from_function(
        cls,
        func: Callable[..., Any],
        name: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        version: str | None = None,
    ) -> Tool:
        """Build a :class:`Tool` from a callable, deriving its schemas."""
        tool_name = name or getattr(func, "__name__", "tool")
        tool_description = description
        if not tool_description:
            doc = inspect.getdoc(func) or ""
            tool_description = doc.splitlines()[0].strip() if doc else ""
        return cls(
            name=tool_name,
            description=tool_description or f"Execute the {tool_name} tool.",
            input_schema=_derive_input_schema(func),
            output_schema=_derive_output_schema(func),
            handler=func,
            tags=list(tags or []),
            version=version or "1.0.0",
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary (name/description/etc.)."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "outputSchema": self.output_schema,
            "tags": list(self.tags),
            "version": self.version,
        }


# =========================================================================
# @tool decorator
# =========================================================================


def tool(
    name: str | None = None,
    *,
    description: str | None = None,
    tags: list[str] | None = None,
    version: str | None = None,
) -> Callable[..., Any]:
    """Decorator that turns a callable into an MCP-style :class:`Tool`.

    The returned object is the original function (so it stays directly
    callable / testable) with an attached ``_mcp_tool`` attribute carrying the
    derived :class:`Tool`. Supports both ``@tool()`` and bare ``@tool`` usage.

    Example::

        @tool(description="Add two integers")
        def add(a: int, b: int) -> int:
            return a + b
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        tool_obj = Tool.from_function(
            func,
            name=name,
            description=description,
            tags=tags,
            version=version,
        )
        func._mcp_tool = tool_obj  # type: ignore[attr-defined]  # noqa: SLF001
        return func

    if isinstance(name, Callable):  # bare @tool usage
        func = name
        name = None
        return decorator(func)
    return decorator


def _tool_of(candidate: Any) -> Tool:
    """Resolve a :class:`Tool` from a Tool, a decorated fn or a bare fn."""
    if isinstance(candidate, Tool):
        return candidate
    attached = getattr(candidate, "_mcp_tool", None)
    if isinstance(attached, Tool):
        return attached
    if callable(candidate):
        return Tool.from_function(candidate)
    raise TypeError(f"Cannot register {candidate!r}: not a Tool or callable")


# =========================================================================
# ToolRegistry
# =========================================================================


class ToolRegistry:
    """Thread-safe registry + MCP serving layer for :class:`Tool` objects.

    Responsibilities:
      * register / unregister / get / list / count with duplicate rejection
      * input validation against each tool's ``input_schema`` before dispatch
      * sync (``call``) and async (``acall``) dispatch
      * MCP wire responses via ``handle_request``
    """

    def __init__(self, max_tools: int = 1000) -> None:
        self._tools: dict[str, Tool] = {}
        self._lock: threading.RLock = threading.RLock()
        self._max_tools: int = max(1, int(max_tools))
        self._initialized: bool = False

    # -- Properties ---------------------------------------------------------

    @property
    def max_tools(self) -> int:
        """Maximum number of tools the registry will hold."""
        return self._max_tools

    @property
    def initialized(self) -> bool:
        """True once built-in demo tools have been registered."""
        return self._initialized

    # -- Registration -------------------------------------------------------

    def register(
        self,
        tool_or_decorator: Any,
        name: str | None = None,
    ) -> Tool:
        """Register a Tool (or decorated/bare callable), returning the Tool.

        If ``name`` is given it overrides the tool's name. Raises
        :class:`ValueError` on duplicate names and :class:`ToolCallError` when
        the registry is full.
        """
        resolved = _tool_of(tool_or_decorator)
        final_name = name or resolved.name
        if not final_name:
            raise ValueError("Tool name must not be empty")
        with self._lock:
            if final_name in self._tools:
                raise ValueError(f"A tool named {final_name!r} is already registered")
            if len(self._tools) >= self._max_tools:
                raise ToolCallError(
                    f"Tool registry is full ({self._max_tools} tools max)"
                )
            if final_name != resolved.name:
                resolved = _rename(resolved, final_name)
            self._tools[final_name] = resolved
        _logger.info("Registered tool %r", final_name)
        return resolved

    def unregister(self, name: str) -> bool:
        """Remove a tool by name. Returns True if it was removed."""
        with self._lock:
            return self._tools.pop(name, None) is not None

    def get(self, name: str) -> Tool | None:
        """Return the :class:`Tool` registered under ``name`` (or None)."""
        with self._lock:
            return self._tools.get(name)

    def list(self) -> list[dict[str, Any]]:
        """Return JSON-serializable dicts for every registered tool."""
        with self._lock:
            return [t.to_dict() for t in sorted(self._tools.values(), key=lambda t: t.name)]

    def list_tools(self) -> list[dict[str, Any]]:
        """Alias of :meth:`list` exposing the same MCP-facing dict payloads."""
        return self.list()

    def tools(self) -> list[dict[str, Any]]:
        """Return the MCP ``tools/list`` ``result.tools`` payload directly."""
        return self.list()

    def count(self) -> int:
        """Return the number of registered tools."""
        with self._lock:
            return len(self._tools)

    # -- Built-ins ----------------------------------------------------------

    def initialize(self) -> None:
        """Idempotently register the built-in demo tools."""
        if self._initialized:
            return
        register_builtin_tools(self)
        self._initialized = True

    # -- Validation ---------------------------------------------------------

    def validate(self, tool_: Tool, arguments: dict[str, Any] | None) -> dict[str, Any]:
        """Validate ``arguments`` against ``tool_``'s input schema.

        Verifies required args are present and present args match their
        declared JSON types. Raises :class:`ValidationError` with a clear
        message on mismatch.
        """
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise ValidationError(
                f"Arguments for tool {tool_.name!r} must be a dict, got "
                f"{type(arguments).__name__}"
            )
        schema = tool_.input_schema
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        for req in required:
            if req not in arguments:
                raise ValidationError(
                    f"Missing required argument {req!r} for tool {tool_.name!r}"
                )

        for key, value in arguments.items():
            prop = properties.get(key)
            if prop is None:
                continue
            self._check_value(tool_, key, prop, value)
        return arguments

    @staticmethod
    def _check_value(
        tool_: Tool,
        key: str,
        prop: dict[str, Any],
        value: Any,
    ) -> None:
        """Check a single value against its JSON type; raise on mismatch."""
        if value is None and prop.get("nullable"):
            return
        expected = prop.get("type")
        if expected in (None, "any", "null"):
            if expected == "null" and value is not None:
                raise ValidationError(
                    f"Argument {key!r} for tool {tool_.name!r} must be null"
                )
            return
        ok = _type_matches(expected, value)
        if not ok:
            raise ValidationError(
                f"Argument {key!r} for tool {tool_.name!r} must be of type "
                f"{expected!r}, got {type(value).__name__}"
            )

    # -- Dispatch -----------------------------------------------------------

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Synchronously execute the tool named ``name`` with ``arguments``.

        Async handlers are awaited transparently (via the running loop, or a
        fresh one when none is active).
        """
        tool_ = self.get(name)
        if tool_ is None:
            raise ToolCallError(f"Unknown tool: {name!r}")
        kwargs = self.validate(tool_, arguments)
        result = tool_.handler(**kwargs)
        if inspect.isawaitable(result):
            return _run_awaitable(result)
        return result

    async def acall(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Asynchronously execute the tool named ``name`` with ``arguments``."""
        tool_ = self.get(name)
        if tool_ is None:
            raise ToolCallError(f"Unknown tool: {name!r}")
        kwargs = self.validate(tool_, arguments)
        result = tool_.handler(**kwargs)
        if inspect.isawaitable(result):
            result = await result
        return result

    # -- MCP wire layer -----------------------------------------------------

    async def handle_request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        request_id: Any = None,
    ) -> dict[str, Any]:
        """Handle an MCP/JSON-RPC request, returning a JSON-RPC 2.0 response.

        Supported methods:
          * ``tools/list`` — returns registered tool metadata.
          * ``tools/call`` — executes a tool with ``params.name`` /
            ``params.arguments``; results are wrapped as text content.

        Unknown methods and tool/validation errors are surfaced as JSON-RPC
        error responses so the wire layer never raises.
        """
        params = params or {}
        if method == "tools/list":
            return {
                "jsonrpc": _JSONRPC_VERSION,
                "id": request_id,
                "method": "tools/list",
                "result": {"tools": self.tools()},
            }
        if method == "tools/call":
            return await self._handle_call(params, request_id)
        return {
            "jsonrpc": _JSONRPC_VERSION,
            "id": request_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    async def _handle_call(
        self,
        params: dict[str, Any],
        request_id: Any,
    ) -> dict[str, Any]:
        """Execute an MCP ``tools/call`` request."""
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or not self.has(name):
            return self._call_error(
                request_id, f"Unknown tool: {name!r}", code=-32602
            )
        try:
            output = await self.acall(name, arguments)
        except ValidationError as exc:
            return self._call_error(request_id, str(exc), code=-32602)
        except ToolCallError as exc:
            return self._call_error(request_id, str(exc), code=-32602)
        except Exception as exc:  # noqa: BLE001 - surface handler errors
            _logger.exception("Tool %r raised during call", name)
            return self._call_error(request_id, f"Tool execution failed: {exc}")
        content = _content_for(output)
        return {
            "jsonrpc": _JSONRPC_VERSION,
            "id": request_id,
            "method": "tools/call",
            "result": {"content": [content], "isError": False},
        }

    def has(self, name: str) -> bool:
        """Return True if a tool named ``name`` is registered."""
        return self.get(name) is not None

    @staticmethod
    def _call_error(request_id: Any, message: str, code: int = -32602) -> dict[str, Any]:
        """Build a JSON-RPC error envelope for a failed tool call."""
        return {
            "jsonrpc": _JSONRPC_VERSION,
            "id": request_id,
            "error": {"code": code, "message": message},
        }


def _rename(tool_: Tool, new_name: str) -> Tool:
    """Return a copy of ``tool_`` with an overridden name."""
    return Tool(
        name=new_name,
        description=tool_.description,
        input_schema=tool_.input_schema,
        output_schema=tool_.output_schema,
        handler=tool_.handler,
        tags=list(tool_.tags),
        version=tool_.version,
    )


def _type_matches(expected: str, value: Any) -> bool:
    """Check whether ``value`` matches a JSON Schema ``type`` keyword."""
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True


def _content_for(output: Any) -> dict[str, Any]:
    """Wrap a tool result as an MCP ``text`` content item."""
    if isinstance(output, str):
        text = output
    else:
        try:
            text = json.dumps(output, default=str)
        except (TypeError, ValueError):  # noqa: BLE001
            text = str(output)
    return {"type": "text", "text": text}


def _run_awaitable(awaitable: Any) -> Any:
    """Execute an awaitable from synchronous code without deadlocking."""
    async def _unwrap() -> Any:
        return await awaitable

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_unwrap())
        finally:
            loop.close()
    # Already inside a running loop: schedule and block the current thread.
    loop = asyncio.get_running_loop()
    future = asyncio.run_coroutine_threadsafe(_unwrap(), loop)
    return future.result()


# =========================================================================
# Built-in demo tools
# =========================================================================


def register_builtin_tools(registry: ToolRegistry) -> None:
    """Register a handful of example tools onto ``registry``.

    Idempotent per built-in name: existing entries are left untouched.
    """
    _quiet_register(registry, echo)
    _quiet_register(registry, add)
    _quiet_register(registry, now)
    _quiet_register(registry, get_env)
    _quiet_register(registry, upper)


def _quiet_register(registry: ToolRegistry, func: Callable[..., Any]) -> None:
    """Register a built-in only when its name is not already taken."""
    existing = getattr(func, "_mcp_tool", None)
    name = existing.name if isinstance(existing, Tool) else func.__name__
    if registry.has(name):
        return
    registry.register(func)


@tool(description="Echo the given text back unchanged.", tags=["demo", "text"])
def echo(text: str) -> str:
    """:param text: the text to echo back."""
    return text


@tool(description="Add two integers together.", tags=["demo", "math"])
def add(a: int, b: int) -> int:
    """:param a: first integer.
    :param b: second integer.
    """
    return a + b


@tool(description="Return the current UTC time as an ISO string.", tags=["demo", "time"])
def now(format: str = "iso") -> str:  # noqa: A002
    """:param format: 'iso' for ISO-8601, otherwise integer UTC timestamp."""
    current = datetime.now(UTC)
    if format == "timestamp":
        return str(int(current.timestamp()))
    return current.isoformat()


@tool(
    description="Read an environment variable, returning '' when unset.",
    tags=["demo", "system"],
)
def get_env(name: str) -> str:
    """:param name: the environment variable name to read."""
    return os.environ.get(name, "")


@tool(description="Convert text to uppercase.", tags=["demo", "text"])
def upper(text: str) -> str:
    """:param text: the text to uppercase."""
    return text.upper()


# =========================================================================
# FastMCP-style ToolServer
# =========================================================================


class ToolServer:
    """FastMCP-style server facade over a :class:`ToolRegistry`.

    Provides the familiar ``@server.tool`` decorator ergonomics layered on top
    of the thread-safe registry: registering a plain sync or async callable
    auto-derives its JSON Schema from the signature + docstring, and the same
    callable stays directly callable/testable.

        server = ToolServer()
        @server.tool(description="Add two integers")
        def add(a: int, b: int) -> int:
            return a + b

        server.list()                          # auto-built schemas
        server.call("add", {"a": 2, "b": 3})   # -> 5
        asyncio.run(server.handle_request("tools/call", {...}))

    Both sync and async handlers are supported transparently through
    :meth:`call` / :meth:`acall`, and JSON-RPC 2.0 responses for
    ``tools/list`` / ``tools/call`` are produced by :meth:`handle_request`.
    """

    def __init__(self, name: str = "mcp", registry: ToolRegistry | None = None) -> None:
        self.name = name
        self.registry = registry if registry is not None else ToolRegistry()

    # -- Registration decorator -------------------------------------------

    def tool(
        self,
        name: str | None = None,
        *,
        description: str | None = None,
        tags: list[str] | None = None,
        version: str | None = None,
    ) -> Callable[..., Any]:
        """Decorator that registers a callable as a tool on this server.

        Supports both ``@server.tool`` (bare) and ``@server.tool(...)``
        (with options). The decorated callable is preserved (and tagged with
        ``_mcp_tool``) so it stays directly callable, and it is immediately
        registered for dispatch. Sync and async handlers both work.
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            decorated = tool(
                name=name,
                description=description,
                tags=tags,
                version=version,
            )(func)
            self.register(decorated, name=name)
            return decorated

        if isinstance(name, Callable):  # bare @server.tool usage
            func = name
            name = None
            return decorator(func)
        return decorator

    # -- Registry passthrough ---------------------------------------------

    def register(self, tool_or_decorator: Any, name: str | None = None) -> Tool:
        """Register a Tool / decorated / bare callable and return the Tool."""
        return self.registry.register(tool_or_decorator, name=name)

    def unregister(self, name: str) -> bool:
        """Remove the tool registered under ``name`` (True if removed)."""
        return self.registry.unregister(name)

    def get(self, name: str) -> Tool | None:
        """Return the :class:`Tool` registered under ``name`` (or None)."""
        return self.registry.get(name)

    def has(self, name: str) -> bool:
        """Return True if a tool named ``name`` is registered."""
        return self.registry.has(name)

    def count(self) -> int:
        """Return the number of registered tools."""
        return self.registry.count()

    def list(self) -> list[dict[str, Any]]:
        """Return JSON-serializable auto-built schemas for every tool."""
        return self.registry.list()

    # -- Dispatch ----------------------------------------------------------

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Synchronously dispatch to the tool named ``name``.

        Async handlers are awaited transparently. Raises :class:`ToolCallError`
        for an unknown tool and :class:`ValidationError` for bad arguments.
        """
        return self.registry.call(name, arguments=arguments)

    async def acall(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> Any:
        """Asynchronously dispatch to the tool named ``name``."""
        return await self.registry.acall(name, arguments=arguments)

    # -- MCP / JSON-RPC wire layer ----------------------------------------

    async def handle_request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        request_id: Any = None,
    ) -> dict[str, Any]:
        """Serve ``tools/list`` / ``tools/call`` as JSON-RPC 2.0 responses."""
        return await self.registry.handle_request(
            method, params=params, request_id=request_id
        )


# =========================================================================
# Pluggable transports
# =========================================================================


class Transport(abc.ABC):
    """Abstract base class for MCP message transports.

    A transport carries JSON-RPC 2.0 shaped dictionaries between a peer (the
    client) and the :class:`ToolServer`. Concrete transports (stdio,
    in-memory, HTTP/SSE later) implement :meth:`send` and :meth:`receive`;
    :meth:`request` provides a convenience round-trip helper.
    """

    @abc.abstractmethod
    def send(self, message: dict[str, Any]) -> None:
        """Send one JSON-RPC message to the peer."""

    @abc.abstractmethod
    def receive(self) -> dict[str, Any] | None:
        """Receive one JSON-RPC message, or None when nothing is pending."""

    def request(self, message: dict[str, Any], timeout: float = 5.0) -> dict[str, Any]:
        """Send ``message`` and block until a response arrives (or ``timeout``).

        Useful for request/response round-trips over a synchronous transport.
        """
        deadline = time.monotonic() + timeout
        self.send(message)
        while time.monotonic() < deadline:
            response = self.receive()
            if response is not None:
                return response
            time.sleep(0.005)
        raise TimeoutError(f"Timed out after {timeout}s waiting for a response")

    def serve(
        self,
        handler: Callable[[dict[str, Any]], dict[str, Any] | None],
    ) -> None:
        """Run a synchronous read/serve loop, dispatching to ``handler``.

        Calls ``handler(message)`` for each received message and, if it
        returns a response, sends it back. Stops on EOF. Useful for stdio
        servers and in-memory test harnesses.
        """
        while True:
            message = self.receive()
            if message is None:
                break
            response = handler(message)
            if response is not None:
                self.send(response)


class MemoryTransport(Transport):
    """Bidirectional in-memory transport for tests and concurrent servers.

    Two :class:`MemoryTransport` endpoints connected with :meth:`connect`
    pass messages to each other synchronously (no blocking I/O).
    """

    def __init__(self) -> None:
        self._peer: MemoryTransport | None = None
        self._inbox: list[dict[str, Any]] = []
        self._closed = False

    def connect(self, peer: MemoryTransport) -> None:
        """Pair this endpoint with ``peer`` so sends route into its inbox."""
        self._peer = peer
        peer._peer = self

    def send(self, message: dict[str, Any]) -> None:
        if self._peer is None:
            raise RuntimeError("MemoryTransport is not connected to a peer")
        if self._closed:
            raise RuntimeError("MemoryTransport is closed")
        self._peer._inbox.append(message)

    def receive(self) -> dict[str, Any] | None:
        if not self._inbox:
            return None
        return self._inbox.pop(0)

    def close(self) -> None:
        self._closed = True


class StdioTransport(Transport):
    """JSON-RPC transport over ``stdin``/``stdout`` (or given file objects).

    Each message is a single UTF-8 JSON line. Suitable for MCP over stdio:
    the server reads a request line, writes a response line, and exits on EOF.
    """

    def __init__(self, stdin: Any = None, stdout: Any = None) -> None:
        self._stdin = stdin if stdin is not None else sys.stdin
        self._stdout = stdout if stdout is not None else sys.stdout
        self._eof = False

    def send(self, message: dict[str, Any]) -> None:
        self._stdout.write(json.dumps(message, default=str) + "\n")
        self._stdout.flush()

    def receive(self) -> dict[str, Any] | None:
        if self._eof:
            return None
        line = self._stdin.readline()
        if line == "":
            self._eof = True
            return None
        line = line.strip()
        if not line:
            return None
        try:
            parsed = json.loads(line)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid JSON-RPC line: {line!r}") from None
        return parsed if isinstance(parsed, dict) else parsed
