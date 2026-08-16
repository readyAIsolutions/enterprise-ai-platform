# Demiurge live-debug workflow (sandbox cannot reach LAN printers)

Durable debugging technique for Demiurge backend work against LO's LAN printers
(192.168.1.x). Captured after a long thrash where endpoints returned stale/empty
data and the agent could not see why.

## HARD FACT: the agent sandbox has NO network reach to 192.168.x.x
- Every `ping`/`nc`/`curl` to the printers from the agent shell returns EMPTY
  output (even `curl -v`), regardless of exit code. The DEVICE itself can reach
  them; the AGENT process cannot.
- Consequence: you CANNOT probe camera URLs, run `BELT_MDL_INFO`, or verify
  printer output from the agent shell. Do NOT loop on curl-to-LAN — it's blind.
- Instead: (a) run diagnostic scripts ON THE BOX via the ssh'd session if one
  exists, or (b) ask LO to paste the real console output / open the URL in a
  browser and tell you what shows. His eyes close the gap.

## Stale-endpoint trap (uvicorn returns old-shaped data)
Symptom: you edit `server.py`, restart uvicorn, but the live endpoint still
returns the OLD response shape (e.g. bare `[]` instead of your new `{_debug:...}`).
Root causes found this session:
1. A LEFTOVER non-uvicorn python worker holding :8093 (from a `--reload`
   reloader child, or an old `demiurge_backup` server). `pgrep uvicorn` shows
   nothing but `ss -ltnp` reveals a `python3` pid on the port. Kill THAT pid.
2. `kill -9 $PID` where PID came from `ss` can grab a stale process while a new
   one already bound. Always re-verify `ss -ltnp | grep ':8093'` is FREE before
   relaunching, and confirm the new pid in the launch log.
3. `search_files` on large files (server.py ~93KB) silently returns 0 matches
   for patterns that DO exist — use `grep -n` via terminal instead.

## Reliable restart sequence
1. `pkill -9 -f uvicorn` (may need a second explicit `kill -9 <pid>` on the
   non-uvicorn holder from `ss`).
2. Confirm `ss -ltnp | grep ':8093'` is empty.
3. `cd ~/Desktop/Demiurge3D/backend && source ../.venv/bin/activate &&
   uvicorn server:app --host 0.0.0.0 --port 8093` (background=true).
4. Sleep ~8s, then `curl localhost:8093/api/printer/5/cameras` to confirm.

## Self-heal pattern (so startup-time probe flakes never blank the UI)
If discovery depends on a live probe at startup, add an on-demand rediscover in
the GET route: `if not m.cameras: await m.discover_cameras()`. But better:
register known-good resources UNCONDITIONALLY (don't gate on probe), and let the
probe only upgrade/fallback, never drop.
