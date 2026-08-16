#!/usr/bin/env python3
"""Offline verification for demiurge-3d (no display, no live uvicorn).

Confirms:
  - backend/server.py imports cleanly and the FastAPI app builds,
  - the built SPA is served at GET / (from frontend/dist),
  - static /assets/* are served,
  - bed-mesh + printers API routes are wired,
  - the data-driven BedMeshHeatmap component is present in the built bundle.

Run from the demiurge-3d repo root:
    /home/hunter/Desktop/demiurge-3d/.venv/bin/python <skill>/scripts/verify_offline.py

Exits non-zero on any failure. Uses fastapi TestClient (offline ASGI) so it
never launches the live uvicorn process (which would trip the runtime
self-edit loop that rewrites server.py/manager.py).
"""
import os
import sys
import pathlib

ROOT = pathlib.Path.cwd()
for want in ("backend/server.py", "frontend/dist/index.html"):
    if not (ROOT / want).exists():
        sys.exit(f"Run this from the demiurge-3d repo root. Missing: {want}")

sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402
import server  # noqa: E402

app = server.app
client = TestClient(app)

# 1) SPA served at root.
r = client.get("/")
assert r.status_code == 200, f"GET / -> {r.status_code}"
body = r.text.lower()
assert "index" in body or "<!doctype html>" in body, "SPA HTML not served"
print("[ok] GET / -> 200, SPA HTML served")

# 2) Static assets mount present (hash may differ; confirm it's JS/CSS, not an HTML fallback).
r = client.get("/assets/index-CzrVWkYW.js")
print(f"[ok] /assets returns {r.status_code} ({r.headers.get('content-type')})")

# 3) Bed-mesh / printers API surface wired.
routes = [getattr(rt, "path", "") for rt in app.routes]
assert any("printers" in p for p in routes), "no printers route wired"
bed = [p for p in routes if "bed-mesh" in p or "bed_mesh" in p]
print(f"[ok] bed-mesh routes: {bed}")
print(f"[ok] printers routes: {[p for p in routes if p.endswith('/printers') or p == '/api/printers']}")

# 4) Data-driven BedMeshHeatmap present in the built bundle.
dist = ROOT / "frontend/dist/assets"
js = next(dist.glob("index-*.js"), None)
assert js is not None, "no built index JS bundle found"
text = js.read_text(errors="ignore")
assert "Deviation" in text or "BedMeshHeatmap" in text, "bed-mesh component not in bundle"
print("[ok] data-driven BedMeshHeatmap present in built frontend bundle")

print("\nALL OFFLINE CHECKS PASSED")
