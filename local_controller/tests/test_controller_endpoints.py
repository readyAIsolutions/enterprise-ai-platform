"""Tests for the controller desktop-app endpoints: /prompt_buffer and /secret."""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]          # enterprise/
PARENT = REPO.parent                                  # Enterprise Builder/


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Srv:
    def __init__(self) -> None:
        self.port = _free_port()
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "enterprise.local_controller.controller",
             "--port", str(self.port)],
            cwd=str(REPO),
            env={**__import__("os").environ, "PYTHONPATH": str(PARENT)},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(2.2)

    def req(self, method: str, path: str, body=None):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
                                   data=data, method=method,
                                   headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(r, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode() or "{}")

    def close(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


def test_health_advertises_new_endpoints():
    s = _Srv()
    try:
        _, payload = s.req("GET", "/health")
        assert "/prompt_buffer" in payload["endpoints"]
        assert "/secret" in payload["endpoints"]
    finally:
        s.close()


def test_prompt_buffer_post_peek_drain():
    s = _Srv()
    try:
        code, p = s.req("POST", "/prompt_buffer", {"text": "goal A"})
        assert code == 200 and p["queued"] == 1
        s.req("POST", "/prompt_buffer", {"text": "goal B"})
        _, peek = s.req("GET", "/prompt_buffer")
        assert peek["count"] == 2 and peek["drained"] is False
        _, drain = s.req("GET", "/prompt_buffer?drain=true")
        assert drain["count"] == 2 and drain["drained"] is True
        _, empty = s.req("GET", "/prompt_buffer")
        assert empty["count"] == 0
    finally:
        s.close()


def test_prompt_buffer_rejects_empty():
    s = _Srv()
    try:
        code, p = s.req("POST", "/prompt_buffer", {"text": "   "})
        assert code == 400
    finally:
        s.close()


def test_secret_set_get_list():
    s = _Srv()
    name = f"test_sec_{s.port}"
    try:
        code, p = s.req("POST", "/secret", {"name": name, "value": "v123"})
        assert code == 200 and p["stored"] is True
        code, got = s.req("GET", f"/secret?name={name}")
        assert code == 200 and got["value"] == "v123"
        _, listing = s.req("GET", "/secret")
        assert name in listing["names"]
    finally:
        s.close()


def test_secret_missing_and_bad_name():
    s = _Srv()
    try:
        assert s.req("GET", "/secret?name=does_not_exist")[0] == 404
        assert s.req("POST", "/secret", {"name": "bad name", "value": "x"})[0] == 422
        assert s.req("POST", "/secret", {"value": "x"})[0] == 400
    finally:
        s.close()
