#!/usr/bin/env python3
"""Enterprise Platform Dashboard — SINGULARITY Edition. :8421."""
import json, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
VALIDATION_SCRIPT = str(HERE / "run_validation.py")

from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route
from starlette.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from jinja2 import Environment, FileSystemLoader

jinja_env = Environment(loader=FileSystemLoader(str(HERE/"templates")), autoescape=True)
START_TIME = time.time()
_cache = {}
_cache_time = 0.0

def _run_validation():
    """Run validation as subprocess — no import path issues."""
    try:
        result = subprocess.run(
            [sys.executable, VALIDATION_SCRIPT],
            capture_output=True, text=True, timeout=30,
            cwd="/home/hunter/Desktop/Enterprise Builder"
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except Exception:
        pass
    return None

def _get_validation():
    global _cache, _cache_time
    now = time.time()
    if _cache and (now - _cache_time) < 5:
        return _cache
    data = _run_validation()
    if data:
        _cache = data
        _cache_time = now
        return data
    return {"final_score": "—", "certification": "Offline", "module_count": 0,
            "total_tests": "—", "base_score": "—", "transcendent_bonus": "—",
            "modules": {}, "bonuses": dict.fromkeys([
                "swarm_intelligence","recursive_self_improve","compression_transcend",
                "zero_cost_operation","adaptive_resilience","cross_domain_intel",
                "hermeneutic_closure","temporal_autonomy"], 0),
            "recommendations": ["Validation engine offline"], "signal_dbm": "—"}

def _get_swarm():
    signal, concurrency = -60, 50
    try:
        out = subprocess.run(["iw", "dev", "wlp4s0", "link"], capture_output=True, text=True, timeout=3)
        import re
        m = re.search(r"signal:\s*(-?\d+)\s*dBm", out.stdout)
        if m:
            signal = int(m.group(1))
            if signal > -48: concurrency = 80
            elif signal > -52: concurrency = 70
            elif signal > -56: concurrency = 60
            elif signal > -60: concurrency = 50
            elif signal > -65: concurrency = 40
            elif signal > -70: concurrency = 25
            else: concurrency = 15
    except: pass
    turbo = False
    try:
        import urllib.request
        with urllib.request.urlopen("http://localhost:8922/health", timeout=2) as r:
            turbo = r.status == 200
    except: pass
    return {"signal_dbm": signal, "concurrency": concurrency, "interface": "wlp4s0", "turbocharger": turbo}

async def home(req):
    v = _get_validation()
    s = _get_swarm()
    ctx = {"request": req, "score": v, "swarm": s, "uptime": int(time.time()-START_TIME), "now": datetime.now().strftime("%H:%M:%S")}
    return HTMLResponse(jinja_env.get_template("dashboard.html").render(ctx))

async def api_score(req): return JSONResponse(_get_validation())
async def api_modules(req): return JSONResponse(_get_validation().get("modules", {}))
async def api_swarm(req): return JSONResponse(_get_swarm())
async def api_events(req): return JSONResponse({"events": [], "count": 0})
async def api_health(req): return JSONResponse({"status": "healthy", "uptime": int(time.time()-START_TIME)})

app = Starlette(debug=False)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.routes.extend([
    Route("/", home), Route("/api/score", api_score), Route("/api/modules", api_modules),
    Route("/api/swarm", api_swarm), Route("/api/events", api_events), Route("/api/health", api_health),
])
if (HERE/"static").exists(): app.mount("/static", StaticFiles(directory=str(HERE/"static")), name="static")

# Warm cache on startup
v = _get_validation()
print(f"\n  DASHBOARD: http://0.0.0.0:8421  |  {v.get('final_score','—')} {v.get('certification','')}\n")

if __name__ == "__main__":
    import uvicorn; uvicorn.run(app, host="0.0.0.0", port=8421, log_level="info")