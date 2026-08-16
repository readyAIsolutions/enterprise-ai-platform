"""Multiplayer builder client.

Runs on each team member's machine. Connects to a coordination server over
WebSocket, advertises its hardware + model capabilities, and executes assigned
tasks via a pluggable Worker. NEVER sends API keys — only capability tags.

Run standalone or import; there is also a CLI entry:
    python3 -m enterprise.multiplayer.client.client --host 127.0.0.1 --port 8787
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import time
from typing import Any, Dict, Optional

from ..protocol import make_message, decode
from .runner import WORKERS

HEARTBEAT_INTERVAL = 15.0


def default_machine_profile() -> Dict[str, Any]:
    """Announce local hardware so the server can route by capacity."""
    import multiprocessing
    try:
        import psutil  # type: ignore
        ram = round(psutil.virtual_memory().total / (1024 ** 3), 1)
        cores = psutil.cpu_count() or multiprocessing.cpu_count()
    except Exception:
        cores = multiprocessing.cpu_count()
        ram = None
    gpu = "gpu" in (os.environ.get("MP_TAGS", "")) or _looks_like_gpu_box()
    return {
        "cpus": cores,
        "ram_gb": ram,
        "hostname": platform.node(),
        "gpu_name": os.environ.get("GPU_NAME", ""),
    }


def _looks_like_gpu_box() -> bool:
    return os.path.exists(os.path.expanduser("~/.hermes")) or any(
        os.path.exists(p) for p in ("/usr/bin/nvidia-smi", "/usr/bin/rocm-smi"))


def default_capabilities() -> Dict[str, Any]:
    tags = [t for t in (os.environ.get("MP_TAGS", "").split(",")) if t]
    if not tags:
        tags = ["cpu"]
    return {
        "max_concurrent_tasks": int(os.environ.get("MP_MAX_TASKS", "2")),
        "models": [x for x in os.environ.get("MP_MODELS", "free-router").split(",") if x],
        "providers": [x for x in os.environ.get("MP_PROVIDERS", "openrouter,free-router").split(",") if x],
        "tags": tags,
        "gpu": "gpu" in tags,
    }


class BuilderClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 8787,
                 client_id: Optional[str] = None,
                 worker_name: str = "shell",
                 workdir: Optional[str] = None) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id or (platform.node() + "-" + str(os.getpid()))
        self.worker = WORKERS[worker_name](cwd=workdir)
        self.ws = None
        self._capacity = default_capabilities()

    async def connect(self):
        import websockets
        uri = f"ws://{self.host}:{self.port}"
        self.ws = await websockets.connect(uri, ping_interval=25)
        await self.ws.send(json.dumps(make_message(
            "hello",
            client_id=self.client_id,
            capabilities=self._capacity,
            machine=default_machine_profile(),
            tenant=os.environ.get("MP_TENANT", "default"),
            token=os.environ.get("MP_TOKEN", ""),
        )))

    async def run_forever(self) -> None:
        import websockets
        hb = asyncio.create_task(self._heartbeat())
        try:
            async for raw in self.ws:
                msg = decode(raw)
                kind = msg.get("type", "")
                if kind == "task":
                    asyncio.create_task(self._execute(msg))
                elif kind == "welcome":
                    print(f"[{self.client_id}] welcome from server {msg.get('server_id')}")
        finally:
            hb.cancel()

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                await self.ws.send(json.dumps(make_message(
                    "heartbeat", client_id=self.client_id)))
            except Exception:
                break

    async def _execute(self, task: Dict[str, Any]) -> None:
        tid = task["task_id"]
        # Announce start
        try:
            await self.ws.send(json.dumps(make_message("work_start", client_id=self.client_id, task_id=tid)))
        except Exception:
            pass
        result = self.worker.run(task)
        # send result
        payload = make_message(
            "work_result", client_id=self.client_id, task_id=tid,
            status="completed" if result.get("ok") else "failed",
            summary=result.get("summary", ""),
            error="" if result.get("ok") else result.get("summary", ""),
            artifacts=result.get("artifacts", []),
        )
        if "artifacts" not in payload:
            payload["artifacts"] = result.get("artifacts", [])
        try:
            await self.ws.send(json.dumps(payload))
        except Exception as exc:
            print(f"[{self.client_id}] failed to send result: {exc}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Multiplayer builder client")
    ap.add_argument("--host", default=os.environ.get("MP_SERVER", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--id", default=None)
    ap.add_argument("--worker", default="shell", choices=list(WORKERS))
    ap.add_argument("--workdir", default=None)
    args = ap.parse_args()

    client = BuilderClient(args.host, args.port, args.id, args.worker, args.workdir)

    async def _amain():
        await client.connect()
        print(f"[{client.client_id}] connected to ws://{args.host}:{args.port}")
        await client.run_forever()

    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        print("\nclient stopped")


if __name__ == "__main__":
    main()