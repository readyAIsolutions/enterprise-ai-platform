"""ADD-ONLY read-only FastAPI panel skeleton for the Demiurge 3D backend.

Copy this into `backend/demiurge/webapp/<name>_health.py` (or similar) and
fill the `compute_*` body. It follows the proven `fleet_health.py` shape:

  * A standalone `APIRouter` (prefix `/api/<name>`) — no existing handler touched.
  * A `mount_<name>_health(app)` helper for a 2-line additive registration in
    `demiurge/webapp/main.py`:
        from demiurge.webapp.<name>_health import mount_<name>_health
        mount_<name>_health(app)
  * Config/env-only inputs (NEVER a request param that points at a filesystem).
  * Strictly read-only: imports only `fastapi` + stdlib + stable sibling modules.
    No `httpx`/`requests`/`socket`/`subprocess`/`paramiko` — it can never reach a
    printer or the network. Keep the import block at MODULE TOP-LEVEL only
    (function-local imports like `import sys` are fine but excluded from the
    safety AST scan).

Test it WITHOUT importing `main.py`: in `tests/test_<name>_health_routes.py`
build `FastAPI(); app.include_router(router); TestClient(app)` and feed a
synthetic store via a `monkeypatch` env fixture.
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

# Import ONLY stable, read-only sibling modules. Never a printer/motion client.
from demiurge.printer import fleet_snapshot as _snap
from demiurge.printer import fleet_trends as _trends  # or your analytics module

__all__ = ["router", "compute_report", "mount_<name>_health", "resolve_store_dir"]


def resolve_store_dir(store_dir: Optional[str] = None) -> str:
    """Config/env-only store path (absolute). Never request-supplied."""
    if store_dir:
        return str(os.path.abspath(store_dir))
    env = os.environ.get("DEMIURGE_FLEET_STORE")
    if env:
        return str(os.path.abspath(env))
    return str(_snap.DEFAULT_STORE_DIR.resolve())  # sibling default


def compute_report(
    store_dir: Optional[str] = None, *, limit: Optional[int] = None
) -> dict:
    """Read the SnapshotStore and run the read-only analytics.

    Returns a JSON-serializable dict. An empty/missing store yields an empty
    report (never raises) — the route stays 200.
    """
    store = _snap.SnapshotStore(resolve_store_dir(store_dir))
    snapshots = store.load_history(limit=limit)
    report = _trends.analyze_history(snapshots)
    body = report.to_dict()
    body["store_dir"] = resolve_store_dir(store_dir)
    body["snapshot_count"] = store.count()
    body["limit"] = limit
    return body


router = APIRouter(prefix="/api/<name>", tags=["<name>-health"])


@router.get("/health")
def health(
    limit: Optional[int] = Query(default=None, ge=1, le=2000),
) -> dict:
    return compute_report(limit=limit)


@router.get("/health/text", response_class=PlainTextResponse)
def health_text(
    limit: Optional[int] = Query(default=None, ge=1, le=2000),
) -> str:
    store = _snap.SnapshotStore(resolve_store_dir())
    report = _trends.analyze_history(store.load_history(limit=limit))
    return _trends.render_trend_text(report)


@router.get("/health/printer/{name}")
def health_printer(
    name: str,
    limit: Optional[int] = Query(default=None, ge=1, le=2000),
):
    store = _snap.SnapshotStore(resolve_store_dir())
    report = _trends.analyze_history(store.load_history(limit=limit))
    for p in report.printers:
        if p.name == name:
            return p.to_dict()
    raise HTTPException(
        status_code=404,
        detail={"error": "no history for printer", "name": name},
    )


def mount_<name>_health(app) -> None:
    """Register this router on a FastAPI/Starlette app (2-line additive edit in
    `demiurge/webapp/main.py`)."""
    app.include_router(router)
