# Fleet systemd user-unit health — include in every monitor pass

The four file/port axes (builder floor / :8420 dashboard / :8922 turbocharger / status_hub controller) cover on-disk and TCP health, but the swarm also runs under `systemd --user`. A full fleet-health pass should ALSO survey user units, because a crash-looping unit can burn CPU/restarts indefinitely and is invisible to the port probes.

## Add to the pass (one terminal call)
```bash
systemctl --user list-units --all 2>/dev/null | grep -iE "swarm|dash|turbo|creed"
```
Plus, if any unit looks suspect:
```bash
systemctl --user status <unit>.service 2>&1 | head -20
journalctl --user -u <unit>.service -n 15 --no-pager
```

## Diagnostic signature — "activating (auto-restart)" + huge restart counter + exit 2
Observed 2026-08: `eni-impossible-swarm.service` sat in `activating (auto-restart)` with a **restart counter ~77,000+**, `Main PID ... status=2/INVALIDARGUMENT` every ~10s.

This means the unit **starts, fails immediately, and systemd retries forever**. The #1 cause is a stale `ExecStart` path:

- `ExecStart=/usr/bin/python3 <path>` where `<path>` does not exist on disk.
- Diagnose instantly by running the ExecStart target directly:
  ```bash
  python3 <path-to-exe> 2>&1   # -> "can't open file ... No such file or directory"
  ```
  If the file is gone, that's the whole story — no deeper crash to debug.

## Deciding fix vs disable
- If the target was MOVED (e.g. archived to a .7z / KB), restore it OR point `ExecStart` at the live copy via `systemctl --user edit`.
- If the script is genuinely gone and not needed to serve the live fleet, stop the churn:
  ```bash
  systemctl --user disable --now eni-impossible-swarm.service
  ```
  (Note: `enable`d+`auto-restart` units keep re-spawning every few seconds until stopped — they do NOT stop on their own.)

## Don't-misflag trap
A crash-looping service is a REAL interrupt, but it is NOT a port-occupied conflict and NOT a fleet-outage on the floor. Report it as its own line under "separate issues", alongside — not mixed with — the axis status. Do not attempt to "fix" a missing binary by installing anything; restore or disable is the whole decision space.