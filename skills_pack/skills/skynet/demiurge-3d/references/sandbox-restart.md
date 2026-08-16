# Sandbox server-restart caveat (kill stale uvicorn)

When restarting the Demiurge backend in the agent sandbox, the documented
`pkill -f "uvicorn server:app"` can return exit code `-15` and the terminal tool
reports the command as "failed" because the signal also touches the shell's own
process group. This is COSMETIC — the old server IS killed. Do not loop on it.

Reliable kill-and-restart sequence (avoid self-signaling the shell):
1. Find the holder without pkill:
   `ss -tlnp 2>/dev/null | grep 8093`   -> note PID
2. Kill that specific PID:
   `kill <PID>`   (or `for p in $(pgrep -f "uvicorn server:app"); do kill $p; done`)
3. `sleep 1`
4. `rm -rf __pycache__ forge/__pycache__`  (drop stale compiled route table)
5. Start fresh on 8093 via `terminal(background=true)` (notify_on_complete=false).
6. Verify with `curl` on :8093 — NOT :8000.

Symptom that means a stale server is shadowing your edits: you change `server.py`,
restart, but the browser still 404s a route you just added. The old process
(predating your edit) is still bound to 8093. Kill by PID, clear pycache, restart.

NOTE: `pkill` self-signaling is environment-specific to the sandbox; on the host
it behaves normally. This note is about avoiding a confusing terminal-tool
"failure" loop, not about the kill not working.
