#!/usr/bin/env python3
"""
Enterprise Platform Dashboard — SINGULARITY Edition
====================================================
Live dashboard on :8421 showing platform score, module grid,
swarm status, transcendent axes, and event feed.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Ensure enterprise is importable — use correct project root
HERE = Path(__file__).resolve().parent
# Try Enterprise Builder first, fall back to Eni Builder
for candidate in [HERE.parents[1], HERE.parents[1].with_name("Enterprise Builder")]:
    ent_dir = candidate / "enterprise"
    if (ent_dir / "platform_kernel.py").exists():
        BASE = candidate
        ENTERPRISE_DIR = ent_dir
        break
else:
    BASE = HERE.parents[1]
    ENTERPRISE_DIR = BASE / "enterprise"

if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))
if str(ENTERPRISE_DIR) not in sys.path:
    sys.path.insert(0, str(ENTERPRISE_DIR))

from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route
from starlette.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from jinja2 import Environment, FileSystemLoader

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE / "templates"
STATIC = HERE / "static"

# Use explicit Jinja2 Environment to avoid Jinja2Templates cache bug
jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=True)

# ── Enterprise imports ───────────────────────────────────────────────────
try:
    from enterprise.platform_kernel import PlatformOS, EventBus
    platform = PlatformOS.get_instance()
    bus = EventBus()
except Exception as e:
    platform = None
    bus = None
    print(f"[WARN] PlatformOS unavailable: {e}")

try:
    from enterprise.modules.enterprise_validation.validation_engine import run_full_validation
except Exception as e:
    run_full_validation = None
    print(f"[WARN] Validation engine unavailable: {e}")

try:
    from enterprise.modules.swarm_network import WiFiReader
except Exception:
    WiFiReader = None

# ── Caching ──────────────────────────────────────────────────────────────
_cache: Dict[str, Any] = {}
_cache_time: float = 0.0
CACHE_TTL = 5  # seconds

def get_cached_validation() -> Dict[str, Any]:
    global _cache, _cache_time
    now = time.time()
    if _cache and (now - _cache_time) < CACHE_TTL:
        return _cache
    if run_full_validation:
        try:
            report = asyncio.run(run_full_validation())
            _cache = {
                "base_score": report.platform_score,
                "transcendent_bonus": round(report.transcendent_bonus, 1),
                "final_score": report.final_score,
                "certification": report.platform_certification.value,
                "total_tests": report.total_test_count,
                "total_sloc": report.total_source_lines,
                "module_count": len(report.modules),
                "pass_rate": report.overall_pass_rate,
                "modules": {
                    name: {
                        "score": s.overall_score(),
                        "cert": s.certification.value,
                        "tests": s.test_count,
                    }
                    for name, s in report.modules.items()
                },
                "bonuses": {
                    "swarm_intelligence": report.bonuses.swarm_intelligence,
                    "recursive_self_improve": report.bonuses.recursive_self_improve,
                    "compression_transcend": report.bonuses.compression_transcend,
                    "zero_cost_operation": report.bonuses.zero_cost_operation,
                    "adaptive_resilience": report.bonuses.adaptive_resilience,
                    "cross_domain_intel": report.bonuses.cross_domain_intel,
                    "hermeneutic_closure": report.bonuses.hermeneutic_closure,
                    "temporal_autonomy": report.bonuses.temporal_autonomy,
                },
                "recommendations": report.recommendations,
                "signal_dbm": report.wifi_signal_dbm,
                "signal_concurrency": report.wifi_concurrency_safe,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            _cache_time = now
            return _cache
        except Exception as e:
            pass
    
    # Fallback — validation engine unavailable
    return {
        "base_score": "—",
        "transcendent_bonus": "—",
        "final_score": "—",
        "certification": "Offline",
        "total_tests": "—",
        "total_sloc": "—",
        "module_count": 0,
        "pass_rate": "—",
        "modules": {},
        "bonuses": {
            "swarm_intelligence": 0, "recursive_self_improve": 0,
            "compression_transcend": 0, "zero_cost_operation": 0,
            "adaptive_resilience": 0, "cross_domain_intel": 0,
            "hermeneutic_closure": 0, "temporal_autonomy": 0,
        },
        "recommendations": ["Validation engine unavailable — run from project root"],
        "signal_dbm": "—",
        "signal_concurrency": "—",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error": "validation engine not available",
    }


def get_swarm_status() -> Dict[str, Any]:
    signal = -60
    concurrency = 50
    if WiFiReader:
        try:
            reader = WiFiReader()
            signal = reader.signal_dbm
            if signal > -48:       concurrency = 80
            elif signal > -52:     concurrency = 70
            elif signal > -56:     concurrency = 60
            elif signal > -60:     concurrency = 50
            elif signal > -65:     concurrency = 40
            elif signal > -70:     concurrency = 25
            else:                  concurrency = 15
        except Exception:
            pass
    return {
        "signal_dbm": signal,
        "concurrency": concurrency,
        "interface": "wlp4s0",
        "turbocharger": _check_turbocharger(),
    }


def _check_turbocharger() -> bool:
    try:
        import urllib.request
        with urllib.request.urlopen("http://localhost:8922/health", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


START_TIME = time.time()


# ── Routes ───────────────────────────────────────────────────────────────

async def homepage(request):
    validation = get_cached_validation()
    swarm = get_swarm_status()
    uptime = int(time.time() - START_TIME)
    
    ctx = {
        "request": request,
        "score": validation,
        "swarm": swarm,
        "uptime": uptime,
        "now": datetime.now().strftime("%H:%M:%S"),
    }
    
    template = jinja_env.get_template("dashboard.html")
    return HTMLResponse(template.render(ctx))


async def api_score(request):
    return JSONResponse(get_cached_validation())


async def api_modules(request):
    v = get_cached_validation()
    return JSONResponse(v.get("modules", {}))


async def api_swarm(request):
    return JSONResponse(get_swarm_status())


async def api_events(request):
    events = []
    if bus:
        try:
            events = bus.get_history()[-20:]
            events = [{"topic": e.topic, "source": e.source, "time": str(e.timestamp)} for e in events]
        except Exception:
            pass
    return JSONResponse({"events": events, "count": len(events)})


async def api_health(request):
    return JSONResponse({
        "status": "healthy",
        "uptime": int(time.time() - START_TIME),
        "platform": "connected" if platform else "disconnected",
        "validation": "available" if run_full_validation else "unavailable",
    })


# ── App ──────────────────────────────────────────────────────────────────

app = Starlette(debug=False)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.routes.extend([
    Route("/", homepage),
    Route("/api/score", api_score),
    Route("/api/modules", api_modules),
    Route("/api/swarm", api_swarm),
    Route("/api/events", api_events),
    Route("/api/health", api_health),
])

if STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

# ── Startup ──────────────────────────────────────────────────────────────

print()
print("╔══════════════════════════════════════════════════════╗")
print("║     ENTERPRISE PLATFORM DASHBOARD — BOOTING         ║")
print("╚══════════════════════════════════════════════════════╝")

# Warm cache
validation = get_cached_validation()
score = validation.get("final_score", "?")
cert = validation.get("certification", "?")
mods = validation.get("module_count", "?")
tests = validation.get("total_tests", "?")

print(f"  Platform Score: {score} — {cert}")
print(f"  Modules: {mods}  |  Tests: {tests}")
print(f"  Dashboard: http://0.0.0.0:8421")
print("╚══════════════════════════════════════════════════════╝")
print()