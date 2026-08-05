"""Master-class tests for the FastMCP-style layer + pluggable transports.

These tests cover the additions built on top of the existing registry:

  - ``@server.tool`` decorator + auto-derived JSON Schema (types, required,
    default, description) — matching a sample function exactly.
  - Transparent sync + async handler dispatch.
  - ``server.call`` dispatch + errors (unknown tool / bad args / tool raised).
  - ``server.list()`` returning auto-built schemas.
  - Pluggable ``Transport`` ABC, both ``MemoryTransport`` and
    ``StdioTransport`` round-trips (object-level).
  - JSON-RPC ``tools/list`` / ``tools/call`` wiring through the ToolServer.
  - ``create_mcp_tools_module`` factory + module lifecycle.

Run with:
    python3 -m pytest modules/mcp_tools/tests -q
"""

from __future__ import annotations

import asyncio
import io
import json
from typing import Any

import pytest

from enterprise.modules.mcp_tools import (
    MCPToolGatewayModule,
    MemoryTransport,
    StdioTransport,
    Tool,
    ToolCallError,
    ToolServer,
    Transport,
    ValidationError,
    create_mcp_tools_module,
)
from enterprise.platform_kernel import HealthStatus


# ---------------------------------------------------------------------------
# Sample function used to assert exact schema derivation
# ---------------------------------------------------------------------------


def sample(
    text: str,
    count: int,
    ratio: float,
    enabled: bool,
    labels: list[str],
    meta: dict[str, Any],
    level: int = 3,
) -> str:
    """Compute a sample result.

    :param text: the input text.
    :param count: how many repetitions.
    :param ratio: a scaling ratio.
    :param enabled: whether enabled.
    :param labels: tag labels.
    :param meta: extra metadata.
    :param level: verbosity level.
    """
    return text * count


async def async_sum(values: list[int]) -> int:
    """Async tool summing a list of ints."""
    await asyncio.sleep(0)
    return sum(values)


def boom(a: int) -> int:
    """Raise an exception to verify tool-raised error handling."""
    raise RuntimeError("boom exploded")


# ---------------------------------------------------------------------------
# ToolServer @tool decorator + auto schema derivation
# ---------------------------------------------------------------------------


class TestToolServerSchema:
    def _server(self) -> ToolServer:
        server = ToolServer(name="mcp")

        @server.tool(description="Sample tool for schema checks.")
        def wrapper(**kwargs: Any) -> str:  # pragma: no cover - placeholder
            return ""

        return server

    def test_schema_matches_sample_function(self) -> None:
        server = ToolServer()
        registered = server.register(sample)
        schema = registered.input_schema
        props = schema["properties"]

        assert schema["type"] == "object"
        assert props["text"]["type"] == "string"
        assert props["count"]["type"] == "integer"
        assert props["ratio"]["type"] == "number"
        assert props["enabled"]["type"] == "boolean"
        assert props["labels"]["type"] == "array"
        assert props["meta"]["type"] == "object"

        # Required: level has a default -> not required.
        assert set(schema["required"]) == {"text", "count", "ratio", "enabled", "labels", "meta"}
        assert props["level"]["required"] is False
        assert props["text"]["required"] is True

    def test_schema_includes_default_value(self) -> None:
        server = ToolServer()
        registered = server.register(sample)
        prop = registered.input_schema["properties"]["level"]
        assert prop["default"] == 3

    def test_schema_includes_param_description_from_docstring(self) -> None:
        server = ToolServer()
        registered = server.register(sample)
        desc = registered.input_schema["properties"]["text"]["description"]
        assert "input text" in desc

    def test_tool_decorator_sets_description_and_tags(self) -> None:
        server = ToolServer()

        @server.tool(description="Add two numbers.", tags=["math"])
        def addx(a: int, b: int) -> int:
            return a + b

        t = server.get("addx")
        assert t is not None
        assert t.description == "Add two numbers."
        assert t.tags == ["math"]

    def test_tool_decorator_bare_usage(self) -> None:
        server = ToolServer()

        @server.tool
        def bare_tool(v: int) -> int:
            return v

        assert server.has("bare_tool")
        assert isinstance(server.get("bare_tool"), Tool)

    def test_tool_decorator_name_override(self) -> None:
        server = ToolServer()

        @server.tool(name="renamed_tool")
        def original(x: int) -> int:
            return x

        assert server.has("renamed_tool")
        assert not server.has("original")

    def test_decorated_function_stays_callable(self) -> None:
        server = ToolServer()

        @server.tool(description="multiply")
        def mul(a: int, b: int) -> int:
            return a * b

        assert mul(2, 3) == 6
        assert mul._mcp_tool is server.get("mul")  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Dispatch: sync + async transparently, error handling
# ---------------------------------------------------------------------------


class TestToolServerDispatch:
    def test_call_sync_tool(self) -> None:
        server = ToolServer()
        server.register(sample)
        args = {"text": "hi", "count": 2, "ratio": 1.0, "enabled": True,
                "labels": ["a"], "meta": {}}
        assert server.call("sample", args) == "hihi"

    def test_call_async_tool_transparently(self) -> None:
        server = ToolServer()
        server.register(async_sum)
        assert server.call("async_sum", {"values": [1, 2, 3]}) == 6

    async def test_acall_async_tool(self) -> None:
        server = ToolServer()
        server.register(async_sum)
        assert await server.acall("async_sum", {"values": [1, 2, 3]}) == 6

    async def test_acall_sync_tool(self) -> None:
        server = ToolServer()
        server.register(sample)
        args = {"text": "x", "count": 3, "ratio": 1.0, "enabled": True,
                "labels": ["a"], "meta": {}}
        assert await server.acall("sample", args) == "xxx"

    def test_call_unknown_tool_raises(self) -> None:
        server = ToolServer()
        with pytest.raises(ToolCallError, match="Unknown tool"):
            server.call("nope")

    def test_call_bad_args_raises(self) -> None:
        server = ToolServer()
        server.register(sample)
        with pytest.raises(ValidationError, match="Missing required argument"):
            server.call("sample", {"text": "hi"})

    def test_call_tool_raised_error_propagates(self) -> None:
        server = ToolServer()
        server.register(boom)
        with pytest.raises(RuntimeError, match="boom exploded"):
            server.call("boom", {"a": 1})

    def test_list_returns_auto_built_schemas(self) -> None:
        server = ToolServer()
        server.register(sample)
        listed = server.list()
        assert len(listed) == 1
        payload = json.dumps(listed)  # must be JSON serializable
        assert isinstance(payload, str)
        assert listed[0]["name"] == "sample"
        assert "inputSchema" in listed[0]

    def test_list_after_multiple_registrations_sorted(self) -> None:
        server = ToolServer()
        server.register(sample)

        @server.tool
        def zeta(v: int) -> int:
            return v

        names = [entry["name"] for entry in server.list()]
        assert names == sorted(names)
        assert len(names) == 2


# ---------------------------------------------------------------------------
# Pluggable transports
# ---------------------------------------------------------------------------


class TestTransports:
    def test_transport_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            Transport()  # type: ignore[abstract]

    def test_memory_transport_roundtrip_object(self) -> None:
        client, server_end = MemoryTransport(), MemoryTransport()
        client.connect(server_end)

        client.send({"jsonrpc": "2.0", "id": 1, "method": "ping"})
        received = server_end.receive()
        assert received == {"jsonrpc": "2.0", "id": 1, "method": "ping"}

        server_end.send({"jsonrpc": "2.0", "id": 1, "result": "pong"})
        assert client.receive()["result"] == "pong"

    def test_memory_transport_unconnected_raises(self) -> None:
        client = MemoryTransport()
        with pytest.raises(RuntimeError, match="not connected"):
            client.send({"method": "x"})

    def test_memory_transport_receive_empty_returns_none(self) -> None:
        client = MemoryTransport()
        assert client.receive() is None

    def test_remote_call_over_memory_transport(self) -> None:
        client, server_end = MemoryTransport(), MemoryTransport()
        client.connect(server_end)
        server = ToolServer()
        server.register(sample)

        client.send(
            {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
             "params": {"name": "sample",
                        "arguments": {"text": "ab", "count": 2, "ratio": 1.0,
                                      "enabled": True, "labels": ["a"], "meta": {}}}}
        )
        request = server_end.receive()
        response = asyncio.run(
            server.handle_request(request["method"], params=request["params"], request_id=request["id"])
        )
        server_end.send(response)
        reply = client.receive()
        assert reply["id"] == 7
        assert reply["result"]["content"][0]["text"] == "abab"

    def test_stdio_transport_roundtrip_object(self) -> None:
        server = ToolServer()
        server.register(sample)

        request = json.dumps(
            {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}
        ) + "\n"
        stdin = io.StringIO(request)
        stdout = io.StringIO()
        transport = StdioTransport(stdin=stdin, stdout=stdout)

        msg = transport.receive()
        response = asyncio.run(
            server.handle_request(msg["method"], params=msg.get("params"), request_id=msg["id"])
        )
        transport.send(response)

        reply = json.loads(stdout.getvalue())
        assert reply["id"] == 3
        assert reply["method"] == "tools/list"
        assert any(t["name"] == "sample" for t in reply["result"]["tools"])

    def test_stdio_transport_invalid_json_raises(self) -> None:
        stdin = io.StringIO("this is not json\n")
        transport = StdioTransport(stdin=stdin, stdout=io.StringIO())
        with pytest.raises(ValueError, match="Invalid JSON-RPC"):
            transport.receive()

    def test_stdio_transport_eof_returns_none(self) -> None:
        transport = StdioTransport(stdin=io.StringIO(""), stdout=io.StringIO())
        assert transport.receive() is None
        assert transport.receive() is None  # stays EOF


# ---------------------------------------------------------------------------
# JSON-RPC wire layer through ToolServer
# ---------------------------------------------------------------------------


class TestToolServerMCPWire:
    def _server(self) -> ToolServer:
        server = ToolServer()
        server.register(sample)

        @server.tool(description="Greet someone.")
        def greet(name: str) -> str:
            """:param name: who to greet."""
            return f"Hello {name}"

        return server

    async def test_handle_tools_list(self) -> None:
        response = await self._server().handle_request("tools/list", request_id=1)
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert response["method"] == "tools/list"
        assert len(response["result"]["tools"]) == 2

    async def test_handle_tools_call_success(self) -> None:
        response = await self._server().handle_request(
            "tools/call",
            {"name": "greet", "arguments": {"name": "Noor"}},
            request_id=2,
        )
        assert response["method"] == "tools/call"
        assert response["result"]["isError"] is False
        assert response["result"]["content"][0]["text"] == "Hello Noor"

    async def test_handle_call_unknown_tool(self) -> None:
        response = await self._server().handle_request(
            "tools/call", {"name": "missing", "arguments": {}}, request_id=3
        )
        assert response["error"]["code"] == -32602
        assert "Unknown tool" in response["error"]["message"]

    async def test_handle_call_validation_error(self) -> None:
        response = await self._server().handle_request(
            "tools/call", {"name": "greet", "arguments": {}}, request_id=4
        )
        assert response["error"]["code"] == -32602

    async def test_handle_call_tool_raised_wrapped(self) -> None:
        server = ToolServer()
        server.register(boom)
        response = await server.handle_request(
            "tools/call", {"name": "boom", "arguments": {"a": 1}}, request_id=5
        )
        assert response["error"]["code"] == -32602
        assert "Tool execution failed" in response["error"]["message"]

    async def test_handle_unknown_method(self) -> None:
        response = await self._server().handle_request("bogus/method", request_id=6)
        assert response["error"]["code"] == -32601


# ---------------------------------------------------------------------------
# Module factory + lifecycle
# ---------------------------------------------------------------------------


class TestModuleFactory:
    async def test_create_module_factory_returns_module(self) -> None:
        mod = create_mcp_tools_module({"max_tools": 25})
        assert isinstance(mod, MCPToolGatewayModule)
        assert mod.max_tools == 25

    async def test_create_module_factory_lifecycle(self) -> None:
        mod = create_mcp_tools_module()
        assert await mod.health_check() is HealthStatus.UNKNOWN
        await mod.initialize()
        assert mod.status is HealthStatus.HEALTHY
        assert mod.registry is not None
        assert mod.registry.count() == 5
        await mod.shutdown()
        assert mod.registry is None

    async def test_create_module_factory_default_max_tools(self) -> None:
        assert create_mcp_tools_module().max_tools == 1000
