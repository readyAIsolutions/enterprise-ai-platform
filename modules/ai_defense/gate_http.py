#!/usr/bin/env python3
"""Enterprise AI Defense - deployable AdversaryGate HTTP middleware.

Closes the deployed-vs-source gap the AgentForceHarness cannot: it puts the
fail-closed ``AdversaryGate`` in front of a LIVE site so that AI/agent attackers
are actually blocked at the transport layer, and lets TriadForge verify that the
deployed gate reacts (not just the in-process Python gate object).

Two deployments are provided, both stdlib-only and decoupled from any framework:

* ``AdversaryGateMiddleware`` --- a WSGI middleware you wrap around any WSGI app
  (Flask/Django/plain callable). One line::

      from enterprise.modules.ai_defense.gate_http import AdversaryGateMiddleware
      app = AdversaryGateMiddleware(inner_app, profile="aggressive")

* ``make_gate_server`` --- a tiny wsgiref daemon that pipes HTTP through the gate
  to an inner app, so you can defend a plain site without touching its code::

      gs = make_gate_server(inner_app, host="127.0.0.1", port=8534,
                            profile="aggressive")

When the gate BLOCK: returns ``429 Too Many Requests`` with JSON body naming the
facet + reason + ``Retry-After`` and an ``X-Adversary-Gate`` response header so
TriadForge's adversary engine can confirm the deployed defense reacted.

Faithful to ENI Rule 0: the gate only ever sees request metadata (IP, UA,
headers, query, POSTed content) --- never secrets. Content is scanned with the
IndirectPromptInjectionGuard before any downstream model receives it.

Version: 1.0.0
"""
from __future__ import annotations

import ipaddress
import json
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from wsgiref.simple_server import WSGIServer, make_server

from enterprise.modules.ai_defense.adversary_gate import (
    AdversaryGate,
    GateDecision,
    PROFILES,
)

__all__ = [
    "AdversaryGateMiddleware",
    "make_gate_server",
    "AdversaryGateServer",
    "GATE_BLOCK_STATUS",
]

GATE_BLOCK_STATUS = 429

# Paths we treat as auth (credential-stuffing guard hooks on these).
AUTH_PATHS = ("/login", "/signin", "/auth", "/gate", "/unlock", "/api/login",
              "/api/auth", "/verify")
# Paths we treat as model/query endpoints (extraction guard hooks on these).
MODEL_PATHS = ("/api/complete", "/api/chat", "/complete", "/generate",
               "/v1/completions", "/api/model", "/query")
# Paths we treat as content-submission (injection guard hooks on these).
CONTENT_PATHS = ("/submit", "/post", "/comment", "/api/submit", "/api/content",
                 "/message", "/send")
# Paths that are never gated (static assets, health checks).
IGNORE_PREFIXES = ("/static/", "/assets/", "/favicon.ico", "/health",
                   "/robots.txt", "/.well-known/")


def _client_ip(environ: Dict[str, Any]) -> str:
    """Best-effort client IP honoring X-Forwarded-For only for private hops."""
    fwd = environ.get("HTTP_X_FORWARDED_FOR", "")
    if fwd:
        head = fwd.split(",")[0].strip()
        try:
            ip = ipaddress.ip_address(head)
            if not ip.is_global:
                # XFF with a private hop => trust it (we're behind a reverse proxy)
                return head
        except ValueError:
            pass
    return environ.get("REMOTE_ADDR", "unknown")


def _is_auth_path(path: str) -> bool:
    return any(path.startswith(p) for p in AUTH_PATHS)


def _is_model_path(path: str) -> bool:
    return any(path.startswith(p) for p in MODEL_PATHS)


def _is_content_path(path: str) -> bool:
    return any(path.startswith(p) for p in CONTENT_PATHS)


def _is_ignored(path: str) -> bool:
    return any(path.startswith(p) for p in IGNORE_PREFIXES)


def _http_headers(environ: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k, v in environ.items():
        if k.startswith("HTTP_"):
            out[k[5:].replace("_", "-").lower()] = v
    # Normalize the UA so the gate's bot classifier keys on the right name.
    out["user-agent"] = environ.get("HTTP_USER_AGENT", "")
    return out


def _read_body(environ: Dict[str, Any], limit: int = 16_384) -> str:
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except (TypeError, ValueError):
        length = 0
    if length <= 0:
        return ""
    raw = environ.get("wsgi.input").read(min(length, limit))  # type: ignore[union-attr]
    try:
        return raw.decode("utf-8", "replace")
    except Exception:
        return ""


class AdversaryGateMiddleware:
    """WSGI middleware that runs the fail-closed AdversaryGate on every request.

    Blocks -> 429 + JSON body + ``X-Adversary-Gate`` header + ``Retry-After``.
    Allows -> pass through to the wrapped app, optionally decorating the
    response with an ``X-Adversary-Gate`` header so clients see defense is active.
    """

    def __init__(
        self,
        app: Callable,
        profile: str = "balanced",
        debug: bool = False,
        advertise_header: bool = True,
        now: Optional[Callable[[], float]] = None,
    ) -> None:
        self.app = app
        if profile not in PROFILES:
            raise ValueError(f"unknown profile {profile!r}; choices={list(PROFILES)}")
        self.profile_name = profile
        self.gate = AdversaryGate(profile=PROFILES[profile], clock=now or time.time)
        self.debug = debug
        self.advertise_header = advertise_header
        self._lock = threading.RLock()

    # ── WSGI entry ──────────────────────────────────────────────────────────
    def __call__(self, environ: Dict[str, Any], start_response: Callable) -> List[bytes]:
        path = environ.get("PATH_INFO", "/")
        if _is_ignored(path):
            return self.app(environ, start_response)

        key = _client_ip(environ)
        ua = environ.get("HTTP_USER_AGENT", "")
        headers = _http_headers(environ)
        query = environ.get("QUERY_STRING", "")

        decision: GateDecision
        with self._lock:
            decision = self._run_gate(path, key, ua, headers, query, environ)

        if not decision.allowed:
            # ── BLOCK ──
            body = json.dumps({
                "error": "request blocked by AdversaryGate",
                "facet": decision.facet,
                "reason": decision.reason,
                "profile": self.profile_name,
            }).encode("utf-8")
            start_response(
                f"{GATE_BLOCK_STATUS} Too Many Requests",
                [
                    ("Content-Type", "application/json"),
                    ("Content-Length", str(len(body))),
                    ("Retry-After", "60"),
                    ("X-Adversary-Gate", "blocked"),
                    ("Cache-Control", "no-store"),
                ],
            )
            return [body]

        # ── ALLOW: pass through to the wrapped app ──
        decorate = self.advertise_header

        def _response(start_response2: Callable) -> Callable:
            def _wrapped(status: str, response_headers: List[Tuple[str, str]], exc_info=None):
                if decorate:
                    response_headers = list(response_headers) + [
                        ("X-Adversary-Gate", "active")]
                return start_response2(status, response_headers, exc_info)
            return _wrapped

        return self.app(environ, _response(start_response))

    # ── gate orchestration ──────────────────────────────────────────────────
    def _run_gate(self, path: str, key: str, ua: str, headers: Dict[str, str],
                  query: str, environ: Dict[str, Any]) -> GateDecision:
        method = environ.get("REQUEST_METHOD", "GET")

        # 1) Auth endpoints: credential-stuffing guard hooks.
        if _is_auth_path(path):
            content = _read_body(environ)
            # classify the attempt: success if we can't tell (fail-open on auth
            # outcome is DOWNSTREAM's job); the guard charges failures here.
            if method in ("POST", "PUT"):
                acct = self._extract_account(content) or key
                d = self.gate.facade.check_auth(acct, key)
                if d.malicious:
                    return GateDecision(False, d.reason or "lockout", "credential-stuffing",
                                        d.score or 1.0)
                # Feed the streaming failure signal so lockout accumulates.
                self.gate.facade.record_auth_failure(acct, key)
            return self.gate.gate(key=key, user_agent=ua, headers=headers)

        # 2) Model/query endpoints: extraction guard on the query.
        if _is_model_path(path):
            content = _read_body(environ)
            query = query or content or ""
            return self.gate.gate(key=key, user_agent=ua, headers=headers,
                                  query=query[:2048])

        # 3) Content-submission endpoints: indirect injection guard on the body.
        if _is_content_path(path) and method in ("POST", "PUT", "PATCH"):
            content = _read_body(environ)
            return self.gate.gate(key=key, user_agent=ua, headers=headers,
                                  content=content[:8192])

        # 4) Everything else: anomaly + bot only.
        return self.gate.gate(key=key, user_agent=ua, headers=headers)

    @staticmethod
    def _extract_account(content: str) -> str:
        """Crude but effective: pull a username/email from a JSON or form body."""
        if not content:
            return ""
        for field in ("username", "email", "user", "account", "login"):
            import re
            m = re.search(rf'"{field}"\s*:\s*"([^"]+)"', content)
            if m:
                return m.group(1)
            m = re.search(rf"{field}=([^&\s]+)", content)
            if m:
                return m.group(1)
        return ""

    def posture(self) -> Dict[str, Any]:
        return {
            "profile": self.profile_name,
            "facade": self.gate.facade.posture(),
        }


class AdversaryGateServer:
    """Threaded WSGI server wrapping an inner app behind the gate."""

    def __init__(self, inner_app: Callable, profile: str = "balanced",
                 host: str = "127.0.0.1", port: int = 0):
        self.middleware = AdversaryGateMiddleware(inner_app, profile=profile)
        self._httpd = make_server(host, port, self.middleware,
                                  server_class=_ThreadingWSGIServer)
        self._thread: Optional[threading.Thread] = None

    @property
    def port(self) -> int:
        return self._httpd.server_address[1]

    def start(self) -> None:
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()

    def posture(self) -> Dict[str, Any]:
        return self.middleware.posture()


class _ThreadingWSGIServer(WSGIServer):
    daemon_threads = True


def make_gate_server(inner_app: Callable, profile: str = "balanced",
                     host: str = "127.0.0.1", port: int = 0) -> AdversaryGateServer:
    """Build a ready-to-start gate server in front of ``inner_app``."""
    return AdversaryGateServer(inner_app, profile=profile, host=host, port=port)
