# Fleet-Monitor Cron — [SILENT] Break Decision: One-Shot Verify Block

Run before emitting a fleet-monitor report, to decide whether this firing is
identical to the prior one (→ `[SILENT]`) or contains genuine change (→ report).
Suppression discipline lives in `monitor_cron_diagnostics.md` (7 criteria).
This is the compact ready-to-run confirmation block mirroring those criteria
in a single terminal call. Outputs `(none above ...)` / `000` / stale FIFO /
"no such file" → same-signature dormancy, safe to suppress.

```bash
cd /home/hunter/Commander/eni_swarm
echo "=== STATUS files touched today? ==="
find . -name 'STATUS_BUILDER_*.md' -newermt "$(date +%Y-%m-%d) 00:00" 2>/dev/null   # none = no build activity
echo "=== dashboard :8420 today? ==="
curl -s -o /dev/null -w 'health=%{http_code}\n' --max-time 4 http://127.0.0.1:8420/health  # 000 = still down
echo "=== newest control FIFOs ==="
ls -la /tmp/eni_ctl_BUILDER_* 2>/dev/null | tail -3   # only stale = no new dispatch requests
echo "=== alerts file present? ==="
ls -la HEARTBEAT_ALERTS.md 2>&1 | head -1   # "No such file" is the standing normal state
```

## Decision summary (all unchanged → [SILENT])
- No `STATUS_BUILDER_*.md` touched since midnight → floor not mid-work
- `:8420` health `000`/not bound → dashboard outage is chronic, already flagged, not new
- `:8922` health `200`/bound + `MASTER_STATUS.md` freshly refreshed → controller healthy (routine 5-min self-heal, NOT a state change)
- No NEW `/tmp/eni_ctl_BUILDER_*` FIFO (oldest is fine; only a FIFO newer than the last report is a signal)
- `HEARTBEAT_ALERTS.md` absent → expected standing state (monitor_fleet.py's blocked_builders path stays inert)

## Location note
`fleet_health_probe.sh` may exist BOTH in this skill's `scripts/` dir and at
`eni_swarm/fleet_health_probe.sh` (an earlier session recreated the local copy
when the skill copy was momentarily absent). Prefer the skill copy. If you must
recreate the local one, port the skill version's content verbatim — do NOT
hand-write a different probe, or the axes reported can silently diverge.