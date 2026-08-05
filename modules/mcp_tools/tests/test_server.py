"""Conformance tests for the real MCP transport servers (HTTP + SSE + stdio).

These tests exercise the *socket-level* transports added in ``server.py`` and
are fully hermetic: the HTTP server runs in a daemon thread on an ephemeral
port (``port=0`` -> OS-assigned), is driven in-process via ``http.client``, and
is shut down at the end of every test. No long-lived listeners leak.

Run with:
    python3 -m pytest modules/mcp_tools/tests/test_server.py -q
"""

from __future__ import annotations

import http.client
import io
import json
from typing import Any

import pytest
from enterprise.modules.mcp_tools import ToolServer
from enterprise.modules.mcp_tools.server import (
    MCPServer,
    SSETransport,
    StdioServer,
    serve,
)

# ---------------------------------------------------------------------------
# Example tools
# ---------------------------------------------------------------------------


def _make_server() -> ToolServer:
    tool_server = ToolServer(name="test-mcp")

    @tool_server.tool(description="Add two integers")
    def add(a: int, b: int) -> int:
        return a + b

    @tool_server.tool(description="Greet someone")
    def greet(name: str) -> str:
        return f"Hello {name}"

    @tool_server.tool(description="Async upper")
    async def upper(text: str) -> str:
        return text.upper()

    return tool_server


# ---------------------------------------------------------------------------
# HTTP transport (real socket, in-process client)
# ---------------------------------------------------------------------------


class TestHTTPServer:
    @pytest.fixture
    def mcp(self) -> MCPServer:
        tool_server = _make_server()
        server = MCPServer(tool_server, name="http-mcp")
        server.start(host="127.0.0.1", port=0)
        yield server
        server.shutdown()

    def _post(self, mcp: MCPServer, payload: Any) -> tuple[int, dict[str, Any]]:  # noqa: ANN401
        conn = http.client.HTTPConnection("127.0.0.1", mcp.port, timeout=5)
        try:
            body = json.dumps(payload).encode("utf-8")
            conn.request(
                "POST",
                "/mcp",
                body=body,
                headers={"Content-Type": "application/json"},
            )
            resp = conn.getresponse()
            data = json.loads(resp.read().decode("utf-8"))
            return resp.status, data
        finally:
            conn.close()

    def test_start_binds_ephemeral_port(self, mcp: MCPServer) -> None:
        assert mcp.port is not None
        assert mcp.port > 0
        assert mcp.port <= 65535

    def test_serves_tools_list_over_http(self, mcp: MCPServer) -> None:
        status, resp = self._post(mcp, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert status == 200
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 1
        tools = {t["name"]: t for t in resp["result"]["tools"]}
        assert set(tools) == {"add", "greet", "upper"}
        assert "inputSchema" in tools["add"]

    def test_tools_call_sync_tool_over_http(self, mcp: MCPServer) -> None:
        status, resp = self._post(
            mcp,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "add", "arguments": {"a": 2, "b": 3}},
            },
        )
        assert status == 200
        assert resp["result"]["content"][0]["text"] == "5"
        assert resp["result"]["isError"] is False

    def test_tools_call_async_tool_over_http(self, mcp: MCPServer) -> None:
        status, resp = self._post(
            mcp,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "upper", "arguments": {"text": "abc"}},
            },
        )
        assert status == 200
        assert resp["result"]["content"][0]["text"] == "ABC"

    def test_unknown_tool_returns_jsonrpc_error(self, mcp: MCPServer) -> None:
        status, resp = self._post(
            mcp,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "nope", "arguments": {}},
            },
        )
        assert status == 200
        assert resp["error"]["code"] == -32602

    def test_malformed_json_returns_parse_error(self, mcp: MCPServer) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", mcp.port, timeout=5)
        try:
            conn.request(
                "POST", "/mcp", body="{not-json", headers={"Content-Type": "application/json"}
            )
            resp = conn.getresponse()
            data = json.loads(resp.read().decode("utf-8"))
            assert resp.status == 400
            assert data["error"]["code"] == -32700
        finally:
            conn.close()

    def test_invalid_request_not_object(self, mcp: MCPServer) -> None:
        status, resp = self._post(mcp, [1, 2, 3])
        assert resp["error"]["code"] == -32600

    def test_unknown_method_returns_32601(self, mcp: MCPServer) -> None:
        status, resp = self._post(mcp, {"jsonrpc": "2.0", "id": 5, "method": "bogus/method"})
        assert resp["error"]["code"] == -32601

    def test_health_endpoint(self, mcp: MCPServer) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", mcp.port, timeout=5)
        try:
            conn.request("GET", "/health")
            resp = conn.getresponse()
            data = json.loads(resp.read().decode("utf-8"))
            assert resp.status == 200
            assert data["status"] == "ok"
            assert data["tools"] == 3
        finally:
            conn.close()

    def test_get_mcp_handshake(self, mcp: MCPServer) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", mcp.port, timeout=5)
        try:
            conn.request("GET", "/mcp")
            resp = conn.getresponse()
            data = json.loads(resp.read().decode("utf-8"))
            assert resp.status == 200
            assert data["result"]["serverInfo"]["name"] == "http-mcp"
        finally:
            conn.close()

    def test_shutdown_stops_listener(self) -> None:
        server = MCPServer(_make_server())
        server.start(port=0)
        port = server.port
        server.shutdown()
        assert server.port is None

        def probe() -> None:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            try:
                conn.request("GET", "/health")
                conn.getresponse()
            finally:
                conn.close()

        with pytest.raises((ConnectionRefusedError, OSError)):
            probe()


# ---------------------------------------------------------------------------
# serve() helper
# ---------------------------------------------------------------------------


class TestServeHelper:
    def test_serve_returns_running_http_server(self) -> None:
        tool_server = _make_server()
        server = serve(tool_server, port=0, name="served")
        try:
            assert server.port
            assert server.port > 0
            conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
            try:
                conn.request(
                    "POST",
                    "/mcp",
                    body=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode(),
                    headers={"Content-Type": "application/json"},
                )
                resp = conn.getresponse()
                data = json.loads(resp.read().decode("utf-8"))
                assert len(data["result"]["tools"]) == 3
            finally:
                conn.close()
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# SSETransport
# ---------------------------------------------------------------------------


class TestSSETransport:
    def test_format_event_basic(self) -> None:
        frame = SSETransport.format_event({"a": 1}, event="message")
        text = frame.decode("utf-8")
        assert "event: message" in text
        assert 'data: {"a": 1}' in text
        assert text.endswith("\n\n")

    def test_format_and_parse_roundtrip(self) -> None:
        payload = {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}
        frame = SSETransport.format_event(payload, event="message", event_id="9")
        parsed = SSETransport.parse_events(frame)
        assert len(parsed) == 1
        assert parsed[0]["event"] == "message"
        assert json.loads(parsed[0]["data"]) == payload

    def test_sse_streams_tools_list(self) -> None:
        mcp = MCPServer(_make_server())
        transport = SSETransport(mcp)
        frames = b"".join(transport.stream({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}))
        events = SSETransport.parse_events(frames)
        assert any(json.loads(e["data"]).get("result") for e in events)

    def test_sse_emits_progress_for_async_tool(self) -> None:
        mcp = MCPServer(_make_server())
        transport = SSETransport(mcp)
        frames = b"".join(
            transport.stream(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "upper", "arguments": {"text": "x"}},
                }
            )
        )
        events = SSETransport.parse_events(frames)
        assert events[0]["event"] == "progress"
        final = json.loads(events[-1]["data"])
        assert final["result"]["content"][0]["text"] == "X"

    def test_sse_emits_start_for_sync_tool(self) -> None:
        mcp = MCPServer(_make_server())
        transport = SSETransport(mcp)
        frames = b"".join(
            transport.stream(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "add", "arguments": {"a": 1, "b": 2}},
                }
            )
        )
        events = SSETransport.parse_events(frames)
        assert events[0]["event"] == "start"

    def test_sse_http_endpoint_streams_event_stream(
        self,
    ) -> None:
        tool_server = _make_server()
        server = MCPServer(tool_server)
        server.start(port=0)
        try:
            conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
            try:
                conn.request(
                    "POST",
                    "/sse",
                    body=json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": 7,
                            "method": "tools/call",
                            "params": {"name": "greet", "arguments": {"name": "Zoe"}},
                        }
                    ).encode(),
                    headers={"Content-Type": "application/json"},
                )
                resp = conn.getresponse()
                assert resp.getheader("Content-Type").startswith("text/event-stream")
                body = resp.read().decode("utf-8")
                events = SSETransport.parse_events(body)
                final = json.loads(events[-1]["data"])
                assert final["result"]["content"][0]["text"] == "Hello Zoe"
            finally:
                conn.close()
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# StdioServer
# ---------------------------------------------------------------------------


class TestStdioServer:
    def test_stdio_roundtrip_tools_list(self) -> None:
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        stdin = io.StringIO(json.dumps(request) + "\n")
        stdout = io.StringIO()
        stdio = StdioServer(MCPServer(_make_server()), stdin=stdin, stdout=stdout)
        stdio.serve()
        parsed = json.loads(stdout.getvalue())
        assert parsed["id"] == 1
        assert len(parsed["result"]["tools"]) == 3

    def test_stdio_roundtrip_sync_call(self) -> None:
        request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "add", "arguments": {"a": 10, "b": 5}},
        }
        stdin = io.StringIO(json.dumps(request) + "\n")
        stdout = io.StringIO()
        stdio = StdioServer(MCPServer(_make_server()), stdin=stdin, stdout=stdout)
        stdio.serve()
        parsed = json.loads(stdout.getvalue())
        assert parsed["id"] == 2
        assert parsed["result"]["content"][0]["text"] == "15"

    def test_stdio_multi_request_stream(self) -> None:
        requests = (
            "\n".join(
                json.dumps(r)
                for r in [
                    {"jsonrpc": "2.0", "id": "a", "method": "tools/list"},
                    {
                        "jsonrpc": "2.0",
                        "id": "b",
                        "method": "tools/call",
                        "params": {"name": "upper", "arguments": {"text": "hey"}},
                    },
                ]
            )
            + "\n"
        )
        stdin = io.StringIO(requests)
        stdout = io.StringIO()
        stdio = StdioServer(MCPServer(_make_server()), stdin=stdin, stdout=stdout)
        stdio.serve()
        lines = stdout.getvalue().strip().split("\n")
        assert len(lines) == 2
        first = json.loads(lines[0])
        second = json.loads(lines[1])
        assert first["id"] == "a"
        assert second["result"]["content"][0]["text"] == "HEY"

    def test_stdio_unknown_tool_returns_error(self) -> None:
        request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "missing", "arguments": {}},
        }
        stdin = io.StringIO(json.dumps(request) + "\n")
        stdout = io.StringIO()
        stdio = StdioServer(MCPServer(_make_server()), stdin=stdin, stdout=stdout)
        stdio.serve()
        parsed = json.loads(stdout.getvalue())
        assert parsed["error"]["code"] == -32602

    def test_stdio_serve_once_roundtrip(self) -> None:
        request = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "greet", "arguments": {"name": "Bob"}},
        }
        stdin = io.StringIO(json.dumps(request) + "\n")
        stdout = io.StringIO()
        stdio = StdioServer(MCPServer(_make_server()), stdin=stdin, stdout=stdout)
        assert stdio.serve_once() is True
        parsed = json.loads(stdout.getvalue())
        assert parsed["result"]["content"][0]["text"] == "Hello Bob"
        assert stdio.serve_once() is False  # EOF

    def test_stdio_eof_no_output(self) -> None:
        stdout = io.StringIO()
        stdio = StdioServer(MCPServer(_make_server()), stdin=io.StringIO(""), stdout=stdout)
        stdio.serve()
        assert stdout.getvalue() == ""

    def test_stdio_process_message_direct(self) -> None:
        mcp = MCPServer(_make_server())
        resp = mcp.process_message({"jsonrpc": "2.0", "id": 99, "method": "tools/list"})
        assert resp["id"] == 99
        assert len(resp["result"]["tools"]) == 3


# ---------------------------------------------------------------------------
# MCPServer in-process dispatch (no socket)
# ---------------------------------------------------------------------------


class TestMCPServerDispatch:
    def test_process_message_sync_call(self) -> None:
        mcp = MCPServer(_make_server())
        resp = mcp.process_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "add", "arguments": {"a": 1, "b": 1}},
            }
        )
        assert resp["result"]["content"][0]["text"] == "2"

    def test_process_message_async_call(self) -> None:
        mcp = MCPServer(_make_server())
        resp = mcp.process_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "upper", "arguments": {"text": "hi"}},
            }
        )
        assert resp["result"]["content"][0]["text"] == "HI"

    def test_process_message_non_object(self) -> None:
        mcp = MCPServer(_make_server())
        resp = mcp.process_message("not a dict")
        assert resp["error"]["code"] == -32600

    async def test_handle_request_async(self) -> None:
        mcp = MCPServer(_make_server())
        resp = await mcp.handle_request("tools/list", request_id=5)
        assert resp["id"] == 5
        assert len(resp["result"]["tools"]) == 3
