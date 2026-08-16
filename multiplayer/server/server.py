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
from typing import Any, Dict, List, Optional

from ..protocol import PROTOCOL_VERSION, TaskState, decode, make_message
from .broker import Broker, HEARTBEAT_TIMEOUT, run_assign_loop
from .state import Board, ClientRecord, new_id

logger = logging.getLogger("eni.mp.server")

FRAME_LOG_LIMIT = 4000


class MultiplayerServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 8787,
                 data_dir: Optional[str] = None, auth_token: Optional[str] = None,
                 tenants: Optional[Dict[str, List[str]]] = None) -> None:
        self.host = host
        self.port = port
        self.auth_token = auth_token or os.environ.get("MP_AUTH_TOKEN", "").strip()
        # tenants: {tenant_name: [allowed_client_ids]} — empty list = any client
        self.tenants: Dict[str, List[str]] = tenants or {}
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
        self._client_tenant: Dict[str, str] = {}
        self._task_tenant: Dict[str, str] = {}

    # ------------------------------------------------------------- tenancy
    def _tenant_for(self, client_id: str) -> str:
        """Tenant for a client. First registered match, else 'default'."""
        return self._client_tenant.get(client_id, "default")

    def _tenant_workspace(self, tenant: str) -> str:
        """Each tenant gets an isolated workspace (no cross-tenant clobber)."""
        safe = "".join(c for c in (tenant or "default") if c.isalnum() or c in "-_") or "default"
        ws = os.path.join(self._workspace_dir(), safe)
        os.makedirs(ws, exist_ok=True)
        return ws

    def _check_auth(self, token: str) -> bool:
        """True when auth is disabled or the token matches."""
        if not self.auth_token:
            return True
        return bool(token) and token == self.auth_token

    def _client_allowed(self, client_id: str, tenant: str) -> bool:
        """For a tenant, an empty allowlist admits anyone; otherwise require the id."""
        allow = self.tenants.get(tenant, [])
        return (not allow) or (client_id in allow)

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
        # Auth + tenancy gate.
        tenant = (msg.get("tenant") or "default")
        if not self._check_auth(msg.get("token", "")) or not self._client_allowed(client_id, tenant):
            await self._send(client_id, make_message(
                "error", message="unauthorized: bad token or tenant not allowed",
                task_id="", code="unauthorized"))
            return
        self._client_tenant[client_id] = tenant
        self._tenant_workspace(tenant)
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
                # Merge into the TASK's tenant (from submit), not the client's —
                # this is the correct isolation boundary.
                task_tenant = self._task_tenant.get(tid, self._tenant_for(client_id))
                ws = self._tenant_workspace(task_tenant)
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
        snap["tenants"] = sorted(self.tenants.keys())
        snap["auth_required"] = bool(self.auth_token)
        return snap

    async def submit(self, goal: str, **fields) -> Dict[str, Any]:
        tenant = fields.pop("tenant", "default")
        token = fields.pop("token", "")
        if not self._check_auth(token):
            return {"error": "unauthorized", "ok": False}
        rec = await self.broker.submit(goal, **fields)
        self._task_tenant[rec.task_id] = tenant
        return {"task_id": rec.task_id, "status": rec.status.value, "goal": rec.goal}

    async def submit_plan(self, goal: str, **fields) -> Dict[str, Any]:
        """Fan a bare goal out through the local planner into one task per step.

        Each step task carries its own feature/step/test_hint and an enriched
        prompt, so builders get unique, correctly-named artifacts (no collision)
        that the LLM worker writes and self-tests. Returns the list of task_ids.
        """
        tenant = fields.pop("tenant", "default")
        token = fields.pop("token", "")
        if not self._check_auth(token):
            return {"error": "unauthorized", "ok": False}
        # Use the planner when importable (plain or enterpriced path).
        plan = None
        for modname in ("local_controller.planner", "enterprise.local_controller.planner"):
            try:
                import importlib
                mod = importlib.import_module(modname)
                plan = mod.parse_goal(goal)
                enrich = getattr(mod, "enrich_prompt", None)
                print(f"[submit_plan] planner via {modname} steps={len(plan.tasks)}") if enrich else None
                break
            except Exception as exc:
                print(f"[submit_plan] import {modname} failed: {exc}")
                continue
        if plan is None:
            # planner unavailable -> single opaque task
            return await self.submit(goal, tenant=tenant, token=token, **fields)

        tasks = plan.tasks or []
        if not tasks:
            return await self.submit(goal, tenant=tenant, token=token,
                                     **{k: v for k, v in fields.items() if k != "goal"})
        ids = []
        for t in tasks:
            prompt = t.prompt
            # enrich each step prompt for better artifacts
            try:
                from local_controller.planner import enrich_prompt as _enrich
                prompt = _enrich(t.prompt, goal=goal)
            except Exception:
                pass
            rec = await self.broker.submit(
                goal, prompt=prompt, repo=fields.get("repo", ""),
                feature=t.feature, step=t.step, test_hint=t.test_hint,
                model_hint=fields.get("model_hint", ""),
                tags=fields.get("tags", []) or [])
            self._task_tenant[rec.task_id] = tenant
            ids.append(rec.task_id)
        return {"goal": goal, "task_ids": ids, "steps": len(ids),
                "tenant": tenant}


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
            if self.path.startswith("/api/submit_plan"):
                try:
                    n = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(n) or b"{}")
                except Exception:
                    body = {}
                goal = body.get("goal", "")
                if not goal:
                    self._json(400, {"error": "missing 'goal'"})
                    return
                res = _loop_run(server.submit_plan(
                    goal,
                    repo=body.get("repo", ""),
                    tenant=body.get("tenant", "default"),
                    token=body.get("token", "")))
                self._json(200, res)
            elif self.path.startswith("/api/submit"):
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
                    model_hint=body.get("model_hint", ""),
                    tenant=body.get("tenant", "default"),
                    token=body.get("token", "")))
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


def run(host: str = "0.0.0.0", port: int = 8787, data_dir: Optional[str] = None,
        auth_token: Optional[str] = None, tenants: Optional[Dict[str, List[str]]] = None,
        tls_cert: Optional[str] = None, tls_key: Optional[str] = None) -> None:
    """Run the server (blocking). WS on `port`, HTTP API on `port+1`.

    Defaults to binding 0.0.0.0 so other machines on the LAN can join with their
    own builder clients. Enable auth by passing auth_token or setting MP_AUTH_TOKEN.
    Enable TLS by passing tls_cert/tls_key (PEM cert + key). Tenancy provides
    isolated per-tenant workspaces (dict tenant -> allowed client ids).
    """
    import websockets
    import ssl
    server = MultiplayerServer(host, port, data_dir, auth_token=auth_token,
                               tenants=tenants)

    http_port = port + 1
    api_httpd = ThreadingHTTPServer((host, http_port), _request_handler_factory(server))
    Thread(target=api_httpd.serve_forever, daemon=True).start()

    async def main():
        await server.broker.resume_from_disk()
        ws_kwargs = {"ping_interval": 25}
        if tls_cert and tls_key:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(tls_cert, tls_key)
            ws_kwargs["ssl"] = ctx
        scheme = "wss" if ws_kwargs.get("ssl") else "ws"
        serve = websockets.serve(websocket_handler(server),
                                 host, port, **ws_kwargs)
        await serve
        asyncio.ensure_future(_reap(server))
        # The assign loop drives QUEUED -> ASSIGNED on the MAIN event loop so
        # broker delivery reaches the websocket correctly.
        loop_stop = asyncio.Event()
        asyncio.ensure_future(run_assign_loop(server.broker, interval=1.0,
                                              stop=loop_stop))
        auth_note = "auth=enabled" if server.auth_token else "auth=disabled"
        print(f"Multiplayer server ready: {scheme}://{host}:{port}  http://{host}:{http_port} [{auth_note}]")
        print(f"  health http://{host}:{http_port}/health")
        print(f"  board  http://{host}:{http_port}/api/board")
        print(f"  submit POST http://{host}:{http_port}/api/submit  {{'goal': '...', 'token': '...'}}")
        print(f"  tenants {list(server.tenants.keys())}")
        await asyncio.Future()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nserver stopped")
        api_httpd.shutdown()


if __name__ == "__main__":
    import sys
    run(host=os.environ.get("MP_HOST", "0.0.0.0"),
        port=int(sys.argv[1]) if len(sys.argv) > 1 else 8787)