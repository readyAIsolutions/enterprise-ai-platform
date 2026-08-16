# Demiurge 3D — K2 Plus camera discovery (fix + pitfalls)

## K2 Plus camera reality (LO's fleet, 2026-07-16)

- NOZZLE cam: live, served at `http://<host>:8081/snapshot`. This is the feed
  that ALWAYS works. It is a single JPEG snapshot endpoint (not MJPEG stream).
- CHAMBER cam: the printer's main webcam. Path varies by firmware. On LO's
  units the `:4408/webcam2/?action=stream` path is DEAD. `:4408/webcam/` may
  answer intermittently. Treat chamber as "probe only, show only if it actually
  responds" — never show a dead "Chamber" tile.
- Earlier discovery code had the labels SWAPPED (working `:8081` feed tagged
  `chamber`, dead `:4408/webcam2` tagged `nozzle`) AND gated both cams behind a
  live probe, so a startup-time blip hid the working nozzle too.

## Correct discover_cameras pattern (demiurge/printer/manager.py)

1. Register the NOZZLE unconditionally (OUTSIDE any try). LO confirmed
   `:8081/snapshot` works — a flaky chamber probe or startup network blip must
   NEVER hide it. Use the snapshot URL as both stream_url and snapshot_url
   (CameraStream polls snapshot URLs via cache-buster, which renders reliably
   cross-origin where raw MJPEG often does not).
2. Probe CHAMBER candidates (`{camera_base}/webcam/?action=stream`,
   `.../webcam/?action=snapshot`, `http://<host>:8080/webcam/?action=stream`,
   `http://<host>:8080/snapshot`). Add the first that answers image/mjpeg.
   If none respond -> no chamber cam (no false tile).
3. Dedup by STREAM url: if the chamber resolves to the SAME url the nozzle
   already uses, skip it (firmware quirk can make both candidates resolve to
   one feed).
4. Make the `/api/printer/{id}/cameras` route SELF-HEAL: if `m.cameras` is
   empty at request time, re-run `discover_cameras()` (best-effort, timeout
   ~12s) before returning. Startup discovery can miss cams if the printer is
   mid-connect.
5. Frontend: key React camera tiles by `cam.id` (backend-supplied, unique per
   kind+stream_url), never by `cam.kind` (duplicate-key bug collapsed 2 cams
   to 0).

## PITFALL — agent shell has NO LAN egress to 192.168.x.x

The agent sandbox CANNOT reach the printers directly. Every `curl`/`ping`/`nc`
to `192.168.1.65`/`.66` from the agent terminal returns EMPTY (even `curl -v`,
even `ping`), and `execute_code`'s `terminal()` does too. The Demiurge
SERVER, however, runs on LO's box and CAN reach them — that's why the
`/cameras` API "succeeds" while agent-shell probes show nothing.

Therefore, to debug camera discovery, do NOT probe the printer IP from the
agent shell. Instead:
- Run a Python script ON THE BOX via the venv (write it to
  `/home/hunter/.cache/d3d_tmp/`, then `terminal` `python3 script.py` with
  `source ../.venv/bin/activate`). A standalone
  `from demiurge.printer.manager import PrinterManager; m=...; await
  m.discover_cameras()` against `http://192.168.1.65:7125` reaches the printer
  and reveals the real cam list. This is the authoritative test.
- OR hit the localhost API (`curl localhost:8093/api/printer/5/cameras`) — the
  server does the LAN reach for you.

## PITFALL — live process not reflecting on-disk edits (stop reboot-looping)

Symptom observed: edited `server.py` (added a `_debug` dict to the `/cameras`
response), rebooted uvicorn ~10x on 8093, yet the live endpoint kept returning
the OLD bare `[]` shape. The process serving the port was launched from the
correct dir with `--reload`, but the response never matched on-disk code.

Root cause was NOT isolatable from the agent shell (could be a stale worker, a
shadowed `server.py` import, or a second service). The durable lesson:
- When the live server's RESPONSE SHAPE does not match the on-disk code, DO NOT
  keep kill-restart-looping. Each blind reboot burned a cycle and taught nothing.
- Instead: (a) confirm the frontend/port target (is the UI actually pointed at
  `localhost:8093`, or at the old `demiurge_backup` instance / a different port?),
  (b) ask LO to do ONE clean manual restart from a terminal on his box, or
  (c) add a unique marker string to the response and verify it appears — if it
  does not, the served module is not your file.
- Verify the right process holds 8093: `ss -tlnp | grep 8093` and cross-check
  the PID's launch cwd. Kill stale holders by PID, not by blanket `pkill`.
