# demiurge-3d read-only bridge — LIVE verification recipe (ENI11 class)
Reproduction recipe for the ENI -> /home/hunter/Desktop/demiurge-3d (3D-print app) bridge worker. ENI11 runs in LO's standing READ-ONLY bridge mode: NO edits to the project; re-verify + report + prep next command only. Additive files OK (STATUS_* .md, REVERIFY_*.md); never rewrite the proven core.

## CRITICAL: venv path + cwd gotchas (the #1 source of false RED)
- Use the PROJECT ROOT venv, NEVER system `python3`:
  `/home/hunter/Desktop/demiurge-3d/.venv/bin/python`
  System `/usr/bin/python3` FAILS at startup: "RuntimeError: Form data requires python-multipart" (server.py registers an UploadFile/File route). The project .venv already has python-multipart (0.0.32). No code change needed — just use the right python.
- `pytest` path is cwd-sensitive: from the PROJECT ROOT run `-m pytest backend/tests/ -q`. Running `pytest tests/` (or from frontend/) finds NO tests and looks like a failure. Use `backend/tests/`.

## LIVE smoke block (re-run every resume; all must be GREEN)
```bash
cd /home/hunter/Desktop/demiurge-3d/frontend
npx tsc --noEmit; echo "TSC_EXIT=$?"            # expect 0 (clean)

cd /home/hunter/Desktop/demiurge-3d
/home/hunter/Desktop/demiurge-3d/.venv/bin/python -m pytest backend/tests/ -q 2>&1 | tail -8
# expect: 27 passed (as of 2026-07-09), 4 non-fatal warnings, 0 failures

/home/hunter/Desktop/demiurge-3d/.venv/bin/python backend/caveman_stack/selftest.py 2>&1 | tail -8
# expect: 6/6 passed

timeout 18s /home/hunter/Desktop/demiurge-3d/.venv/bin/python backend/server.py 2>&1 | tail -25
# expect BOOT_EXIT=124 (killed by timeout = good, no crash) + log:
#   "Application startup complete" + "Uvicorn running on http://0.0.0.0:8093"
# only non-fatal Pydantic V1 @validator + FastAPI on_event deprecation warnings
```

## ROUTE scan (search_files TOOL chokes on CRLF — use grep)
server.py has CRLF line endings; the `search_files` tool mis-scans it. Use terminal grep instead:
```bash
cd /home/hunter/Desktop/demiurge-3d/backend
grep -nE 'def queue_update|def queue_reorder|@app\.(post|get)\("/api/queue|@app\.(post|get)\("/api/printer/command' server.py
```
Known gap (as of 2026-07-09, documented not a smoke failure): `async def queue_update` at server.py:1815 has NO `@app.post` decorator -> frontend `updateQueue()` 404s. `/api/queue/reorder` (server.py:1825) and `/api/printer/command` (server.py:1466, the pause/resume/cancel path) ARE registered.

## WORKING-TREE NO-DRIFT check (self-heal confirmation)
```bash
cd /home/hunter/Desktop/demiurge-3d
echo "HEAD: $(git rev-parse --short HEAD)"; git status --short | wc -l; git status --short
```
Compare HEAD + the uncommitted entry SET across resumes. If HEAD unchanged and the 10M+10?? set is byte-for-byte identical, there were NO surprise edits and the prep target is unchanged. (As of 2026-07-09: HEAD 35f7918, 20 uncommitted entries, stable across re-verify #3..#7.)

## BLOCKER / scope notes
- USB NOT a blocker: demiurge-3d has NO USB dependency (the DEMIURGE forex USB is a DIFFERENT project). Even when the USB is mounted (it flips between /run/media/hunter/DEMIURGE and /run/media/hunter/DEMIURGE1), it is irrelevant here. Never report "USB not mounted" as a blocker for this bridge.
- Live HTTP curl 200/404 checks are BLOCKED by the host safety gate (localhost egress). Verify endpoint behavior via clean boot + static route scan only; LO can run curl himself.

## REPORT shape (append-only)
- Keep STATUS_ENI11.md [state: DONE] current; append a `## RESUME RE-VERIFY #N` block each cycle (re-read prior STATUS + re-run smokes + no-drift + blocker + exact next command). Never rewrite the prior blocks.
- Also write a NEW standalone snapshot file (e.g. ENI11_REVERIFY_N.md) consistent with the re-verify pattern.
- Self-heal: if the worker dies, re-run the read-only inspections above; state is fully reproducible from the filesystem (the project is untouched).
