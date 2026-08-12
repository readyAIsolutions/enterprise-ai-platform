#!/usr/bin/env python3
"""Enterprise Platform Dashboard — SINGULARITY Edition. :8421.

Surfaces LIVE kernel telemetry — real EventBus history, per-module health
(including functional capability probes) and a live MetricsCollector snapshot —
instead of hardcoded empty/static values. Fully degradable: if the kernel can
not be imported, the endpoints still return well-formed, live-shaped data
with ``live: false`` so the dashboard never crashes.
"""

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route
from starlette.staticfiles import StaticFiles

HERE = Path(__file__).resolve().parent
VALIDATION_SCRIPT = str(HERE / "run_validation.py")

# ── Kernel live telemetry ─────────────────────────────────────────────────────
# Pull the real kernel primitives so the dashboard surfaces LIVE events, health
# and metrics. If the kernel cannot be imported we degrade to well-formed empty
# (but live-shaped) structures and report the reason under `live: false`.
try:
    from platform_kernel import (
        Event,
        EventBus,
        EventPriority,
        HealthChecker,
        HealthStatus,
        MetricsCollector,
        Module,
        ModuleRecord,
        ModuleRegistry,
        _json_safe,
        module,
    )

    _KERNEL_OK = True
    _KERNEL_ERR = None
except Exception as exc:  # pragma: no cover - import fallback path
    _KERNEL_OK = False
    _KERNEL_ERR = str(exc)
    Event = EventBus = EventPriority = MetricsCollector = None
    Module = ModuleRecord = ModuleRegistry = None
    HealthChecker = HealthStatus = None
    module = _json_safe = lambda *_a, **_k: None

jinja_env = Environment(loader=FileSystemLoader(str(HERE / "templates")), autoescape=True)
START_TIME = time.time()
_cache = {}
_cache_time = 0.0


def _run_validation() -> dict | None:
    """Run validation as subprocess — no import path issues."""
    try:
        result = subprocess.run(
            [sys.executable, VALIDATION_SCRIPT],
            capture_output=True,
            text=True,
            timeout=30,
            cwd="/home/hunter/Desktop/Enterprise Builder",
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except Exception:
        pass
    return None


def _get_validation() -> dict:
    global _cache, _cache_time
    now = time.time()
    if _cache and (now - _cache_time) < 5:
        return _cache
    data = _run_validation()
    if data:
        _cache = data
        _cache_time = now
        return data
    return {
        "final_score": "—",
        "certification": "Offline",
        "module_count": 0,
        "total_tests": "—",
        "base_score": "—",
        "transcendent_bonus": "—",
        "modules": {},
        "bonuses": dict.fromkeys(
            [
                "swarm_intelligence",
                "recursive_self_improve",
                "compression_transcend",
                "zero_cost_operation",
                "adaptive_resilience",
                "cross_domain_intel",
                "hermeneutic_closure",
                "temporal_autonomy",
            ],
            0,
        ),
        "recommendations": ["Validation engine offline"],
        "signal_dbm": "—",
    }


def _get_swarm() -> dict:
    signal, concurrency = -60, 50
    try:
        out = subprocess.run(
            ["iw", "dev", "wlp4s0", "link"], capture_output=True, text=True, timeout=3
        )
        import re

        m = re.search(r"signal:\s*(-?\d+)\s*dBm", out.stdout)
        if m:
            signal = int(m.group(1))
            if signal > -48:
                concurrency = 80
            elif signal > -52:
                concurrency = 70
            elif signal > -56:
                concurrency = 60
            elif signal > -60:
                concurrency = 50
            elif signal > -65:
                concurrency = 40
            elif signal > -70:
                concurrency = 25
            else:
                concurrency = 15
    except Exception:
        pass
    turbo = False
    try:
        import urllib.request

        with urllib.request.urlopen("http://localhost:8922/health", timeout=2) as r:
            turbo = r.status == 200
    except Exception:
        pass
    return {
        "signal_dbm": signal,
        "concurrency": concurrency,
        "interface": "wlp4s0",
        "turbocharger": turbo,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  LIVE TELEMETRY CORE
# ══════════════════════════════════════════════════════════════════════════════
_event_bus = EventBus() if _KERNEL_OK else None
_metrics = MetricsCollector() if _KERNEL_OK else None
_health_checker = None  # injected / self-check HealthChecker
_live_os = None  # optionally injected running kernel

# A real self-check module so per-module health is meaningful even when the
# dashboard runs standalone (no injected platform). Its probe() performs an
# actual non-mutating capability check against the live telemetry stores.
if _KERNEL_OK and Module is not None:

    @module(name="dashboard", version="1.0.0")
    class DashboardSelfModule(Module):
        async def initialize(self) -> None:
            pass

        async def shutdown(self) -> None:
            pass

        async def health_check(self) -> "HealthStatus":
            ok = bool(_event_bus) and bool(_metrics)
            return HealthStatus.HEALTHY if ok else HealthStatus.UNHEALTHY

        async def probe(self) -> dict:
            evs = _event_bus.get_history(limit=1) if _event_bus else []
            return {
                "event_bus_ready": bool(_event_bus),
                "metrics_ready": bool(_metrics),
                "kernel_import_err": _KERNEL_ERR,
                "last_event_topic": evs[-1].topic if evs else None,
            }

    _dashboard_instance = DashboardSelfModule()
    _own_registry = ModuleRegistry(config={})
    with _own_registry._lock:
        _own_registry._records["dashboard"] = ModuleRecord(
            name="dashboard",
            path=HERE,
            version="1.0.0",
            instance=_dashboard_instance,
        )
    _health_checker = HealthChecker(_own_registry, _event_bus)
else:
    _dashboard_instance = None
    _own_registry = None
    _health_checker = None


def configure_live_source(
    os_instance: object | None = None,
    event_bus: object | None = None,
    metrics: object | None = None,
    health_checker: object | None = None,
) -> None:
    """Inject a running kernel so the dashboard reflects REAL platform state.

    If given a PlatformOS instance, its EventBus, MetricsCollector and
    HealthChecker (with real initialized modules) become the live source.
    """
    global _live_os, _event_bus, _metrics, _health_checker
    _live_os = os_instance
    if event_bus is not None:
        _event_bus = event_bus
    if metrics is not None:
        _metrics = metrics
    if health_checker is not None:
        _health_checker = health_checker
    elif os_instance is not None:
        _health_checker = getattr(os_instance, "health_checker", None) or _health_checker


def publish_event(
    topic: str,
    source: str = "dashboard",
    payload: dict | None = None,
    priority: object | None = None,
) -> object | None:
    """Publish a REAL event onto the live EventBus (surfaced by /api/events).

    Returns the created Event, or None if the kernel is unavailable.
    """
    if _event_bus is None:
        return None
    pri = priority if priority is not None else EventPriority.NORMAL
    ev = Event.create(topic, source, payload or {}, priority=pri)
    _event_bus.publish(ev)
    if _metrics is not None:
        _metrics.increment("events.published", module=source)
    return ev


def _record_http(name: str = "http.requests") -> None:
    if _metrics is not None:
        _metrics.increment(name, module="dashboard")


def _event_to_dict(ev: object) -> dict:
    ts = getattr(ev, "timestamp", None)
    prio = getattr(ev, "priority", "unknown")
    return {
        "event_id": getattr(ev, "event_id", None),
        "topic": getattr(ev, "topic", ""),
        "source": getattr(ev, "source", ""),
        "priority": prio.value if hasattr(prio, "value") else prio,
        "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
        "correlation_id": getattr(ev, "correlation_id", None),
        "payload": _json_safe(getattr(ev, "payload", {})),
    }


def _qint(raw: str | None, default: int) -> int:
    try:
        return max(1, min(int(raw), 1000))
    except (TypeError, ValueError):
        return default


_health_cache = {}
_health_cache_time = 0.0
_HEALTH_TTL = 3.0


async def _refresh_health() -> dict | None:
    """Run structural+functional health checks and return per-module dicts."""
    if _health_checker is None:
        return None
    try:
        await _health_checker.run_all_checks(functional=True)
    except Exception:
        try:
            await _health_checker.run_all_checks()
        except Exception:
            return None
    reports = _health_checker.get_all_reports()
    return {name: [r.to_dict() for r in rl] for name, rl in reports.items()}


def _build_offline_health() -> dict:
    return {
        "platform": [
            {
                "module_name": "platform",
                "status": "unknown",
                "response_time_ms": 0.0,
                "timestamp": datetime.now(UTC).isoformat(),
                "details": {
                    "modules_checked": 0,
                    "healthy": 0,
                    "unhealthy": 0,
                    "unhealthy_modules": [],
                },
                "consecutive_failures": 0,
                "consecutive_successes": 0,
            }
        ]
    }


async def _get_health_reports() -> dict:
    global _health_cache, _health_cache_time
    now = time.time()
    if _health_cache and (now - _health_cache_time) < _HEALTH_TTL:
        return _health_cache
    data = await _refresh_health()
    if data:
        _health_cache = data
        _health_cache_time = now
        return data
    return _build_offline_health()


def _overall_status(modules: dict) -> str:
    if not modules:
        return "degraded"
    names = [n for n in modules if n != "platform"]
    if not names:
        return "healthy"
    unhealthy = 0
    for n in names:
        rl = modules.get(n, [])
        if rl and rl[-1].get("status") == "unhealthy":
            unhealthy += 1
    if unhealthy == 0:
        return "healthy"
    if unhealthy < len(names):
        return "degraded"
    return "unhealthy"


# Emit a real startup event so the event stream is never empty once the kernel
# primitives are available.
if _event_bus is not None:
    publish_event("dashboard.started", "dashboard", {"pid": os.getpid()})


# ══════════════════════════════════════════════════════════════════════════════
#  HANDLERS
# ══════════════════════════════════════════════════════════════════════════════
async def home(req: Request) -> HTMLResponse:
    v = _get_validation()
    s = _get_swarm()
    _record_http()
    ctx = {
        "request": req,
        "score": v,
        "swarm": s,
        "uptime": int(time.time() - START_TIME),
        "now": datetime.now().strftime("%H:%M:%S"),
    }
    return HTMLResponse(jinja_env.get_template("dashboard.html").render(ctx))


async def api_score(_req: Request) -> JSONResponse:
    _record_http()
    return JSONResponse(_get_validation())


async def api_modules(_req: Request) -> JSONResponse:
    _record_http()
    return JSONResponse(_get_validation().get("modules", {}))


async def api_swarm(_req: Request) -> JSONResponse:
    _record_http()
    return JSONResponse(_get_swarm())


async def api_events(req: Request) -> JSONResponse:
    _record_http("http.events_requests")
    limit = _qint(req.query_params.get("limit"), 50)
    evs = _event_bus.get_history(limit=limit) if _event_bus else []
    return JSONResponse(
        {
            "events": [_event_to_dict(e) for e in evs],
            "count": len(evs),
            "live": _event_bus is not None,
        }
    )


async def api_metrics(_req: Request) -> JSONResponse:
    _record_http("http.metrics_requests")
    if _metrics is None:
        return JSONResponse(
            {"counters": {}, "gauges": {}, "histograms": {}, "history_count": 0, "live": False}
        )
    snap = _metrics.snapshot()
    snap["live"] = True
    snap["generated_at"] = datetime.now(UTC).isoformat()
    return JSONResponse(snap)


async def api_health(_req: Request) -> JSONResponse:
    _record_http("http.health_requests")
    mods = await _get_health_reports()
    metrics_snap = _metrics.snapshot() if _metrics is not None else {}
    uptime = int(time.time() - START_TIME)
    return JSONResponse(
        {
            "status": _overall_status(mods),
            "uptime": uptime,
            "live": _event_bus is not None,
            "modules": mods,
            "metrics": metrics_snap,
            "now": datetime.now(UTC).isoformat(),
        }
    )


async def api_control(req: Request) -> JSONResponse:
    """Control surface: run enterprise/agent-os verbs from the browser.

    Dispatches to the validated `eni_cli` runner via subprocess (the repo's
    bulletproof pattern — sidesteps import-path / event-loop / singleton
    issues inside the Starlette process). Body: {"verb": "...", "args": {...}}.
    """
    _record_http("http.control_requests")
    try:
        data = await req.json()
    except Exception:
        data = {}
    verb = str(data.get("verb", "")).strip()
    args = data.get("args", {}) or {}
    cli = HERE.parent / "scripts" / "eni_cli.py"
    # Map verb -> CLI args (whitelisted — never pass raw input to shell).
    if verb == "agent-os":
        sub_verb = str(args.get("verb", "status"))
        if sub_verb not in {"status", "brief", "oracle", "draft", "publish_latest", "voice", "hermes"}:
            return JSONResponse({"ok": False, "error": f"disallowed agent-os verb: {sub_verb}"}, status_code=400)
        cmd = [sys.executable, str(cli), "agent-os", sub_verb]
        if sub_verb == "voice":
            txt = str(args.get("text", ""))[:500]
            cmd += ["--text", txt]
        if sub_verb == "brief":
            cmd += ["--deliver", str(args.get("deliver", "file"))]
        if sub_verb == "publish_latest":
            cmd += ["--limit", str(int(args.get("limit", 1)))]
    elif verb == "brief":
        deliver = str(args.get("deliver", "file"))
        if deliver not in {"file", "signal", "both"}:
            deliver = "file"
        cmd = [sys.executable, str(cli), "brief", "--deliver", deliver]
    elif verb == "status":
        cmd = [sys.executable, str(cli), "status"]
    elif verb == "doctor":
        cmd = [sys.executable, str(cli), "doctor"]
    elif verb == "modules":
        cmd = [sys.executable, str(cli), "modules"]
    else:
        return JSONResponse({"ok": False, "error": f"unknown control verb: {verb}"}, status_code=400)

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90, cwd=str(HERE.parent))
    except subprocess.TimeoutExpired:
        return JSONResponse({"ok": False, "error": "command timed out"})
    return JSONResponse(
        {
            "ok": proc.returncode == 0,
            "exit": proc.returncode,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-1000:],
        }
    )


app = Starlette(debug=False)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.routes.extend(
    [
        Route("/", home),
        Route("/api/score", api_score),
        Route("/api/modules", api_modules),
        Route("/api/swarm", api_swarm),
        Route("/api/events", api_events),
        Route("/api/health", api_health),
        Route("/api/metrics", api_metrics),
        Route("/api/control", api_control, methods=["POST"]),
    ]
)
if (HERE / "static").exists():
    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")

# Warm cache on startup
v = _get_validation()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8421, log_level="info")
