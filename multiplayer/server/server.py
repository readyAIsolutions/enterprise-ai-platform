"""Multiplayer coordination server.

Accepts long-running builder clients over WebSocket, brokers tasks to them by
capacity, collects work_start/work_log/artifact/work_result streams, and serves
an HTTP front-end (health, live board, submit) for dashboards and operators.

Transports:
  * WebSocket (`ws://host:PORT/ws`) — the client channel (websockets lib here).
  * HTTP (`http://host:PORT+1/api/...`) — operator/dashboard API (stdlib).

Security: the server NEVER receives API keys. Clients send only *capabilities*
(model names, provider names, hardware). Task prompts may carry placeholder refs
(`{KEY:name}`) resolved client-side; the server forwards opaque strings.

IMPORTANT: every Board/Broker method in this codebase is an **async** coroutine —
the event loop must await them all.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any, Dict, Optional

from ..protocol import PROTOCOL_VERSION, TaskState, decode, make_message
from .broker import Broker, HEARTBEAT_TIMEOUT, run_assign_loop
from .state import Board, ClientRecord, new_id

logger = logging.getLogger("eni.mp.server")

FRAME_LOG_LIMIT = 4000


class MultiplayerServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 8787,
                 data_dir: Optional[str] = None) -> None:
        self.host = host
        self.port = port
        self.data_dir = data_dir or os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "data", "multiplayer"))
        os.makedirs(self.data_dir, exist_ok=True)
        self.board = Board()
        # Wire broker->client delivery through the server's socket registry.
        self.broker = Broker(self.board, self.data_dir,
                             on_send=self._broker_deliver)
        self._conn_ws: Dict[str, str] = {}   # client_id -> ephemeral, values: ws id (unused)
        self._ws_by_client: Dict[str, Any] = {}
        self._httpd_api: Optional[ThreadingHTTPServer] = None

    # ------------------------------------------------------------- helpers
    def _broker_deliver(self, client_id: str, message: Dict[str, Any]) -> None:
        """Callback the Broker calls to push a message to a client. Schedules on
        the server's running event loop (Broker.assign may be awaited from a
        worker thread via the HTTP API)."""
        ws = self._ws_by_client.get(client_id)
        if ws is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._send(client_id, message))

    def _workspace_dir(self) -> str:
        return os.path.normpath(os.path.join(self.data_dir, "wspace"))

    # -------------------------------------------------------- client events
    async def _handle_message(self, client_id: str, msg: Dict[str, Any]) -> None:
        kind = msg.get("type", "")
        if kind == "hello":
            await self._hello(client_id, msg)
        elif kind == "work_start":
            tid = msg.get("task_id", "")
            await self.board.set_status(tid, TaskState.RUNNING)
            await self.board.update_task(tid, started_at=time.time())
            await self.board.log("work_start", tid, client_id, "client picked up task")
        elif kind == "work_log":
            tid = msg.get("task_id", "")
            chunk = msg.get("chunk", "")
            rec = await self.board.get_task(tid)
            if rec is not None:
                rec.stdout = (rec.stdout + chunk)[-FRAME_LOG_LIMIT:]
                await self.board.update_task(tid, stdout=rec.stdout)
        elif kind == "work_result":
            await self._work_result(client_id, msg)
        elif kind == "heartbeat":
            await self.board.touch_client(client_id, time.time())

    async def _hello(self, client_id: str, msg: Dict[str, Any]) -> None:
        cap = msg.get("capabilities", {}) or {}
        mach = msg.get("machine", {}) or {}
        rec = ClientRecord(
            client_id=client_id,
            connected_at=time.time(),
            last_seen=time.time(),
            hostname=mach.get("hostname", client_id),
            max_concurrent_tasks=int(cap.get("max_concurrent_tasks", 2) or 2),
            models=cap.get("models", []) or [],
            providers=cap.get("providers", []) or [],
            tags=cap.get("tags", []) or [],
            gpu=bool(cap.get("gpu")),
            running=[],
            transport="ws",
        )
        await self.board.add_client(rec)
        await self.board.log("hello", "", client_id, "client registered", str(mach))
        await self._send(client_id, make_message(
            "welcome", server_id="mp-server", server_version=PROTOCOL_VERSION,
            assigned_client_id=client_id, note="hello accepted"))
        await self.broker.assign()

    async def _work_result(self, client_id: str, msg: Dict[str, Any]) -> None:
        tid = msg.get("task_id", "")
        ok = msg.get("status", "") == "completed"
        artifacts = msg.get("artifacts", []) or []
        rec = await self.board.get_task(tid)
        if rec is not None:
            await self.board.update_task(
                tid, result_status="completed" if ok else "failed",
                completed_at=time.time(), summary=msg.get("summary", ""),
                assigned_client=client_id)
            if ok:
                from .workspace_merge import apply_artifacts
                ws = os.path.join(self._workspace_dir(), "default")
                os.makedirs(ws, exist_ok=True)
                ledger = os.path.join(self.data_dir, "work_merge.ledger")
                merged = apply_artifacts(ws, artifacts, ledger_path=ledger,
                                         task_id=tid, client_id=client_id)
                await self.board.update_task(
                    tid, merged_paths=merged.get("written", []),
                    conflicts=merged.get("conflicts", []))
                await self.board.log(
                    "merged", tid, client_id,
                    f"integrated {len(merged.get('written', []))} artifacts, "
                    f"{len(merged.get('conflicts', []))} conflicts")
            else:
                await self.board.log("failed", tid, client_id, "task failed",
                                     msg.get("error", ""))
            await self.board.set_status(tid, TaskState.COMPLETED if ok else TaskState.FAILED)
        await self.broker.assign()

    async def _send(self, client_id: str, msg: Dict[str, Any]) -> None:
        ws = self._ws_by_client.get(client_id)
        if ws is None:
            return
        try:
            await ws.send(json.dumps(msg))
        except Exception:
            pass

    # ------------------------------------------------------------- snapshot
    async def board_snapshot(self) -> Dict[str, Any]:
        snap = await self.board.board_snapshot()
        snap["server_version"] = PROTOCOL_VERSION
        snap["heartbeat_timeout"] = HEARTBEAT_TIMEOUT
        return snap

    async def submit(self, goal: str, **fields) -> Dict[str, Any]:
        rec = await self.broker.submit(goal, **fields)
        return {"task_id": rec.task_id, "status": rec.status.value, "goal": rec.goal}


def _request_handler_factory(server: MultiplayerServer):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, code: int, obj: Any) -> None:
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/health", "/health/"):
                try:
                    import asyncio as _a
                    snap = _a.run(server.board_snapshot())
                    self._json(200, {"status": "ok", "uptime": time.time(),
                                     "clients": len(snap.get("clients", [])),
                                     "queue": len(snap.get("queued_ids", []))})
                except Exception as exc:
                    self._json(200, {"status": "ok", "note": str(exc)})
            elif self.path.startswith("/api/board"):
                snap = _loop_run(server.board_snapshot())
                self._json(200, snap)
            elif self.path.startswith("/api/ledger"):
                snap = _loop_run(server.board.ledger())
                self._json(200, snap)
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self):
            if self.path.startswith("/api/submit"):
                try:
                    n = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(n) or b"{}")
                except Exception:
                    body = {}
                goal = body.get("goal", "")
                if not goal:
                    self._json(400, {"error": "missing 'goal'"})
                    return
                res = _loop_run(server.submit(
                    goal,
                    prompt=body.get("prompt", ""),
                    repo=body.get("repo", ""),
                    artifacts=body.get("artifacts", []),
                    model_hint=body.get("model_hint", "")))
                # assignment happens on the main loop's run_assign_loop task
                self._json(200, res)
            else:
                self._json(404, {"error": "not found"})

    return Handler


def _loop_run(coro):
    """Run a coroutine synchronously in a throwaway event loop (HTTP thread)."""
    import asyncio as _a
    async def _wrap():
        return await coro
    return _a.run(_wrap())


async def _reap(server: MultiplayerServer) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_TIMEOUT / 2)
        try:
            await server.broker.check_heartbeats()
        except Exception:
            pass


async def _ws_handler(server: MultiplayerServer, websocket) -> None:
    # temp id until the client's hello tells us its real id
    import uuid
    client_id = "tmp-" + uuid.uuid4().hex[:6]
    try:
        server._ws_by_client[client_id] = websocket
        async for raw in websocket:
            try:
                msg = decode(raw)
            except Exception as exc:
                await _safe_send_ws(websocket, make_message("error", message=f"bad frame: {exc}"))
                continue
            cid = msg.get("client_id")
            # the hello carries the authoritative client_id; adopt it.
            if msg.get("type") == "hello" and cid:
                server._ws_by_client.pop(client_id, None)
                client_id = cid
                server._ws_by_client[cid] = websocket
            await server._handle_message(client_id, msg)
    except Exception as exc:
        logger.info("ws %s dropped: %s", client_id, exc)
    finally:
        server._ws_by_client.pop(client_id, None)
        try:
            await server.broker.check_heartbeats()
        except Exception:
            pass


async def _safe_send_ws(ws, msg) -> None:
    try:
        await ws.send(json.dumps(msg))
    except Exception:
        pass


def websocket_handler(server: MultiplayerServer):
    """Return an async handler that tolerates both the modern websockets
    signature ``(ws)`` and the older ``(ws, path)``."""
    async def _adapt(ws, path=None):
        await _ws_handler(server, ws)
    return _adapt


def run(host: str = "127.0.0.1", port: int = 8787, data_dir: Optional[str] = None) -> None:
    """Run the server (blocking). WS on `port`, HTTP API on `port+1`."""
    import websockets
    server = MultiplayerServer(host, port, data_dir)

    http_port = port + 1
    api_httpd = ThreadingHTTPServer((host, http_port), _request_handler_factory(server))
    Thread(target=api_httpd.serve_forever, daemon=True).start()

    async def main():
        await server.broker.resume_from_disk()
        serve = websockets.serve(websocket_handler(server),
                                 host, port, ping_interval=25)
        await serve
        asyncio.ensure_future(_reap(server))
        # The assign loop drives QUEUED -> ASSIGNED on the MAIN event loop so
        # broker delivery reaches the websocket correctly.
        loop_stop = asyncio.Event()
        asyncio.ensure_future(run_assign_loop(server.broker, interval=1.0,
                                              stop=loop_stop))
        print(f"Multiplayer server ready: ws://{host}:{port}  http://{host}:{http_port}")
        print(f"  health http://{host}:{http_port}/health")
        print(f"  board  http://{host}:{http_port}/api/board")
        print(f"  submit POST http://{host}:{http_port}/api/submit  {{'goal': '...'}}")
        await asyncio.Future()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nserver stopped")
        api_httpd.shutdown()


if __name__ == "__main__":
    import sys
    run(port=int(sys.argv[1]) if len(sys.argv) > 1 else 8787)