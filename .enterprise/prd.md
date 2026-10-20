# .enterprise/prd.md — Dashboard Timeout Fix + Overnight Training

References: `/home/hunter/Desktop/Enterprise Builder/enterprise/` + `fly_brain/` desktop project.

## ACCEPTANCE CRITERIA (inputs/outputs/failure resolved FIRST)

**Dashboard fix:**
- Input: `python3 dashboard_server.py` starts HTTP server on port 8926
- Output: server stays alive indefinitely (no timeout), serves dashboard HTML at `/`, SSE at `/metrics`
- Failure: port in use → kill old process, retry; dashboard HTML missing → 404 with file path in log
- Regression test: start server, sleep 300s (5min), curl / → still returns 200 with "FlySwarm" title

**Overnight training:**
- Input: SWARM_STEPS=100000, 4 bees, headless_swarm.py launched in background
- Output: 400,000 total training steps, checkpoints every 10,000 steps, final report JSON
- Failure: NaN → log and continue; SIGTERM → save checkpoint; disk full → warn
- Success: loss < 3.0 AND bpb < 20.0

## ROOT CAUSE (dashboard timeout)

**Minimal reproduction:** Run `trainer_v2.py` → training finishes in 3s → server stays alive → terminal timeout at 180s kills process → `curl http://127.0.0.1:8926/` returns connection refused.

**Root cause:** Dashboard HTTP server is embedded in training script. Two problems:
1. Training completes quickly (3s), server stays alive but terminal kills it at 180s
2. No separation of concerns — training and serving are coupled

**Sibling call sites checked:**
- `trainer_v2.py` line 84-88: `HTTPServer((127.0.0.1, PORT), Dashboard)` + `serve_forever()` — embedded server
- `headless_swarm.py` — no HTTP server (correct)
- `extended_swarm.py` — no HTTP server (correct)
- `fly_serve.py` — separate HTTP server for inference, not dashboard

**Fix:** Create standalone `dashboard_server.py` that:
1. Starts HTTP server on port 8926
2. Serves `/` (dashboard HTML) and `/metrics` (SSE)
3. Reads metrics from shared state file (`/tmp/flyswarm_state.json`) updated by training scripts
4. Stays alive indefinitely — no timeout dependency
5. Training scripts write to shared state file, not serve HTTP

## WHERE IT LIVES

- `flytrainer/dashboard_server.py` — NEW standalone persistent dashboard server
- `flytrainer/trainer_v2.py` — updated to write to shared state file instead of serving HTTP
- `/tmp/flyswarm_state.json` — shared state between trainer and dashboard

## REGRESSION TEST

1. Start dashboard server in background
2. Wait 300 seconds (5 minutes)
3. curl http://127.0.0.1:8926/ → 200 OK with "FlySwarm" in body
4. curl http://127.0.0.1:8926/metrics → SSE event stream
5. Kill dashboard, verify port released
6. Pass: server survives 5+ minutes without timeout

## BACKWARDS COMPATIBILITY

- trainer_v2.py keeps HTTP serve mode as fallback (--serve flag)
- headless_swarm.py and extended_swarm.py unchanged
- New file only: dashboard_server.py

## DEFINITION OF DONE

- Dashboard server survives 5+ minutes without timeout (regression test passes)
- Overnight training launched with 100K steps per bee
- Checkpoints saved every 10K steps
- No port conflicts
- No stubs, English only