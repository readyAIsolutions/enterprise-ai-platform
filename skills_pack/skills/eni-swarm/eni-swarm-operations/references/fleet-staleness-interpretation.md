# Fleet Monitor — interpreting stale vs. live state

## First — know which monitor you are reading (TWO exist, do not conflate)
- **`monitor_fleet.py`** → writes `HEARTBEAT_LEDGER.md`. Scans ONLY the
  top-level `builds/STATUS_BUILDER_*.md` files (~50 builders). It is a report of the builder
  floor. NOTE: it ALSO runs as a scheduled fleet-monitor cron (seen firing 2026-08 as a cron
  job producing the standard dormant-fleet report) — do not assume it is manual-only; either
  way it is report-only and must never dispatch/edit builder files. It can be re-run ad hoc via
  `python3 monitor_fleet.py` and self-heals the ledger.
- **`status_hub.py` (ACTIVE, separate 5-min cron)** → writes `MASTER_STATUS.md`. Recursively scans
  EVERY `STATUS_*` file across `eni_swarm/` AND `demiurge_scaffold/` (the full wider mini-fleet,
  ~598 minis: 207 DONE / 388 IN-PROGRESS / 3 BLOCKED / 391 ALERTS). It is the true fleet-wide
  truth source and self-heals on re-run.
- A current `crontab -l` shows `*/5 * * * * cd /home/hunter/Commander/eni_swarm && python3 -W
  ignore status_hub.py >> status_hub.cron.log`. Check that log for the authoritative refresh
  line. When reporting fleet health, cite `MASTER_STATUS.md` (the active hub), not just the
  legacy builder ledger.
- **ALERTS ≈ stale IN-PROGRESS, not failures.** status_hub flags `ALERT` when `STATE==BLOCKED` OR
  `(STATE != DONE AND age > 10 min)`. On a dormant fleet a huge ALERTS count (e.g. 391) just means
  nearly every non-DONE mini is old — it is noise, not a real incident.

The single most important analytical step when running/reading `monitor_fleet.py`.
A freshly-written ledger can show **8 IN-PROGRESS + 1 BLOCKED** while the fleet is
actually **fully dormant**. Never read the ledger state counts as "live activity" —
they are snapshots of whatever the STATUS files last recorded.

## Dormant-vs-live decision (do this every pass)

1. **mtime freshness cross-check** — this is the source of truth, not the ledger:
   ```bash
   stat -c '%y' builds/STATUS_BUILDER_*.md | awk '{print $1}' | sort | uniq -c
   ```
   All (or all but one) files on an old date = fleet dormant regardless of what the
   ledger's IN-PROGRESS/BLOCKED rows claim.

1a. **Single parking-date signature** — the strongest dormancy tell: when EVERY
   in-progress builder's mtime is the SAME old date (e.g. all `2026-07-25`, ~13 days
   back), that one shared date is the "floor-park" signature — the whole parallel-build
   floor was intentionally parked in a single earlier session and nothing has run since.
   A typical dormant-but-healthy fleet shows one early-Wednesday parking date for all
   active builders at once. You can recognize it in one glance:
   ```bash
   # all IN-PROGRESS/BLOCKED builders sharing one mtime date == parked floor
   for n in 05 17 25 32 38 39 42 44 46; do
     [ -f builds/STATUS_BUILDER_$n.md ] && \
       echo "$n $(stat -c '%y' builds/STATUS_BUILDER_$n.md | cut -d' ' -f1)"
   done | awk '{print $2}' | sort | uniq -c
   ```
   One date across all active builders = no per-builder churn since the park; report
   the date and the approximate age in minutes (~19000m ≈ 13 days) for readability.
   Do NOT attribute the single shared mtime to "these builders are working in sync" —
   it means the opposite.

   Alternative one-liner (equivalent, direct): which STATUS files changed recently?
   ```bash
   find builds/ -name "STATUS_BUILDER_*.md" -newermt "2026-08-06" 2>/dev/null
   ```
   A result listing exactly ONE builder (the daily-touch IDLE check-in) while the
   rest of the fleet predates the cutoff is the cleanest possible dormant proof —
   no guesswork comparing dates, just "only B37 touched a status file in the last 48h."

2. **Daily-touch correlation** — a single file with today's mtime usually means that
   builder merely checked in **IDLE** (e.g. re-verifying its FIFO doesn't exist), not
   that it's working. Read the file's head to confirm it says `IDLE` rather than an
   active task.

3. **Live-process / FIFO check** — corroborate dormancy:
   - `ps aux | grep -iE "builder|swarm"` (exclude chrome/gvfs/discord noise; the
     infra daemons — eni_controller serve, airllm_server, skill_forge_swarm,
     eni_kb_daemon, swarm_turbocharger — are NOT fleet builders).
   - When the dock already shows dozens of infra daemons (odoo/postgres/avahi etc.),
     narrow to find builder workers specifically with
     `ps aux | grep -iE "eni_swarm|STATUS_BUILDER|eni-mini|demiurge"` and expect
     ZERO matches for a dormant fleet — "no builder PIDs at all" is the strongest
     dormancy corroboration alongside stale mtimes. Report "no builder processes
     running" explicitly.
   - `ls /tmp/eni_ctl_BUILDER_*` — a control FIFO with no watcher process is orphaned
     (stale), not a sign of routing.
   - `curl -s http://127.0.0.1:8940/` — controller up but no per-builder route is
     normal-idle, not an error.

## The MASTER_STATUS.md alert layer (status_hub.py / worker w2)

A SECOND source feeds fleet reads: `status_hub.py` (worker w2, on the 5-min self-heal
cron) auto-generates `MASTER_STATUS.md` in `eni_swarm/`, consolidating every
`STATUS_ENI*.md` plus live-project `STATUS_*` recursively. It exposes four headline
counts — `DONE / IN-PROGRESS / BLOCKED / ALERTS` — plus a per-mini table.

**Read its alert rule before trusting the ALERTS count.** The rule is explicit in the
file: `ALERT raised when STATE==BLOCKED, OR (STATE != DONE AND age > 10 min)`. That
second clause means EVERY stale IN-PROGRESS file fires an alert. On a dormant fleet
the ALERTS total is therefore huge and is noise, not failure:

```bash
grep -E "DONE:|IN-PROGRESS:|BLOCKED:|ALERTS:" MASTER_STATUS.md
```
Typical dormant signature: `207 DONE / 388 IN-PROGRESS / 3 BLOCKED / 391 ALERTS` —
ALERTS ≈ IN-PROGRESS count (+ the few BLOCKED), i.e. ~all alerts are the 388 stale
IN-PROGRESS files, NOT live breakage. Age column reads tens of thousands of minutes
(26000–45000m ≈ 18–31 days) for those. Corroborate with the `find -newermt` /
`stat` mtime checks above.

**The ALERTS count must never be reported as "391 failures".** Decompose it:
- The bulk is stale IN-PROGRESS (dormant fleet) → informational, same conclusion as
  the BUILDER ledger ("fleet dormant, no action").
- Only the small BLOCKED set is real. Triangulate each BLOCKED line:
  ```bash
  grep -i "BLOCKED" MASTER_STATUS.md | grep -v "STALLED"
  ```
  Classify each: **creds-blocked** (e.g. `eni9_w3` — [STATE: BLOCKED — creds]),
  **design-RED by design** (e.g. `gate.md` — veto_usb_loader returns None while the
  DEMIURGE drive is unmounted; deploy gate intentionally RED until the real-USB data
  path exists — explicitly "correct, not a failure"), or a genuinely stalled project
  mini. Only the last class is actionable; the first two you report, don't "fix".

## Conclusion phrase pattern
- `50 files scanned → N parsed` (empty files like a blank BUILDER_5 are skipped by the
  script's crash guard; ledger rows = parsed count, may be < file count). When ledger
  rows < file count, name the hidden builder explicitly by flagging 0-byte STATUS files:
  `find builds/ -name "STATUS_BUILDER_*.md" -empty` — e.g. a present-but-empty
  `STATUS_BUILDER_20.md` vanishes entirely from the ledger, so a visibly absent ledger id
  is the norm for truncated builders, not a missing-status-file error. Report it as
  "builder silently dropped by crash guard (empty STATUS file)" so it's not mistaken for
  a lost worker.
- State roughly: `[DONE] 40 / [IN-PROGRESS] N / [BLOCKED] N — but mtimes all Jul XX →
  fleet dormant, no active tasks` → **no action required**.

### Worked example (Aug 2026 — "all but one" parking touch)
49/50 `STATUS_BUILDER_*.md` mtimes on Jul 25 (16 days stale) while the ledger claimed 8
IN-PROGRESS + 1 BLOCKED. The single fresh file (BUILDER_37, touched that day) was NOT live
work — its body re-verified IDLE ("Control FIFO /tmp/eni_ctl_BUILDER_37 does not exist,
re-verified empirically… do not invent work"). When exactly one file is fresh, ALWAYS open
it: a same-day touch on a builder whose content says IDLE/no-FIFO is a parking/heartbeat
write, not a task. Corroborate with `MASTER_STATUS.md` (every row an old date + alarms all
stale = dormant).


## Quick live-floor probe (run the script directly)
`echo 'ENI PULSE' | grep status_hub.cron.log` returns ZERO hits — fleet_pulse.py's
one-line pulse is written to **stdout**, not to the cron log. To get the authoritative
live floor state you must invoke the probe yourself:
```bash
cd /home/hunter/Commander/eni_swarm && timeout 120 python3 fleet_pulse.py --once
# -> [HH:MM:SS] ENI PULSE | windows=N | stalls: <list> | gate=RED
```
`windows=0` + `gate=RED` + all STATUS files on one old parking date = floor is down/idle,
consistent with the dormant-not-broken determination. Pair with the mtime cross-check above.

## Reporting a dormant fleet — enumerate the waiters
A dormant-pass report is more useful when it names the concrete resume levers instead of
just "fleet is idle." Read each fresh/special builder file's body and note (a) which
builders are parked AWAITING a directive and (b) what un-park them:
- **IDLE-builder**: fresh mtime, body says awaiting directive via its control FIFO — the
  lack of `/tmp/eni_ctl_<name>` is itself the parking proof (see diagnostic-one-liners).
  Resume lever: a live session creates that FIFO and dispatches.
- **BLOCKED-builder** (e.g. `[BLOCKED] ... no task assigned`): parked on no dispatch. Same
  lever — PRODUCT_LEAD must route a task.
- **fresh-spawn / "awaiting LO directive"**: started and immediately parked, no task.
So a strong dormant report reads like: "Fleet dormant — B37 IDLE (needs /tmp/eni_ctl_BUILDER_37),
B46 BLOCKED (needs PRODUCT_LEAD dispatch), B39 fresh-spawn parked. Resume requires a
live-session directive via those FIFOs." This turns a monitoring note into an actionable
handoff for the next live session.

## Ghost-update detection: separate hermes sessions write to STATUS files
A STATUS file with a fresh mtime does not necessarily mean a builder was running.
Separate hermes processes (cron jobs, `hermes chat` sessions, manual investigations)
can write to STATUS files as a side effect of probing or diagnosing the fleet.
Example pattern observed: a `hermes chat` session detected that
`/tmp/eni_ctl_BUILDER_37` did not exist, so it updated the STATUS file to
`[IDLE]` confirming the absence — producing a fresh mtime that looked like a builder
waking up, when in fact the builder had never started.

Detection: when you see a single builder with a much fresher mtime than the rest
of the fleet, read its file body. If the body contains language like
"re-verified empirically" or "ls exit=2, no /tmp/eni_ctl_* entry" or "FIFO does not
exist", it is a ghost-update from a separate hermes session, not a builder coming
online. The fleet remains dormant.

## Second+ consecutive dormant run: [SILENT]
When the fleet has been fully dormant across consecutive cron cycles:
- Compare `HEARTBEAT_LEDGER.md` contents (md5sum) against prior run — if identical, no change.
- Cross-check MASTER_STATUS.md summary counts (DONE / IN-PROGRESS / BLOCKED) against
  HEARTBEAT_LEDGER.md builder counts to confirm zero drift.
- If builder states and mtimes are unchanged and no new ALERTS file exists →
  respond exactly `[SILENT]` to suppress delivery.
- Do NOT re-describe the fleet state or reiterate the staleness analysis on every cycle.
  The first report of dormancy is the deliverable; silence thereafter is correct.

## Fresh single-builder mtime ≠ live fleet (cross-check before declaring activity)
A recently-touched STATUS file does NOT mean the floor is alive. The watchdog cron bumps
`STATUS_BUILDER_NN.md` for idle builders (e.g. BUILDER_37 re-verified its empty FIFO on a
fresh date, `blocker=none`, `next=await LO directive`) — so a fresh mtime on ONE builder can
sit inside an otherwise-frozen fleet. When distinguishing "actively building" from
"idle-but-watchdogged", cross-check with OS truth, never mtime alone:
```
ps aux | grep -iE "builder|swarm" | grep -v grep      # live worker procs
ls -la /tmp/eni_ctl_BUILDER_*                          # mounted control FIFOs
find eni_swarm -name "*.md" -newermt "<last-week>"     # recently-touched files
```
If the fresh file is a `# STATUS — IDLE —` watchdog line and no builder/swarm process is
running under it, that builder is parked, not active. Capture this explicitly (BUILDER_37:
fresh but idle, no FIFO) so a one-hot fresh file isn't misread as a live floor.

## Worked example — confirmed dormant floor (2026-08-15)
Clean run of `monitor_fleet.py` → exit 0, ledger regenerated, ZERO delta vs prior (all
50 builders still 40 DONE / 9 IN-PROGRESS / 1 BLOCKED). That no-change is itself the
dormancy signal:
- Every `builds/STATUS_BUILDER_*.md` except B37 had mtime **Sat Jul 25 (~16:14–16:17)** —
  3+ weeks old despite carrying IN-PROGRESS/BLOCKED markers → stale snapshots, not live workers.
- Only B37 fresh (Aug 14) but content = `# STATUS — IDLE —` watchdog, `blocker=none`, awaiting
  `/tmp/eni_ctl_BUILDER_37` FIFO → fresh-but-parked (never misread as a live floor).
- `.alive_ENI8SMOKE` marker mtime **Jul 9** (no live-beat in a month).
- `HEARTBEAT_ALERTS.md` absent → `blocked_builders` set empty → B46's BLOCKED comes from its
  own STATUS file ("no task assigned, awaiting dispatch"), not the alert path.
Takeaway: quote the batch-mtime + single-fresh-idle signature verbatim in the report so
LO sees concrete evidence, then recommend re-drive-via-directive (not auto-dispatch).

## Don't
- Do NOT dispatch tasks, edit STATUS files, or spin up builders from this cron — it is
  report-only (see fleet-monitor-ledger.md). Report dormancy (naming the waiters + levers)
  and note that resurrecting requires a live-session directive.