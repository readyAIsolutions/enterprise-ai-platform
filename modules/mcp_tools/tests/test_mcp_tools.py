"""Unit tests for the mcp_tools enterprise module.

Covers the FastMCP-style tool framework and the Platform Kernel module:

  - ``@tool`` decorator + JSON Schema derivation from type hints (types,
    defaults -> required:false, optional types, list/dict, descriptions).
  - ToolRegistry register/get/list/count/unregister + duplicate rejection.
  - Input validation (missing required arg, wrong type, non-dict input).
  - Sync + async handler dispatch.
  - MCP/JSON-RPC wire layer (tools/list, tools/call, unknown method, errors).
  - Built-in demo tools.
  - Module lifecycle (initialize/health_check/shutdown) + event publishing.

Run with:
    python3 -m pytest modules/mcp_tools/tests -q
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import pytest
from enterprise.modules.mcp_tools import (
    MCPToolGatewayModule,
    Tool,
    ToolCallError,
    ToolRegistry,
    ValidationError,
    tool,
)
from enterprise.modules.mcp_tools.mcp_tools import register_builtin_tools
from enterprise.platform_kernel import EventBus, HealthStatus

# ---------------------------------------------------------------------------
# Helpers / example handlers
# ---------------------------------------------------------------------------


@tool(description="Greet someone by name.", tags=["test"])
def greet(name: str) -> str:
    """:param name: the person's name."""
    return f"Hello {name}"


@tool(description="Multiply two optional numbers.", tags=["test"])
def scale(value: float = 1.0, factor: int = 2) -> float:
    """:param value: base value.
    :param factor: multiplier.
    """
    return value * factor


def bare_concat(a: str, b: str) -> str:
    """:param a: first part.
    :param b: second part.
    """
    return a + b


@tool(description="Join several tags.", tags=["test"])
def join_tags(tags: list[str]) -> str:
    """:param tags: list of tags to join."""
    return ",".join(tags)


@tool(description="Return a metadata dict.", tags=["test"])
def meta(key: str) -> dict[str, Any]:
    """:param key: the key to store."""
    return {key: 42}


@tool(description="Echo a possibly-absent option.", tags=["test"])
def opt(value: str | None = None) -> str:
    """:param value: optional value."""
    return value or "none"


def typed_int(a: int) -> int:
    """:param a: an integer value."""
    return a


async def async_greet(name: str) -> str:
    """Async handler used to verify async dispatch."""
    return f"Hi {name}"


# ---------------------------------------------------------------------------
# @tool decorator + schema derivation
# ---------------------------------------------------------------------------


class TestToolDecoratorAndSchema:
    def test_schema_type_string_required(self) -> None:
        schema = greet._mcp_tool.input_schema  # type: ignore[attr-defined]
        props = schema["properties"]
        assert schema["type"] == "object"
        assert props["name"]["type"] == "string"
        assert props["name"]["required"] is True
        assert "name" in schema["required"]

    def test_add_schema_types_and_required(self) -> None:
        reg = ToolRegistry()
        reg.initialize()
        add_tool = reg.get("add")
        assert add_tool is not None
        schema = add_tool.input_schema
        assert schema["properties"]["a"]["type"] == "integer"
        assert schema["properties"]["b"]["type"] == "integer"
        assert schema["required"] == ["a", "b"]

    def test_default_becomes_required_false(self) -> None:
        registered = Tool.from_function(scale)
        props = registered.input_schema["properties"]
        assert props["value"]["required"] is False
        assert props["factor"]["required"] is False
        assert registered.input_schema["required"] == []

    def test_optional_type_becomes_required_false(self) -> None:
        registered = Tool.from_function(opt)
        props = registered.input_schema["properties"]
        assert props["value"]["required"] is False
        assert props["value"]["type"] == "string"

    def test_list_type_is_array(self) -> None:
        registered = Tool.from_function(join_tags)
        props = registered.input_schema["properties"]
        assert props["tags"]["type"] == "array"
        assert props["tags"]["required"] is True

    def test_dict_type_is_object(self) -> None:
        registered = Tool.from_function(meta)
        props = registered.input_schema["properties"]
        assert props["key"]["type"] == "string"

    def test_float_type_is_number(self) -> None:
        registered = Tool.from_function(scale)
        assert registered.input_schema["properties"]["value"]["type"] == "number"

    def test_description_from_decorator(self) -> None:
        reg = ToolRegistry()
        reg.initialize()
        echo_tool = reg.get("echo")
        assert echo_tool is not None
        assert "Echo" in echo_tool.description

    def test_docstring_param_description_parsed(self) -> None:
        registered = Tool.from_function(greet)
        assert "person" in registered.input_schema["properties"]["name"].get("description", "")

    def test_bare_at_tool_usage(self) -> None:
        @tool
        def bare(value: int) -> int:  # noqa: ANN001
            return value

        assert hasattr(bare, "_mcp_tool")
        assert bare._mcp_tool.name == "bare"  # type: ignore[attr-defined]

    def test_name_override_in_decorator(self) -> None:
        @tool(name="renamed", description="Overridden")
        def original_fn(x: int) -> int:
            return x

        assert original_fn._mcp_tool.name == "renamed"  # type: ignore[attr-defined]
        assert original_fn._mcp_tool.description == "Overridden"

    def test_output_schema_derived(self) -> None:
        registered = Tool.from_function(greet)
        assert registered.output_schema is not None


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------


class TestToolRegistry:
    def test_register_tool_object(self) -> None:
        reg = ToolRegistry()
        registered = reg.register(Tool.from_function(greet))
        assert reg.count() == 1
        assert registered.name == "greet"

    def test_register_returns_tool(self) -> None:
        reg = ToolRegistry()
        registered = reg.register(greet)
        assert isinstance(registered, Tool)
        assert registered.name == "greet"

    def test_register_name_override(self) -> None:
        reg = ToolRegistry()
        registered = reg.register(greet, name="greet2")
        assert registered.name == "greet2"
        assert reg.has("greet2")
        assert not reg.has("greet")

    def test_get_returns_tool(self) -> None:
        reg = ToolRegistry()
        reg.register(greet)
        assert reg.get("greet") is not None
        assert reg.get("greet").description  # type: ignore[union-attr]

    def test_get_missing_returns_none(self) -> None:
        reg = ToolRegistry()
        assert reg.get("nope") is None

    def test_list_json_serializable(self) -> None:
        reg = ToolRegistry()
        reg.register(greet)
        listed = reg.list()
        assert len(listed) == 1
        payload = json.dumps(listed)  # must not raise
        assert isinstance(payload, str)
        assert listed[0]["name"] == "greet"
        assert "inputSchema" in listed[0]
        assert "tags" in listed[0]
        assert "version" in listed[0]

    def test_count(self) -> None:
        reg = ToolRegistry()
        reg.register(greet)
        reg.register(scale)
        assert reg.count() == 2

    def test_unregister(self) -> None:
        reg = ToolRegistry()
        reg.register(greet)
        assert reg.unregister("greet") is True
        assert reg.count() == 0

    def test_unregister_missing_returns_false(self) -> None:
        reg = ToolRegistry()
        assert reg.unregister("missing") is False

    def test_duplicate_name_rejected(self) -> None:
        reg = ToolRegistry()
        reg.register(greet)
        with pytest.raises(ValueError, match="already registered"):
            reg.register(greet)

    def test_duplicate_name_override_rejected(self) -> None:
        reg = ToolRegistry()
        reg.register(greet)
        with pytest.raises(ValueError, match="already registered"):
            reg.register(scale, name="greet")

    def test_register_decorated_function(self) -> None:
        reg = ToolRegistry()
        reg.register(join_tags)
        assert reg.has("join_tags")

    def test_register_bare_function(self) -> None:
        reg = ToolRegistry()
        reg.register(bare_concat)
        assert reg.has("bare_concat")
        assert reg.call("bare_concat", {"a": "x", "b": "y"}) == "xy"

    def test_register_invalid_raises_typeerror(self) -> None:
        reg = ToolRegistry()
        with pytest.raises(TypeError, match="not a Tool or callable"):
            reg.register(12345)

    def test_max_tools_respected(self) -> None:
        reg = ToolRegistry(max_tools=1)
        reg.register(greet)
        with pytest.raises(ToolCallError, match="full"):
            reg.register(scale)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_validate_success(self) -> None:
        reg = ToolRegistry()
        reg.register(greet)
        kwargs = reg.validate(reg.get("greet"), {"name": "Ada"})  # type: ignore[arg-type]
        assert kwargs == {"name": "Ada"}

    def test_validate_missing_required(self) -> None:
        reg = ToolRegistry()
        reg.register(greet)
        with pytest.raises(ValidationError, match="Missing required argument"):
            reg.validate(reg.get("greet"), {})  # type: ignore[arg-type]

    def test_validate_wrong_type(self) -> None:
        reg = ToolRegistry()
        registered = reg.register(typed_int)
        with pytest.raises(ValidationError, match="must be of type"):
            reg.validate(registered, {"a": "not-an-int"})

    def test_validate_non_dict_arguments(self) -> None:
        reg = ToolRegistry()
        reg.register(greet)
        with pytest.raises(ValidationError, match="must be a dict"):
            reg.validate(reg.get("greet"), ["x"])  # type: ignore[arg-type]

    def test_validate_default_fills_required_list_only(self) -> None:
        reg = ToolRegistry()
        reg.register(scale)
        ok = reg.validate(reg.get("scale"), {})  # type: ignore[arg-type]
        assert ok == {}

    def test_validate_optional_null_value(self) -> None:
        reg = ToolRegistry()
        reg.register(opt)
        registry_tool = reg.get("opt")
        assert registry_tool is not None
        result = reg.call("opt", {"value": None})
        assert result == "none"


# ---------------------------------------------------------------------------
# Dispatch: sync + async
# ---------------------------------------------------------------------------


class TestDispatch:
    def test_call_sync_handler(self) -> None:
        reg = ToolRegistry()
        reg.register(greet)
        assert reg.call("greet", {"name": "Bob"}) == "Hello Bob"

    def test_call_unknown_tool(self) -> None:
        reg = ToolRegistry()
        with pytest.raises(ToolCallError, match="Unknown tool"):
            reg.call("missing")

    def test_call_async_handler_sync_context(self) -> None:
        reg = ToolRegistry()
        reg.register(async_greet)
        assert reg.call("async_greet", {"name": "Carol"}) == "Hi Carol"

    def test_acall_async_handler(self) -> None:
        reg = ToolRegistry()
        reg.register(async_greet)
        assert asyncio.run(reg.acall("async_greet", {"name": "Dave"})) == "Hi Dave"

    def test_acall_sync_handler(self) -> None:
        reg = ToolRegistry()
        reg.register(greet)

        async def _run() -> str:
            return await reg.acall("greet", {"name": "Eve"})

        assert asyncio.run(_run()) == "Hello Eve"

    def test_call_invalid_args_raises(self) -> None:
        reg = ToolRegistry()
        reg.register(greet)
        with pytest.raises(ValidationError, match="Missing required argument"):
            reg.call("greet", {})


# ---------------------------------------------------------------------------
# MCP / JSON-RPC wire layer
# ---------------------------------------------------------------------------


class TestMCPWire:
    def _registry(self) -> ToolRegistry:
        reg = ToolRegistry()
        reg.register(greet)
        return reg

    async def test_handle_tools_list_shape(self) -> None:
        reg = self._registry()
        response = await reg.handle_request("tools/list", request_id=1)
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert response["method"] == "tools/list"
        assert isinstance(response["result"]["tools"], list)

    async def test_handle_tools_call_success(self) -> None:
        reg = self._registry()
        response = await reg.handle_request(
            "tools/call", {"name": "greet", "arguments": {"name": "Fay"}}, request_id=2
        )
        assert response["method"] == "tools/call"
        assert response["result"]["isError"] is False
        text = response["result"]["content"][0]["text"]
        assert "Fay" in text

    async def test_handle_tools_call_unknown_tool(self) -> None:
        reg = self._registry()
        response = await reg.handle_request(
            "tools/call", {"name": "nope", "arguments": {}}, request_id=3
        )
        assert response["error"]["code"] == -32602
        assert "Unknown tool" in response["error"]["message"]

    async def test_handle_unknown_method(self) -> None:
        reg = self._registry()
        response = await reg.handle_request("bogus/method", request_id=4)
        assert response["error"]["code"] == -32601

    async def test_handle_call_validation_error(self) -> None:
        reg = self._registry()
        response = await reg.handle_request(
            "tools/call", {"name": "greet", "arguments": {}}, request_id=5
        )
        assert response["error"]["code"] == -32602
        assert "Missing required argument" in response["error"]["message"]

    async def test_tools_and_list_tools_payloads(self) -> None:
        reg = ToolRegistry()
        reg.register(greet)
        reg.register(scale)
        assert len(reg.tools()) == 2
        assert len(reg.list_tools()) == 2
        assert reg.tools()[0]["name"] == "greet"


# ---------------------------------------------------------------------------
# Built-in demo tools
# ---------------------------------------------------------------------------


class TestBuiltins:
    def _registry(self) -> ToolRegistry:
        reg = ToolRegistry()
        register_builtin_tools(reg)
        return reg

    def test_initialize_registers_builtins(self) -> None:
        reg = ToolRegistry()
        reg.initialize()
        assert reg.count() == 5
        for name in ("echo", "add", "now", "get_env", "upper"):
            assert reg.has(name)

    def test_initialize_idempotent(self) -> None:
        reg = ToolRegistry()
        reg.initialize()
        reg.initialize()
        assert reg.count() == 5

    def test_builtin_echo(self) -> None:
        assert self._registry().call("echo", {"text": "hi"}) == "hi"

    def test_builtin_add(self) -> None:
        assert self._registry().call("add", {"a": 2, "b": 3}) == 5

    def test_builtin_now(self) -> None:
        out = self._registry().call("now")
        assert isinstance(out, str)
        assert len(out) > 0

    def test_builtin_get_env(self) -> None:
        os.environ["MCP_TEST_VAR"] = "set"
        try:
            assert self._registry().call("get_env", {"name": "MCP_TEST_VAR"}) == "set"
        finally:
            os.environ.pop("MCP_TEST_VAR", None)

    def test_builtin_upper(self) -> None:
        assert self._registry().call("upper", {"text": "abc"}) == "ABC"


# ---------------------------------------------------------------------------
# Module lifecycle + facade
# ---------------------------------------------------------------------------


class TestMCPToolGatewayModule:
    async def test_initialize_healthy(self) -> None:
        mod = MCPToolGatewayModule(config={"max_tools": 50})
        assert mod.status is HealthStatus.UNKNOWN
        await mod.initialize()
        assert mod.status is HealthStatus.HEALTHY
        assert mod.registry is not None
        assert mod.registry.count() == 5

    async def test_health_check_unknown_before_init(self) -> None:
        mod = MCPToolGatewayModule()
        assert await mod.health_check() is HealthStatus.UNKNOWN

    async def test_health_check_healthy_after_init(self) -> None:
        mod = MCPToolGatewayModule()
        await mod.initialize()
        assert await mod.health_check() is HealthStatus.HEALTHY

    async def test_shutdown_releases_registry(self) -> None:
        mod = MCPToolGatewayModule()
        await mod.initialize()
        await mod.shutdown()
        assert mod.registry is None

    async def test_defaults(self) -> None:
        mod = MCPToolGatewayModule()
        await mod.initialize()
        assert mod.max_tools == 1000

    async def test_register_facade(self) -> None:
        mod = MCPToolGatewayModule()
        await mod.initialize()
        mod.register_tool(greet)
        assert mod.get_tool("greet") is not None
        assert len(mod.list_tools()) == 6

    async def test_call_facade(self) -> None:
        mod = MCPToolGatewayModule()
        await mod.initialize()
        assert mod.call_tool("echo", {"text": "module"}) == "module"

    async def test_unregister_facade(self) -> None:
        mod = MCPToolGatewayModule()
        await mod.initialize()
        mod.register_tool(greet)
        assert mod.unregister_tool("greet") is True
        assert mod.get_tool("greet") is None

    async def test_operation_before_init_raises(self) -> None:
        mod = MCPToolGatewayModule()
        with pytest.raises(RuntimeError, match="not initialized"):
            mod.call_tool("echo", {"text": "x"})
        with pytest.raises(RuntimeError, match="not initialized"):
            mod.list_tools()

    async def test_call_emits_event(self) -> None:
        bus = EventBus(config={"async_dispatch": False})
        received: list[str] = []

        @bus.subscribe("mcp_tools.tool.called")
        def _on_called(event: Any) -> None:
            received.append(event.topic)

        mod = MCPToolGatewayModule()
        mod.set_event_bus(bus)
        await mod.initialize()
        mod.call_tool("echo", {"text": "hi"})
        assert "mcp_tools.tool.called" in received

    async def test_registered_with_platform(self) -> None:
        from enterprise.platform_kernel import _MODULE_REGISTRY

        assert "mcp_tools" in _MODULE_REGISTRY
        cls = _MODULE_REGISTRY["mcp_tools"]
        assert issubclass(cls, MCPToolGatewayModule)

    async def test_handle_request_through_module(self) -> None:
        mod = MCPToolGatewayModule()
        await mod.initialize()
        response = await mod.handle_request(
            "tools/call", {"name": "echo", "arguments": {"text": "wire"}}, request_id=9
        )
        assert response["result"]["content"][0]["text"] == "wire"
