#!/usr/bin/env python3
"""Defend your site with the Enterprise AdversaryGate in front of an inner app.

Quick deployable wrapper: run a WSGI app behind the fail-closed AdversaryGate so
AI/agent attackers are blocked at the transport layer. Verifies the deployment
reacts (curl flood => 429 + X-Adversary-Gate), which TriadForge's `adversary`
engine then confirms over HTTP.

Usage:
  python3 defend_site.py --profile aggressive --port 8534 app_module:app

Where `app_module:app` is any WSGI callable (or `--demo` spins up a self-test
echo site). LOCAL first — bind 127.0.0.1 by default.
"""
from __future__ import annotations

import argparse
import importlib
import threading
import time
from wsgiref.simple_server import make_server
from wsgiref.validate import validator

from enterprise.modules.ai_defense.gate_http import AdversaryGateMiddleware


def _demo_app(environ, start_response):
    body = b"<html><body><h1>Site behind AdversaryGate</h1></body></html>"
    start_response("200 OK", [("Content-Type", "text/html"),
                              ("Content-Length", str(len(body)))])
    return [body]


def _resolve_app(spec: str):
    if spec == "--demo":
        return _demo_app
    module_name, _, attr = spec.partition(":")
    mod = importlib.import_module(module_name)
    return getattr(mod, attr)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run an app behind the AdversaryGate")
    ap.add_argument("--app", default="--demo", help="module:callable or --demo")
    ap.add_argument("--profile", default="aggressive",
                    choices=["conservative", "balanced", "aggressive"])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8534)
    ap.add_argument("--verify", action="store_true",
                    help="after starting, self-flood and report block rate")
    args = ap.parse_args()

    inner = _resolve_app(args.app)
    wrapped = AdversaryGateMiddleware(inner, profile=args.profile)
    httpd = make_server(args.host, args.port, wrapped)
    port = httpd.server_address[1]

    if args.verify:
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        import urllib.request
        import urllib.error
        blocked = 0
        n = 30
        for _ in range(n):
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/", headers={"User-Agent": "python-requests/2.31"})
            try:
                urllib.request.urlopen(req, timeout=8)
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    blocked += 1
        print(f"AdversaryGate deploy self-verify: {blocked}/{n} flood requests blocked "
              f"({100 * blocked / n:.0f}%) profile={args.profile} on :{port}")
        httpd.shutdown()
        return 0

    print(f"Serving {args.app} behind AdversaryGate(profile={args.profile}) "
          f"on http://{args.host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
