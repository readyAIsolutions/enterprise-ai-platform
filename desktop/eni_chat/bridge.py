#!/usr/bin/env python3
"""Loopback HTTP bridge for the ENI two-pane desktop chat (Hermes + Local).

Serves the chat UIs (same-origin, so no CORS issues inside WebKit) and proxies
chat completions to the two model backends:
  * LEFT pane  -> "Hermes"  : the router (free-router :8920, OpenAI-compatible)
  * RIGHT pane -> "Local"   : a local model server (configurable)

Any pane can target any OpenAI-compatible /v1/chat/completions endpoint (base
URL + model), so the two panes are "Hermes and Local side by side" but still
fully configurable. Streams if the backend supports SSE, else falls back to
non-streaming JSON.
"""
from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

PORT = int(os.environ.get("ENI_DESKTOP_PORT", "8765"))
_HERE = Path(__file__).resolve().parent
STATIC = _HERE / "ui"

# default pane backends (all OpenAI-compatible chat/completions)
DEFAULTS: Dict[str, Dict[str, str]] = {
    "left": {"base": "http://127.0.0.1:8920/v1", "model": "openrouter/auto"},
    "right": {"base": "http://127.0.0.1:8000/v1", "model": "local"},
}
_LOCAL_CANDIDATES = ["http://127.0.0.1:8000/v1", "http://127.0.0.1:8080/v1",
                     "http://127.0.0.1:11434/v1", "http://127.0.0.1:8913/v1"]


def _poke(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout):
            return True
    except Exception:
        return False


def _pick_right_base() -> str:
    for cand in _LOCAL_CANDIDATES:
        if _poke(cand + "/models"):
            return cand
    return _LOCAL_CANDIDATES[0]


def _post(url: str, payload: dict, timeout: float = 120) -> Any:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


class BridgeHandler(BaseHTTPRequestHandler):
    server: "BridgeServer"

    def _json(self, code: int, obj: Any) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _static(self, name: str, ctype: str) -> None:
        p = STATIC / name
        if not p.exists():
            self.send_response(404); self.end_headers(); return
        body = p.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _pane(self, path: str) -> Optional[str]:
        parts = path.strip("/").split("/")
        if len(parts) >= 3 and parts[0] in ("chat", "api"):
            pane = parts[1]
            if pane in ("left", "right"):
                return pane
        return None

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/":
            body = bytes(f'<meta http-equiv="refresh" content="0;url=/chat/left">', "utf-8")
            self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        elif path == "/chat/left" or path == "/chat/right":
            self._static("chat.html", "text/html; charset=utf-8")
        elif path == "/app.js":
            self._static("app.js", "text/javascript; charset=utf-8")
        elif path == "/style.css":
            self._static("style.css", "text/css; charset=utf-8")
        elif path.startswith("/api/") and path.endswith("/models"):
            self._api_models(path)
        else:
            self._json(404, {"error": "not found", "path": path})

    def _api_models(self, path: str) -> None:
        pane = self._pane(path)
        base = (self.server.config.get(pane, {}) or {}).get("base", "")
        names: list = []
        try:
            if base:
                req = urllib.request.Request(base.rstrip("/") + "/models")
                with urllib.request.urlopen(req, timeout=6) as resp:
                    mods = json.loads(resp.read().decode("utf-8", "replace"))
                names = [m.get("id") for m in mods.get("data", [])] if isinstance(mods, dict) else []
        except Exception as exc:
            self._json(200, {"models": [], "error": str(exc)})
            return
        self._json(200, {"models": names})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path in ("/api/left/chat", "/api/right/chat"):
            self._chat(path)
        else:
            self._json(404, {"error": "not found"})

    def _chat(self, path: str) -> None:
        pane = "left" if "left" in path else "right"
        cfg = self.server.config.get(pane, {})
        base = cfg.get("base", "")
        try:
            n = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(n).decode("utf-8", "replace"))
        except Exception as exc:
            self._json(400, {"error": f"bad request: {exc}"}); return
        model = data.get("model") or cfg.get("model") or "auto"
        messages = data.get("messages", [])
        stream = bool(data.get("stream", True))
        if not base:
            self._json(502, {"error": "no backend base URL configured for pane"})
            return
        payload = {"model": model, "messages": messages, "stream": stream,
                   "temperature": 0.5}
        try:
            result = _post(base + "/chat/completions", payload)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:400]
            self._json(502, {"error": f"backend {e.code}: {detail}"}); return
        except Exception as exc:
            self._json(502, {"error": f"backend unreachable: {exc}"}); return
        self._json(200, result)


class BridgeServer(ThreadingHTTPServer):
    def __init__(self, config: Dict[str, Dict[str, str]], port: int = PORT) -> None:
        super().__init__(("127.0.0.1", port), BridgeHandler)
        self.config = config
        self.config.setdefault("left", dict(DEFAULTS["left"]))
        self.config.setdefault("right", dict(DEFAULTS["right"]))


def main() -> None:
    cfg = {
        "left": {"base": DEFAULTS["left"]["base"], "model": DEFAULTS["left"]["model"]},
        "right": {"base": _pick_right_base(), "model": "local"},
    }
    srv = BridgeServer(cfg)
    print(f"[eni_desktop] bridge on http://127.0.0.1:{srv.server_address[1]}")
    print(f"[eni_desktop] LEFT  (Hermes) base={cfg['left']['base']}")
    print(f"[eni_desktop] RIGHT (Local)  base={cfg['right']['base']}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()