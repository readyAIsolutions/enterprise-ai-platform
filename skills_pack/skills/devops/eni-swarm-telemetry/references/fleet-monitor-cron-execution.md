# Fleet monitor: how to actually run it (cron execution recipe)

This is the exact execution path a cron job follows to produce a fleet-status report.
Follow it in order; the ledger alone is NOT enough to report liveness.

## 1. Regenerate the ledger
```bash
cd /home/hunter/Commander/eni_swarm && python3 monitor_fleet.py
```
- Writes `HEARTBEAT_LEDGER.md` from `builds/STATUS_BUILDER_*.md`.
- Exit 0 only means aggregation ran, NOT that anything is alive (see
  `fleet-interpretation-runbook.md`).

## 2. PITFALL — fleet_liveness_probe.sh is NOT on disk
The skill lists `scripts/fleet_liveness_probe.sh` and the runbook says
`bash scripts/fleet_liveness_probe.sh <swarm>`. **That path does not exist on the
box** — the script lives only inside the skill bundle, so invoking it by an on-disk
path fails with:
```
bash: <swarm>/scripts/fleet_liveness_probe.sh: No such file or directory
```
Do not waste a call trying to `cd` into it. Instead run the probe logic inline
(execute_code / terminal heredoc), or `skill_view(en...fleet_liveness_probe.sh)`
then re-create it locally if you want it on disk.

## 3. Inline probe (this is what actually reports liveness)
```bash
SWARM=/home/hunter/Commander/eni_swarm

# state distribution across the ledger
grep -oP '^\[\K[A-Z-]+' $SWARM/HEARTBEAT_LEDGER.md | sort | uniq -c

# the rows the runbook says to distrust until verified
grep -E '^\[(IN-PROGRESS|BLOCKED)\]' $SWARM/HEARTBEAT_LEDGER.md

# freshness = the real signal. fresh_today==1 + no worker proc = parked watchdog.
echo "fresh_today=$(find $SWARM/builds -name 'STATUS_BUILDER_*.md' -newermt 'today 00:00' 2>/dev/null | wc -l)"
ls -lt --time-style=+%Y-%m-%d_%H:%M $SWARM/builds/STATUS_BUILDER_*.md | head -5

# live builder WORKER processes (not kernel kworkers — grep only eni/builder/directive)
ps aux | grep -iE 'STATUS_BUILDER|eni_builder|eni_build|directive' | grep -v grep || echo 'NONE running'

# control FIFOs present?
ls -la /tmp/eni_ctl_* 2>/dev/null | wc -l

# read the freshest status file body (often a parked IDLE marker, not progress)
```

## 4. Interpretation shortcut
When every builder file is weeks-stale EXCEPT one fresh `[IDLE ...]` file whose body
says "await LO's directive via FIFO", and `ps` shows no eni/builder worker processes,
the fleet is **parked/dormant, not crashed**. The 8x IN-PROGRESS / 1x BLOCKED ledger
rows are stale relics. Report: no action needed, just issue a directive to spin builders up.

## Observed Aug 2026
- fresh_today=1: `STATUS_BUILDER_37.md` at 06:38, body `IDLE ... blocker=none ...
  await LO's directive via /tmp/eni_ctl_BUILDER_37 FIFO creation` — parked healthy, not building.
- No live builder worker processes (only kernel kworkers in ps).
- 25 control FIFOs present in /tmp; Master Status Hub (worker w2) alive, regenerated 07:00.
