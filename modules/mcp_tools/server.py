"""MCP Transport Servers — real socket HTTP + SSE + stdio over the ToolServer.

This module turns the existing in-process :class:`~.ToolServer` (which already
speaks JSON-RPC 2.0 for ``tools/list`` / ``tools/call``) into something that
*literally listens on a socket* — no stubs:

* :class:`MCPServer` — wraps a :class:`~.ToolServer` and exposes:
    - ``POST /mcp``  — handles JSON-RPC ``tools/list`` / ``tools/call`` and
      returns the MCP / JSON-RPC 2.0 responses (real HTTP, stdlib
      ``ThreadingHTTPServer``).
    - ``GET /mcp``   — lightweight server-info handshake.
    - ``GET /health``— opaque health check (status / tool count).
    - ``POST /sse``  — returns the response streamed as ``text/event-stream``
      via :class:`SSETransport`.
  It runs on an ephemeral port when ``port=0`` (OS-assigned) and can be
  started/stopped in-process for hermetic tests.
* :class:`SSETransport` — generator-based Server-Sent Events writer. Yields
  ``text/event-stream`` frames and, for ``tools/call``, emits a ``progress``
  event before the final ``message`` event (notably for async handlers).
* :class:`StdioServer` — reads JSON-RPC 2.0 lines from ``stdin`` and writes
  responses to ``stdout``, giving MCP-over-stdio / mapper conformance.
* :func:`serve` — convenience helper that starts an HTTP :class:`MCPServer` on
  a port for a given :class:`~.ToolServer` + config, returning the running
  server (call ``.shutdown()`` when done).

Stdlib only; works on Python 3.11+.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .mcp_tools import StdioTransport, ToolServer, Transport

_logger = logging.getLogger("enterprise.mcp_tools.server")

_JSONRPC_VERSION = "2.0"

SSE_CONTENT_TYPE = "text/event-stream"


# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------


def _json_rpc_response(
    request_id: Any,
    *,
    result: Any = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 success or error envelope."""
    response: dict[str, Any] = {"jsonrpc": _JSONRPC_VERSION, "id": request_id}
    if error is not None:
        response["error"] = error
    else:
        response["result"] = result
    return response


def _parse_error(request_id: Any = None, message: str = "Parse error") -> dict[str, Any]:
    return _json_rpc_response(request_id, error={"code": -32700, "message": message})


def _invalid_request(request_id: Any = None, message: str = "Invalid Request") -> dict[str, Any]:
    return _json_rpc_response(request_id, error={"code": -32600, "message": message})


# ---------------------------------------------------------------------------
# MCPServer — wraps a ToolServer and serves it over real HTTP
# ---------------------------------------------------------------------------


class _MCPHTTPHandler(BaseHTTPRequestHandler):
    """HTTP handler bound to an :class:`MCPServer`.

    ``self.server.mcp`` is the parent MCPServer (set by the factory). All
    responses use HTTP/1.1 keep-alive so a single socket can service many
    requests.
    """

    protocol_version = "HTTP/1.1"
    server_version = "MCPTools/1.0"

    # -- plumbing ---------------------------------------------------------

    @property
    def _mcp(self) -> MCPServer:
        return self.server.mcp  # type: ignore[attr-defined]

    def _send_bytes(
        self, body: bytes, status: int = 200, content_type: str = "application/json"
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self._send_bytes(body, status=status, content_type="application/json")

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length <= 0:
            return b""
        return self.rfile.read(length)

    def _parse_body(self) -> Any | None:
        """Parse the request body into JSON, or None if the JSON is malformed."""
        raw = self._read_body()
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        _logger.debug("HTTP %s", format % args)

    # -- routes -----------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/health":
            self._send_json(self._mcp.health())
        elif path == "/mcp":
            self._send_json(
                {
                    "jsonrpc": _JSONRPC_VERSION,
                    "id": None,
                    "result": {
                        "serverInfo": {
                            "name": self._mcp.name,
                            "version": self._mcp.version,
                            "tools": self._mcp.tool_server.count(),
                        }
                    },
                }
            )
        else:
            self._send_json(_invalid_request(None, "Not Found"), status=404)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/mcp":
            payload = self._parse_body()
            if payload is None:
                self._send_json(_parse_error(None, "Malformed JSON request"), status=400)
                return
            response = self._mcp.process_message(payload)
            self._send_json(response)
        elif path == "/sse":
            payload = self._parse_body()
            if payload is None:
                self._send_json(_parse_error(None, "Malformed JSON request"), status=400)
                return
            transport = SSETransport(self._mcp)
            self.send_response(200)
            self.send_header("Content-Type", SSE_CONTENT_TYPE)
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                for frame in transport.stream(payload):
                    self.wfile.write(frame)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                _logger.debug("SSE client disconnected mid-stream")
        else:
            self._send_json(_invalid_request(None, "Not Found"), status=404)


class MCPServer:
    """Real HTTP MCP server wrapping a :class:`~.ToolServer`.

        server = MCPServer(tool_server)
        server.start(host="127.0.0.1", port=0)   # ephemeral port
        print(server.port)                        # OS-assigned port
        response = await server.handle_request("tools/list")  # direct in-proc
        server.shutdown()

    ``process_message`` is a fully synchronous JSON-RPC dispatcher so it can be
    driven from threads (HTTP handler, stdio loop) as well as async callers.
    """

    def __init__(
        self,
        tool_server: ToolServer | None = None,
        *,
        name: str | None = None,
        version: str = "1.0.0",
    ) -> None:
        self.tool_server = tool_server if tool_server is not None else ToolServer()
        self.name = name or self.tool_server.name
        self.version = version
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.port: int | None = None

    # -- JSON-RPC dispatch (sync, thread-safe per request) ------------------

    def process_message(self, payload: Any) -> dict[str, Any]:
        """Dispatch a full JSON-RPC request message and return its response.

        Handles ``tools/list``, ``tools/call`` and unknown methods, surfacing
        tool/validation failures as JSON-RPC error responses (never raising).
        This is the sync entry-point used by the HTTP handler and stdio loop.
        """
        if not isinstance(payload, dict):
            return _invalid_request(None)
        if payload.get("jsonrpc") != _JSONRPC_VERSION:
            return _invalid_request(payload.get("id"))
        method = payload.get("method")
        if not isinstance(method, str) or not method:
            return _invalid_request(payload.get("id"))
        params = payload.get("params")
        if params is not None and not isinstance(params, dict):
            return _invalid_request(payload.get("id"))
        request_id = payload.get("id")
        try:
            return asyncio.run(
                self.handle_request(method, params=params or {}, request_id=request_id)
            )
        except Exception as exc:  # noqa: BLE001 - never let the wire raise
            _logger.exception("MCP dispatch failed for %r", method)
            return _json_rpc_response(
                request_id, error={"code": -32603, "message": f"Internal error: {exc}"}
            )

    async def handle_request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        request_id: Any = None,
    ) -> dict[str, Any]:
        """Async JSON-RPC dispatch — delegates to :meth:`ToolServer.handle_request`."""
        return await self.tool_server.handle_request(method, params=params, request_id=request_id)

    # -- HTTP lifecycle ----------------------------------------------------

    def start(self, host: str = "127.0.0.1", port: int = 0) -> MCPServer:
        """Start a ThreadingHTTPServer on ``host:port`` in a daemon thread.

        When ``port == 0`` the OS assigns an ephemeral port, available as
        ``self.port``. Returns self for chaining.
        """
        httpd = ThreadingHTTPServer((host, port), _MCPHTTPHandler)
        # Throw away the default '0.0.0.0' log — we wire logging above.
        httpd.mcp = self  # type: ignore[attr-defined]
        self._httpd = httpd
        self.port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self._thread = thread
        _logger.info("MCPServer '%s' listening on http://%s:%s", self.name, host, self.port)
        return self

    def shutdown(self) -> None:
        """Stop the HTTP server and join its thread (no-op if not running)."""
        httpd, self._httpd = self._httpd, None
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        self.port = None

    def health(self) -> dict[str, Any]:
        """Return a small health/status dict for ``GET /health``."""
        return {
            "status": "ok",
            "name": self.name,
            "version": self.version,
            "tools": self.tool_server.count(),
        }


# ---------------------------------------------------------------------------
# SSETransport — Server-Sent Events (text/event-stream) writer
# ---------------------------------------------------------------------------


class SSETransport:
    """Generator-based SSE writer that streams JSON-RPC events as SSE frames.

        transport = SSETransport(mcp_server)
        for frame in transport.stream(payload):   # yields bytes frames
            ...                                    # text/event-stream

    For ``tools/call`` requests the stream first emits a ``progress`` event
    (notably when the target handler is async/coroutine) followed by the final
    ``message`` event carrying the response, so clients see live progress.
    """

    content_type = SSE_CONTENT_TYPE

    def __init__(self, mcp_server: MCPServer | None = None) -> None:
        self.mcp_server = mcp_server

    # -- SSE encoding ------------------------------------------------------

    @staticmethod
    def format_event(data: Any, event: str = "message", event_id: Any = None) -> bytes:
        """Encode ``data`` as one SSE frame (event + data lines + blank line)."""
        lines: list[str] = []
        if event_id is not None:
            lines.append(f"id: {event_id}")
        lines.append(f"event: {event}")
        if not isinstance(data, str):
            data = json.dumps(data, default=str)
        for chunk in data.split("\n"):
            lines.append(f"data: {chunk}")
        return ("\n".join(lines) + "\n\n").encode("utf-8")

    @staticmethod
    def parse_events(raw: str | bytes) -> list[dict[str, Any]]:
        """Parse an SSE byte/str stream into a list of ``{event, data}`` dicts."""
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        events: list[dict[str, Any]] = []
        event_name = "message"
        data_lines: list[str] = []
        for line in raw.split("\n"):
            if line == "":
                if data_lines:
                    events.append({"event": event_name, "data": "\n".join(data_lines)})
                event_name = "message"
                data_lines = []
            elif line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())
        if data_lines:  # trailing frame without blank line
            events.append({"event": event_name, "data": "\n".join(data_lines)})
        return events

    # -- streaming ---------------------------------------------------------

    def _handler_is_async(self, payload: dict[str, Any]) -> bool:
        try:
            name = (payload.get("params") or {}).get("name")
            tool = self.mcp_server.tool_server.get(name) if self.mcp_server else None
        except Exception:  # noqa: BLE001
            return False
        return bool(tool is not None and inspect.iscoroutinefunction(tool.handler))

    def stream(self, request_payload: dict[str, Any] | None) -> Any:
        """Yield SSE frames (bytes) for a single JSON-RPC request.

        For ``tools/call`` an initial ``progress`` event is emitted first
        (always for async handlers), then the ``message`` frame with the result.
        """
        if not isinstance(request_payload, dict):
            yield self.format_event(_parse_error(None, "Not a JSON-RPC request"), event="message")
            return

        method = request_payload.get("method")
        if method == "tools/call":
            name = (request_payload.get("params") or {}).get("name")
            progress_kind = "progress" if self._handler_is_async(request_payload) else "start"
            yield self.format_event(
                {"type": "tools/call", "tool": name, "state": "started"},
                event=progress_kind,
            )

        response = self.mcp_server.process_message(request_payload) if self.mcp_server else {}
        yield self.format_event(response, event="message")


# ---------------------------------------------------------------------------
# StdioServer — MCP over stdio (JSON-RPC 2.0 lines on stdin/stdout)
# ---------------------------------------------------------------------------


class StdioServer:
    """Reads JSON-RPC 2.0 from ``stdin`` and writes responses to ``stdout``.

    Each request/response is a single UTF-8 JSON line, matching the MCP stdio
    / mapper conformance format. ``stdin``/``stdout`` may be injected (e.g.
    ``io.StringIO``) for hermetic round-trip tests.
    """

    def __init__(
        self,
        mcp_server: MCPServer | None = None,
        *,
        stdin: Any = None,
        stdout: Any = None,
    ) -> None:
        self.mcp_server = mcp_server if mcp_server is not None else MCPServer()
        self.transport: Transport = StdioTransport(stdin=stdin, stdout=stdout)

    def handle_message(self, message: dict[str, Any]) -> dict[str, Any]:
        """Dispatch one decoded JSON-RPC request to its response."""
        return self.mcp_server.process_message(message)

    def serve(self) -> None:
        """Run the read/dispatch/write loop until stdin hits EOF."""
        while True:
            message = self.transport.receive()
            if message is None:
                break
            response = self.handle_message(message)
            if response is not None:
                self.transport.send(response)

    def serve_once(self) -> bool:
        """Handle a single request/response round-trip.

        Returns True if a request was processed, False on EOF (nothing left).
        """
        message = self.transport.receive()
        if message is None:
            return False
        response = self.handle_message(message)
        if response is not None:
            self.transport.send(response)
        return True


# ---------------------------------------------------------------------------
# serve() — convenience helper
# ---------------------------------------------------------------------------


def serve(
    tool_server: ToolServer | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    name: str | None = None,
    version: str = "1.0.0",
) -> MCPServer:
    """Start an HTTP :class:`MCPServer` for ``tool_server`` and return it.

    The server is started in a daemon thread on ``host:port`` (port ``0`` uses
    an OS-assigned ephemeral port). The caller must call ``.shutdown()`` when
    done. Example:

        server = serve(my_tool_server, port=0)
        print(server.port)
        ...
        server.shutdown()
    """
    server = MCPServer(tool_server, name=name, version=version)
    return server.start(host=host, port=port)


__all__ = [
    "MCPServer",
    "SSETransport",
    "StdioServer",
    "serve",
    "_MCPHTTPHandler",
]
