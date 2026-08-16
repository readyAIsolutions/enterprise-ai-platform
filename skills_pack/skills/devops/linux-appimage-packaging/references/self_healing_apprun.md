# Self-healing AppRun — crash-resilient launcher

## When to use
A desktop GUI that "must never silently die" (kiosk, control-panel, fleet
dashboard). Two independent failure planes need two independent restarters:

1. **In-process (Python):** an uncaught exception or a deliberate non-zero exit
   is caught and the UI is rebuilt + relaunched inside the same process.
   Bounded by a restart budget so a persistently-crashing app doesn't spin
   forever.
2. **Process-level (AppRun shell loop):** a hard segfault / aborted child
   outside Python's try/except is relaunched by the `while` loop. The Python
   supervisor CANNOT catch these, so this layer is mandatory for true
   resilience.

Make the shell loop the ONLY process-level restart authority: run the app with
`--no-supervise` so the Python side does NOT also fork. Two owners of the same
restart decision fight each other (double-restart, confusing logs).

## The validated loop (set -u, NOT set -e)
```sh
#!/bin/sh
set -u
HERE="$(dirname "$(readlink -f "$0")")"
APP_MODULE="${APP_MODULE:-demiurge.frontend_qt}"
RESTART_BUDGET="${RESTART_BUDGET:-5}"
PYBIN="$HERE/usr/bin/python3"; [ -x "$PYBIN" ] || PYBIN="$(command -v python3)"
PVER="$("$PYBIN" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo 3)"
export PYTHONPATH="$HERE/usr/lib/python$PVER/site-packages:$HERE/usr/share/app:${PYTHONPATH:-}"
export PYTHONPATH="$PYTHONPATH:/usr/lib/python3/dist-packages"
restarts=0
while true; do
  "$PYBIN" -m "$APP_MODULE" --no-supervise "$@"; code=$?
  [ "$code" -eq 0 ] && exit 0
  restarts=$((restarts+1))
  if [ "$restarts" -ge "$RESTART_BUDGET" ]; then
    echo "ERROR: $APP_MODULE exceeded restart budget ($RESTART_BUDGET); giving up." >&2
    exit 1
  fi
  echo "WARN: $APP_MODULE exited $code; self-healing ($restarts/$RESTART_BUDGET)..." >&2
  sleep 1
done
```

## The `set -e` pitfall (the war story)
The first version of the loop above had `set -e` at the top. With `set -e`,
bash aborts the script the instant a child returns non-zero — i.e. the exact
event the loop exists to recover from. Result: the app crashed ONCE, the loop
printed nothing, and the whole AppImage exited. Removing `-e` (keeping `-u`)
made the loop iterate through the full budget (5 restarts) and then exit 1 with
a clear message. **Rule: any wrapper whose purpose is to relaunch a failing
child must not use `set -e`.** `set -u` is fine (catches undefined vars early).

## How to VERIFY the loop without a real GUI
Don't launch the actual (slow) Qt app just to test the loop. Point `APP_MODULE`
at a stub that always exits non-zero:
```
APP_MODULE="a.module.that.does.exit.1" bash AppRun
```
Expected: 5 `WARN: ... self-healing (N/5)...` lines, then
`ERROR: ... exceeded restart budget (5); giving up.` and wrapper exit 1.
Then verify the happy path: a real run that exits 0 must leave the loop
immediately (no spurious restart). For a headless Qt app, run it under
`QT_QPA_PLATFORM=offscreen` and `timeout 3` it; the loop should run the full
duration with no `WARN` lines (exit 124 from timeout = "ran, didn't crash").

## System-wide PyQt6 fallback
When PyQt6 lives at `/usr/lib/python3/dist-packages` (system-wide, NOT in the
bundled venv) and you choose not to bundle Qt, append it to `PYTHONPATH`
additively. Keep the bundled stdlib/site-packages first so the app's own code
still resolves. `PyQt6.QtWebEngineWidgets` is often missing even when `PyQt6`
imports — so build native Qt widgets and open any web dashboard in the system
browser, never embed it.
