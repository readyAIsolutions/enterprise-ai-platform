"""Local HTTP controller for the one-prompt-program brain.

INTENT
------
A tiny, stdlib-only local HTTP server (http.server) that exposes the local
brains as clear JSON endpoints the platform's hermes_controller (or Hermes
itself) can call. Everything runs on the local machine; the ONLY permitted
outbound network call is an explicitly-injected external LLM post in
:mod:`build_provider`, and that body is always passed through
:func:`vault.redact` first so no real secret ever leaves.

Endpoints:
  POST /plan     {goal}                 -> {plan:[...], steps:N}
  POST /enrich   {prompt, [?goal]}     -> {prompt: big_prompt}
  POST /program  {goal}                 -> {session_id, artifacts, logs, ...}
  GET  /health                          -> {status, uptime, endpoints:[...], port}

Default port is 8913; if it is already taken the server announces the conflict
and falls back to 8914.
"""

from __future__ import annotations

import argparse
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional

from local_controller import planner
from local_controller.build_provider import BuildProvider

_DEFAULT_PORT = 8913
_FALLBACK_PORT = 8914


def _port_available(port: int) -> bool:
    """Return True if a TCP bind on 127.0.0.1:<port> succeeds."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def choose_port(preferred: int = _DEFAULT_PORT) -> int:
    """Pick ``preferred`` if free, else announce conflict and return fallback."""
    if _port_available(preferred):
        return preferred
    print(
        f"[controller] port {preferred} is busy - falling back to {_FALLBACK_PORT}"
    )
    return _FALLBACK_PORT


def _read_json(body: bytes) -> Dict[str, Any]:
    try:
        return json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return {"_error": f"invalid JSON: {exc}"}


class ControllerHandler(BaseHTTPRequestHandler):
    """HTTP handler dispatching /plan /enrich /program /health."""

    server: "LocalControllerServer"
    server_version = "LocalController/1.0"

    def _send(self, code: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -- routing ------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 - http.server API name
        if self.path.split("?")[0] == "/health":
            self._handle_health()
        else:
            self._send(
                404,
                {
                    "error": "not found",
                    "endpoints": ["/health", "/plan", "/enrich", "/program"],
                },
            )

    def do_POST(self) -> None:  # noqa: N802 - http.server API name
        path = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        if path == "/plan":
            self._handle_plan(body)
        elif path == "/enrich":
            self._handle_enrich(body)
        elif path == "/program":
            self._handle_program(body)
        else:
            self._send(404, {"error": "not found", "path": self.path})

    # -- handlers -----------------------------------------------------------

    def _handle_health(self) -> None:
        self._send(
            200,
            {
                "status": "ok",
                "uptime_seconds": round(self.server.uptime_seconds(), 2),
                "port": self.server.port,
                "endpoints": ["/plan", "/enrich", "/program", "/health"],
            },
        )

    def _handle_plan(self, body: bytes) -> None:
        data = _read_json(body)
        if "_error" in data:
            self._send(400, data)
            return
        goal = str(data.get("goal", ""))
        try:
            plan = planner.parse_goal(goal)
            self._send(
                200,
                {
                    "goal": plan.goal,
                    "steps": len(plan.tasks),
                    "plan": [t.to_dict() for t in plan.tasks],
                },
            )
        except Exception as exc:  # noqa: BLE001
            self._send(500, {"error": str(exc)})

    def _handle_enrich(self, body: bytes) -> None:
        data = _read_json(body)
        if "_error" in data:
            self._send(400, data)
            return
        prompt = str(data.get("prompt", ""))
        goal = str(data.get("goal", ""))
        big = planner.enrich_prompt(prompt, goal=goal)
        self._send(200, {"prompt": big, "source_length": len(prompt),
                         "enriched_length": len(big)})

    def _handle_program(self, body: bytes) -> None:
        data = _read_json(body)
        if "_error" in data:
            self._send(400, data)
            return
        goal = str(data.get("goal", ""))
        url = data.get("llm_url")  # optional explicit external LLM inject
        key_env = data.get("key_env")
        try:
            result = self.server.provider.run_plan(
                goal=goal, url=url or None, key_env=key_env or None
            )
            self._send(200, result)
        except Exception as exc:  # noqa: BLE001
            self._send(500, {"error": str(exc)})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # Keep controller logs tidy; do not print request bodies/keys.
        print(f"[controller] {time.strftime('%H:%M:%S')} {format % args}")


class LocalControllerServer(ThreadingHTTPServer):
    """Threaded HTTP server that owns startup time + a shared BuildProvider."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        port: int = _DEFAULT_PORT,
        provider: Optional[BuildProvider] = None,
    ) -> None:
        super().__init__(("127.0.0.1", port), ControllerHandler)
        self.port = port
        self.provider = provider or BuildProvider()
        self._started = time.time()

    def uptime_seconds(self) -> float:
        return time.time() - self._started

    def serve_forever_clean(self) -> None:
        try:
            self.serve_forever()
        finally:
            self.server_close()


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Local one-prompt-program controller")
    parser.add_argument("--port", type=int, default=_DEFAULT_PORT,
                        help=f"port (default {_DEFAULT_PORT})")
    args = parser.parse_args()
    port = choose_port(args.port)
    srv = LocalControllerServer(port=port)
    print(f"[controller] listening on http://127.0.0.1:{port}")
    print(f"[controller] health:  GET  /health")
    print(f"[controller] plan:    POST /plan")
    print(f"[controller] enrich:  POST /enrich")
    print(f"[controller] program: POST /program")
    try:
        srv.serve_forever_clean()
    except KeyboardInterrupt:
        print("[controller] shutting down")


if __name__ == "__main__":
    main()