# Fleet MONITOR + HEARTBEAT: what reads where (pitfall found 2026-08-07)

When answering "what is the ENI swarm status?" or running the fleet monitors,
DO NOT trust a single path — the swarm has MULTIPLE fleet generations and the
most-referenced monitor script points at the STALE one.

## The two monitor scripts and their inputs

1. `/home/hunter/Commander/eni_swarm/monitor_fleet.py` (cron-driven)
   - Workdir resolution: picks first of `[<script_dir>/builds, cwd]` that has
     `STATUS_BUILDER_*.md` files → almost always `.../eni_swarm/builds/`.
   - reads `STATUS_BUILDER_*.md` (50 files), writes `HEARTBEAT_LEDGER.md`
     (state buckets `[DONE] [IN-PROGRESS] [BLOCKED]`).
   - Reads `HEARTBEAT_ALERTS.md` for `- BUILDER_(\d+)` lines to force BLOCKED.
   - ⚠️ In practice the `builds/` dir is a **frozen legacy sweep** (mtimes weeks
     old, e.g. Jul 25) → the ledger it writes is stale and MISLEADING. It reports
     a "dead floor" even when other fleet generations are live and healthy.

2. `/home/hunter/Commander/eni_swarm/status_hub.py` + `MASTER_STATUS.md`
   - Consolidated hub: scans `eni_swarm/STATUS_ENI*.md` + every live-project
     STATUS_* recursively. Regenerates MASTER_STATUS.md.
   - Hub line format: `| name | path | STATE | last-update | age-m | ALERT(YES) |`
   - "m" = minutes of age; ALERT rule = STATE==BLOCKED OR (STATE!=DONE AND age>10m).
   - Beware: a large fraction of these rows are stale (age in the thousands of
     minutes / weeks) and the derived "ALERTS" count is mostly false-positive
     history. Cross-check mtimes, not just the YES column.

## The LIVE fleets (as of 2026-08) — where the actual work happens

- DEMIURGE / DEMIURGE3D mini-fleet lives in **`~/.hermes/scripts/`**:
  `STATUS_DEMIURGE_B01..B12.md` + `STATUS_DEMIURGE3D_B01..B12.md` = 24 builders.
  These are the ones actually `State: RUNNING` (fresh PTY bridge / FIFO / REPL).
  Files carry `**State**: RUNNING`, `**Updated**: ISO`, plus a PASS/FAIL board.
- ENI Knowledge Base daemon: `~/.eni/kb/STATUS_ENI_KB.md` (Daemon RUNNING,
  services: compression-pipeline, skill-forge-swarm, mcp-server, lsp-server).
- Dashboard `:8420` (v4.1 optimized fleet) may be DOWN while the mini-fleet is
  fine — distinguish "dashboard down" from "fleet down".

## Quick triage sequence for a fleet-status question

1. Check the FRESHEST real builders first: `ls -t ~/.hermes/scripts/STATUS_*.md`
   → grep `State: RUNNING` / count them. This is the live fleet.
2. `pgrep -fac 'eni_agent_term[.]py'` → legacy visible floor (expect varies).
3. Health endpoints: controller `:8940/health` (=ok), turbocharger `:8922`,
   dashboard `:8420`.
4. Only then read `HEARTBEAT_LEDGER.md` / `MASTER_STATUS.md`, and only after
   checking the mtimes of the STATUS files they consumed — if those are old, the
   ledger is stale by definition.

Lesson encoded: **always sanity-check the mtime of the STATUS files backing any
monitor output before reporting a fleet as DONE/BLOCKED/dead. The monitor's
workdir resolution can silently latch onto a frozen legacy dir.**

## Liveness probes that actually work (verified 2026-08-07)

A status file saying `RUNNING` is a claim, not evidence. When triaging, decide
live-vs-stale with these three cheap checks instead of trusting the banner:

1. **`ss -ltnp` per port** — a service that returns `000` on `/health` may be
   *not listening at all* (process dead) vs *listening but unresponsive*. Pull
   the listening-port list; if the port isn't there and `ps` shows no pid, the
   service is fully DOWN, not degraded. (Dashboard `:8420` was absent from both
   `ss` and `ps` while controller `:8940`/turbo `:8922` were listening → confirmed
   down, distinct from the healthy core.)

2. **Batch-writer-halted fingerprint: identical mtimes across all minis.** The
   24 DEMIURGE/DEMIURGE3D status files all carried the *same* mtime (06:16) yet
   said `RUNNING`. A single shared timestamp across the whole set means one batch
   status-writer loop wrote them all at once and then stopped — the fleet is
   frozen, not live. Check: does `ls -lt` show all files stamped identically?
   That's the tell. Then confirm with `ps` for the driver/bridge processes — none
   present = fleet halted despite the `RUNNING` banners.

3. **KB daemon mtime self-heals — use it as a freshness beacon.** The more
   reliable family is `~/.hermes/scripts/STATUS_DEMIURGE*.md` (minis) vs
   `~/.eni/kb/STATUS_ENI_KB.md` (KB daemon). The KB daemon's status file is
   rewritten on every restart, so a *fresh* mtime there (seconds old) proves the
   daemon+manager are alive even when the minis are stale. Grep the banner with
   the literal markdown form `\*\*State\*\*: RUNNING` — a bare grep for
   `State: RUNNING` misses it (the files use bold `**State**:`).

## Fleet triage signature: the stale "RUNNING" banner tell (found 2026-08-07 cron)

A status file that says `State: RUNNING` is NOT proof of liveness. When triaging, compare MTIMES across the fleet, not just the banner text:

- If ALL builders in a family carry the IDENTICAL mtime (e.g. every one of the 24 DEMIURGE/DEMIURGE3D files at 737 min), they were batch-written once and the heartbeats STOPPED afterward. The RUNNING banners are frozen, not live — "reported RUNNING but silent."
- A genuinely live fleet has varied and/or fresh (seconds-to-minutes old) mtimes.
- Reconcile against the two RELIABLE beacons: the KB daemon status (`~/.eni/kb/STATUS_ENI_KB.md`, rewritten on every restart → fresh mtime proves daemon+manager alive) and the controller `:8940/health`.
- monitor_fleet.py cron flow: expect exit 0 and a regenerated HEARTBEAT_LEDGER.md (40-50 rows bracketed `[DONE]`/`[IN-PROGRESS]`/`[BLOCKED]`). Its state values are stale-sweep artifacts, so report the mini-fleet + KB/controller liveness ALONGSIDE the ledger, or the report is misleading.

## Live reconciliation recipe (proven 2026-08-09)

When producing a fleet report, gather these BEFORE writing anything — the order
matters, and each is an independent probe that can disagree with the others:

1. **Status hub = the single most-current aggregate.** Watch `status_hub.cron.log`
   (live, append-only) and `MASTER_STATUS.md` in `~/Commander/eni_swarm/`. The hub
   regenerates `MASTER_STATUS.md` roughly every minute via worker w2 and is the
   canonical latest view (e.g. "598 minis: 207 done / 388 in-progress / 3 blocked,
   391 alerts"). If it just regenerated (<5 min mtime), the infra moving it is alive
   regardless of what the per-builder STATUS files say. Its ALERT rule: STATE==BLOCKED
   OR (STATE != DONE AND age>10min) — so a fleet with hundreds of stale IN-PROGRESS
   rows is "parked/stalled", not necessarily crashed.
2. **Controller** `curl -s localhost:8940/health` — expect `"healthy": true` with the
   6 checks ({airllm:8913, free_router:8920, secrets, enterprise, hermes_runner, queue}).
3. **KB daemon** `~/.eni/kb/STATUS_ENI_KB.md` — fresh mtime = alive. BUT read the
   `uptime`/`restarts` fields: fresh file with `uptime ~25s` + `restarts=1` on all
   services = the daemon just restarted (restart churn). Flag it as a signal, don't
   report it as plain healthy.
4. **Dashboard `:8420`** — independent probe. `curl -s -o /dev/null -w '%{http_code}'
   localhost:8420/` → `000` means DOWN. Observed down while controller+KB were healthy,
   so there's no single "all alive" shortcut. Launcher: `eni_master_dash.sh`.

### Freshness check (stale sweep you can trust)
```bash
cd ~/Commander/eni_swarm/builds
for f in STATUS_BUILDER_*.md; do
  n=$(basename "$f" .md | sed 's/STATUS_BUILDER_//')
  age=$(( $(date +%s) - $(stat -c %Y "$f") ))
  st=$(head -1 "$f" | tr -d '\n')
  printf "%s age=%s %s\n" "$n" "$age" "$st"
done | awk '{print $2, $0}' | sort -n | head   # NOTE: sort -t= FAILS on empty sep; use awk-sort
```
The mtime array is the ground truth: a genuinely live floor has varied and/or
seconds-to-minutes-old mtimes; a parked floor shows ~14-day-old files with maybe one
lone freshly-touched builder (BUILDER_37 was the only live one in the 2026-08-09 run).
Empty `STATUS_BUILDER_*.md` files (0 bytes) are crash-guard-skipped by monitor_fleet.py
→ the row is absent from HEARTBEAT_LEDGER.md; don't read that as a missing builder.

## Expected steady state of the cron monitor (parked floor) — don't raise a false alarm
The recurring `monitor_fleet.py` cron on a PARKED floor reliably produces a fixed,
benign-looking output that a fresh agent can misread as "work is happening" or "something
broke". All of these are EXPECTED on a parked floor and require NO action:
- Ledger shows ~42 `[DONE]` — this is a PARSE ARTIFACT: the script maps every
  non-BLOCKED / non-IN-PROGRESS builder to DONE, so parked/idle files read as DONE.
  It does NOT mean 42 builders completed work this cycle.
- ~8 stale `[IN-PROGRESS]` (all ~14 days old) and 1 `[BLOCKED]` (typically BUILDER_46,
  "no task assigned, awaiting PRODUCT_LEAD dispatch") — all stale, none progressing.
- `MASTER_STATUS.md` reports huge counts (e.g. 388 IN-PROGRESS / 391 ALERTS) — those are
  the STALE legacy generation (STATUS_ENI*/STATUS_DEMIURGE* from Jul 9-13), not the live
  builder floor. Ignore them when judging builder-floor health.
- BUILDER_37 stays freshly touched on each cron run and re-verifies IDLE (its control
  FIFO does not exist, no directive issued). It correctly refuses to invent work — this
  repeated re-verification is a HEALTHY parked-state signal, not a stuck builder.
- `HEARTBEAT_ALERTS.md` may not exist → no builders force-blocked this run.

Verdict recipe for the cron report: `ps` shows no builder worker processes + builder
mtimes are ~14 days old + only one lone freshly-touched IDLE builder = floor is PARKED /
healthy-but-idle, NOT crashed. Report that, note BUILDER_37's fresh re-verification, and
conclude "no action needed — resume requires LO directives via control FIFOs."

## Pitfall: don't read the ledger's frozen counts as a live alarm

A freshly-triggered `monitor_fleet.py` run on a PARKED floor will still output a ledger
containing 8 `[IN-PROGRESS]` + 1 `[BLOCKED]` (e.g. B5/B17/B25/B32/B38/B39/B42/B44 IN-PROGRESS,
B46 BLOCKED). These are FROZEN HISTORICAL MARKERS from the last active campaign (Jul 25-26) —
the parser classifies each status file's stale `[STATE: IN-PROGRESS]`/`[BLOCKED]` header text,
not live process state. An agent reading only the ledger could misreport "8 builders stuck" when
the floor is healthy-and-parked. Always cross-check the ledger against: (1) `ps` for worker
processes (expected: zero), (2) status-file mtimes (~2 weeks old is parked), (3) dashboard/live
FIFOs. Treat the ledger's IN-PROGRESS/BLOCKED rows as signal ONLY if the underlying status file
was modified recently (same day) — otherwise they are historical noise to exclude from the report.

### ⚠️ Zero-padded filenames = false "missing builder" alarm (found 2026-08-11)
Builder status files are zero-padded: `STATUS_BUILDER_01.md` … `STATUS_BUILDER_09.md`, NOT
`STATUS_BUILDER_1.md` …. `monitor_fleet.py`'s regex `STATUS_BUILDER_(\d+)\.md` matches the padded
name and extracts the builder number, so the ledger can list e.g. `BUILDER_5` even though no
`STATUS_BUILDER_5.md` exists. If you hand-verify with `ls STATUS_BUILDER_5.md` you'll get
"No such file" and may wrongly conclude a builder's status file is missing/corrupted.
Always glob with a wildcard (`ls STATUS_BUILDER_*.md` or `ls STATUS_BUILDER_0?.md`) and
recall the padded name before flagging anything. Verified this exact case: `STATUS_BUILDER_05.md`
(mtime Jul 25) is what produced ledger row `BUILDER_5 [IN-PROGRESS]` — historical noise, as usual.

