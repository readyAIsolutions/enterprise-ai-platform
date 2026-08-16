# Fleet-status interpretation runbook (after running monitor_fleet.py)

`monitor_fleet.py` regenerates `HEARTBEAT_LEDGER.md` from `builds/STATUS_BUILDER_*.md`.
It exits 0 even when the fleet is idle — **exit 0 only means the aggregation ran, NOT
that anything is alive.** Always interpret the ledger by cross-checking disk state
against liveness before reporting "X builders are working".

### IN-PROGRESS ≠ actually building — decode the BODY, don't trust the token
A ledger line reporting `[IN-PROGRESS]` can be a **self-assigned stall**, not live
work. Several builders write an IN-PROGRESS token while their STATUS body admits there
is no real job: `"no project assigned yet ... awaiting task assignment"`, `"Assigning
self: resurrect PRODUCT_LEAD routing..."`, `"scanning swarm for highest-value stalled
work"`, `"awaiting LO directive"`. When the narrative says `assigning self` /
`no task assigned` / `awaiting task` / `stalled` / `stale`, the builder is **parked /
idle-unrouted** and merely *claims* busy. This happens when no coordinator
(PRODUCT_LEAD) is routing real jobs. So:
- Decode the body before counting IN-PROGRESS as working builders.
- Watch for the tell-tale **PRODUCT_LEAD stalled** message (e.g. "207 DONE / 388
  IN-PROGRESS stale from Jul 9-13") — that's the real root cause: a stuck coordinator,
  not busy builders.
- Confirm the token against the file mtime: a Jul-era (stale) IN-PROGRESS is a phantom
  relic; a fresh IN-PROGRESS whose body reads "awaiting directive" is a parked worker
  that merely re-checked in.
- Headline to report when this is true: **fleet is idle-unrouted; bottleneck is
  dispatch (stuck PRODUCT_LEAD), not capacity.** Raw DONE/IN-PROGRESS/BLOCKED counts
  overstate health in this state.

### PITFALL — cron / wrong-cwd runs: probe vs monitor disagree
`monitor_fleet.py` resolves its OWN directory (the script dir with `builds/`), so it
works from anywhere — including a cron job whose cwd is arbitrary (e.g. a Python
site-packages dir). But `fleet_liveness_probe.sh` uses cwd unless `$1` is given, so the
SAME cron invocation prints a scary `WARNING: 0 status files found` unless you pass `$1`.

### PITFALL — `$1` is the swarm BASE dir, NOT the `builds/` subdir
`fleet_liveness_probe.sh` appends `/builds` to its `$1` itself. Passing the `builds/`
dir literally (e.g. `/home/hunter/Commander/eni_swarm/builds`) yields the probe looking
at `.../builds/builds` → `WARNING: 0 status files found … dead fleet` — a FALSE alarm
caused by a bad path, not a dead swarm. **Always pass the swarm base dir** (the dir that
CONTAINS `builds/`), e.g. `bash …/fleet_liveness_probe.sh /home/hunter/Commander/eni_swarm`.
Cross-check: the probe header explicitly says `DISK_STATUS_FILES=0` here usually means a
bad path, not a dead fleet. (Verified route, this run: passing the base dir yields
`DISK_STATUS_FILES=50`.) The SAME cron invocation prints a scary `WARNING: 0 status files found under './builds'` /
`DISK_STATUS_FILES=0` because it fell back to the wrong path — not because the fleet is
dead. The probe's own message says "A zero here is usually a bad path, NOT a dead fleet",
but in a cron context trust it and re-run with the argument. **Always invoke:
`bash fleet_liveness_probe.sh /home/hunter/Commander/eni_swarm`** — never rely on cwd,
and treat a lone `0 status files` from an un-argued probe as an invocation bug until you
re-run it with the swarm dir.

### PITFALL — ledger `[DONE]` ≠ "task completed"; it means "not BLOCKED, not IN-PROGRESS"
`monitor_fleet.py` maps each builder's parsed state with this exact logic
(around lines 51-57 of the script):
- state == `BLOCKED`            → `[BLOCKED]`
- state in (`IN-PROGRESS`,`IN_PROGRESS`) → `[IN-PROGRESS]`
- everything else (incl. `IDLE`, `READY`, `UNKNOWN`, `ACTIVE`) → `[DONE]`

So a ledger that is mostly `[DONE]` describes an **idle/parked fleet, NOT a completed
one.** Builders whose STATUS self-labels `IDLE` or `READY` will show as `[DONE]`. When
reporting, do NOT read "everyone is DONE = all work finished" — read it as "fleet is on
standby." To get real state, cat the individual `builds/STATUS_BUILDER_<N>.md` first
line rather than trusting the umbrella `[DONE]`. Note: `IDLE` is a first-line `[TOKEN]`,
so the fallback parser picks it up only for files whose first non-blank line actually
starts with `[`; header-style files (`# STATUS_BUILDER_N — [IDLE]`, `[state: IDLE]`,
`# STATUS BUILDER N`) fall through to `UNKNOWN` → still `[DONE]`.

### PITFALL — clustered stale mtimes = swarm halted (the #1 read of a ledger)
When nearly ALL `builds/STATUS_BUILDER_*.md` mtimes cluster at the SAME age
(e.g. all ~341h / ~14 days old) and only one or two files are fresh, the
builder fleet has STOPPED — the ledger's IN-PROGRESS / BLOCKED lines are
**artifacts of parsing frozen files, not live activity.** The monitor has no
staleness threshold: it happily reports `[IN-PROGRESS] BUILDER_5 ...` from a
file untouched for two weeks. Before reporting any builder as working, run:
```bash
find /home/hunter/Commander/eni_swarm -name "STATUS_*.md" -mmin -1440   # fresh <24h
ls -la /home/hunter/Commander/eni_swarm/builds/STATUS_BUILDER_*.md | awk '{print $6,$7,$8,$NF}' | sort
```
If only 1 of ~50 is inside 24h, the swarm is effectively down; state the
harbinger: "IN-PROGRESS/BLOCKED in today's ledger come from files frozen
~14d ago." That is the actionable finding.

### PITFALL — infra services UP ≠ builder workers UP
When diagnosing "is the fleet alive?", do NOT treat the routing/support stack
as evidence the builders are running. Each of these being up means nothing about
the ~50 builder workers:
- hermes gateway, `free_router.py`, `swarm_turbocharger.py`,
  `eni_controller.controller serve` — these are the transport/controller tier
  and can all be up while the builder fleet is fully stopped.
- Control FIFOs existing under `/tmp/eni_ctl_*` also just indicate a prior
  session — check their mtime; stale FIFOs ≠ live workers.
Aliveness of the fleet = STATUS file mtimes fresh + dedicated builder/status_hub
worker processes present (`pgrep -af "[s]tatus_hub.py"` with the bracket so you
don't self-match). Missing `status_hub.py` worker + frozen mtimes + idle-only
fresh status file (e.g. `[IDLE] ... awaiting LOs directive`) is the definitive
"swarm stopped, needs human dispatch" verdict.

### PITFALL — false "active" from the probe's own shell
When scanning for live builder worker processes with `pgrep -af "STATUS_BUILDER|directive|builder"` or `ps aux | grep -iE "worker|directive"`, **your own probe's spawned `bash -c ...` wrapper will match the pattern and appear as a "live builder process."** The wrapper shows up as a `bash -c source /tmp/hermes-snap-*.sh ... eval '<your grep pipeline>'` line whose args echo your own search grep. It has a fresh PID and a timestamp (start time = when you ran the command), so on a quick scan it reads as a heartbeat. This is a false positive — filter it out with `grep -v "bash -c"` (or `grep -v hermes-snap`) before concluding anything is alive. Rule: a "live builder" must be a **real worker process (hermes-chat / directive consumer / per-project builder)** — not your own transient shell, not kernel `kworker/*` threads. Cross-check against control FIFOs in /tmp and STATUS mtimes as the authoritative signal.

## Step 1 — count status files vs ledger lines (expect a drop)
```
ls builds/STATUS_BUILDER_*.md | wc -l          # on-disk builders (e.g. 50)
wc -l HEARTBEAT_LEDGER.md                       # ledger rows will be fewer or equal
```
A ledger row count **lower** than the file count is normal and correct: the script's
crash-guard drops any status file that is **empty** (zero content or all-blank lines).
These are builder files that were touched/created but never got a state token. Identify
them explicitly rather than assuming missing builders:
`grep -L . builds/STATUS_BUILDER_*.md` (empty files) → compare against ledger numbers.

## Step 2 — see the raw state token, not just the mapped state
The script maps any non-`IN-PROGRESS`/`BLOCKED` token to `DONE`. Files whose first
non-blank line has **no `[...]` token** (e.g. plain text, `# ...` header) are silently
mapped to `DONE` — they are NOT evidence of completed verified work. Inspect raw tokens
before trusting DONE counts.

## Step 3 — staleness check decides "IN-PROGRESS/BLOCKED = real or artifact"
Non-DONE statuses are almost always **stale artifacts** in this fleet. Check file mtimes:
```
stat -c '%y %n' builds/STATUS_BUILDER_*.md          # compare non-DONE file ages to now
```
If the IN-PROGRESS/BLOCKED files are days old (this fleet froze ~Jul 25 → all 12+ days
stale), they are leftovers from an old run, not active work. Only a status file mtime
within the current session/day indicates a genuinely live builder.

## Step 4 — confirm liveness with processes & FIFOs (the real truth)
```
ps aux | grep -E "hermes|eni_" | grep -v grep    # live worker procs
ls /tmp/eni_ctl_BUILDER_* 2>/dev/null            # control FIFOs present?
# PITFALL: never do the FIFO glob check via `ls` with a shell that has nullglob OFF
# and a wildcard that matches nothing — bash leaves the pattern unexpanded, ls then
# falls back to dumping the ENTIRE containing dir (/tmp) as noise. Prefer a glob that
# stays empty on no-match, e.g.:
compgen -G '/tmp/eni_ctl_BUILDER_*' | head || echo "no control FIFOs"   # empty on no match
# or: find /tmp -maxdepth 1 -name 'eni_ctl_BUILDER_*' 2>/dev/null | head
```
Filter out the always-running infra daemons (router/proxy, controller, KB daemon,
swarm_turbocharger, status_hub, pyright LSP) — these are NOT builders. A live builder is
a `hermes chat`/`eni_` worker with its own `/tmp/eni_ctl_BUILDER_N` FIFO. **A FIFO can
exist without a live worker** (leftover pipe after the worker exited) — a pipe alone is
not liveness.

**FALSE-FRESHNESS TRAP (FIFO mtime):** do NOT treat a same-day FIFO mtime as evidence of a
live builder. Leftover control pipes linger in `/tmp` and keep their creation mtime — a
FIFO created this morning (e.g. `eni_ctl_DEMIURGE3D_B01` at 06:16, `eni_ctl_BUILDER_50` at
12:09) is still dead if no worker holds it open and its STATUS file is days/weeks old.
Observed fleet pattern: 25+ `/tmp/eni_ctl_*` pipes with today's mtime, ALL with stale
STATUS files (Jul 10 / Jul 25) and zero matching worker procs → every one was a dead
relic. Correct liveness test = **FIFO present AND matching STATUS file mtime fresh/today
AND a live worker proc** — all three, not just the pipe. Cross-check each candidate
individually; a single fresh FIFO among a wall of stale ones (e.g. `/tmp/eni_ctl_BUILDER_50`
looked fresh) is still dead if its STATUS file is stale.

## Step 4.5 — infra is alive ≠ fleet is alive (health endpoints)
Before concluding "fleet down", check that the infrastructure is actually up — the
controller and the proxy/turbocharger expose health endpoints that return clean JSON
even when every builder is idle or stale. This distinguishes three distinct states:
infra-down, infra-up-but-routing-stalled, and genuinely-working-fleet.
```
curl -s http://localhost:8940/health     # ENI controller          -> {"status":"ok"}
curl -s http://localhost:8922/health     # swarm_turbocharger      -> {"status":"ok", "concurrency":N}
```
If these return `ok` while all STATUS mtimes are days old and no builder procs/FIFOs are
live, the correct reporting is "**infrastructure healthy; fleet parked / no active
routing**" — NOT "fleet crashed". Routing staleness (PRODUCT_LEAD not dispatching, no
control FIFOs like `/tmp/eni_ctl_BUILDER_N`) is the usual upstream cause, so report it
as the actionable item rather than implying a crash.

## Step 4.5 — concrete liveness probes (verify infra is actually up)
Before calling the fleet "alive", run these three cheap probes and read them together:
```bash
ps aux | grep -iE "eni|builder|swarm" | grep -v grep
#   expect: eni_controller.controller serve (:8940), swarm_turbocharger.py (:8922),
#           airllm_server.py (:8913, the merged eni-controller model), eni_kb_daemon
ls -la /tmp/eni_ctl_* 2>/dev/null
#   named control FIFOs present (e.g. BUILDER_50, DEMIURGE3D_B01..B09) == control plane live
find ./builds -name "STATUS_BUILDER_*.md" -mmin -30 2>/dev/null
#   isolate the GENUINELY fresh builders — the only ones to report as current state;
#   everything else (older mtime) is a DONE terminal or stale artifact
```
`ps`/FIFO present but every STATUS file days-old ⇒ infra up, fleet idle/awaiting directives —
say that explicitly rather than "working on nothing". MASTER_STATUS.md (regenerated by
status_hub.py) is a quick cross-check of the whole ENI/workspace set, but its IN-PROGRESS
rows are often weeks-old stale artifacts too — trust fresh mtime over the state token.

## Step 5 — check HEARTBEAT_ALERTS.md
If the file is absent, NO builder is being force-blocked from the alert source; any
`[BLOCKED]` in the ledger then comes from the builder's own (possibly stale) status
token, or is inherited from the old status — say so rather than implying a new failure.

## Reporting rule of thumb
- 40+ DONE + idle → "fleet quiescent/settled", no action.
- Non-DONE states are stale (days old) + no live procs → flag as artifacts, not failures.
- Only report the genuinely fresh (today-mtime) builder(s) as the real current state.

## Liveness cross-check one-liners (use when ledger is a mix of stale flags)
When most builders carry multi-day-old IN-PROGRESS/DONE tokens, pin down what is
ACTUALLY running before describing fleet health:
```bash
# Which builders have a genuinely fresh status file (today or recent)?
find builds -name "STATUS_BUILDER_*.md" -newermt "2026-08-01" -printf "%f %TY-%Tm-%Td %TH:%TM\n" | sort
# Are any builder minis actually executing?
ps aux | grep -iE "hermes|master_driver|eni" | grep -v grep
# Control FIFOs staged but no matching worker = dispatched-but-not-dispatched state
ls -la /tmp/eni_ctl_* 2>/dev/null
```
Reading the three together:
- Fresh status + no proc + missing FIFO → builder is IDLE "parked" (re-verified its
  FIFO missing), waiting for LO to issue a directive. Report as healthy-but-parked,
  the actionable thread (create the FIFO / dispatch) — NOT a crash.
- Fresh FIFO present but no matching worker proc → routed/staged but not running;
  candidate for a dispatch kick.
- All statuses stale (days old) + no procs + FIFOs idle → fleet dormant, no active work.
- **Ghost ledger entry:** a builder may appear `IN-PROGRESS` / `BLOCKED` in the ledger yet
  no STATUS file on disk** (the crash-guard drops empty files, or the file was
  deleted). When cross-checking, confirm the file actually exists before reporting it as
  active. Treat a missing-file "active" entry as a zombie/ghost: flag it for
  reconciliation, do NOT report it as working.

## ⚠️ PITFALL — status files are ZERO-PADDED (verified 2026-08)
On-disk filenames use zero-padded numbers: `STATUS_BUILDER_01.md` … `STATUS_BUILDER_50.md`
(e.g. `STATUS_BUILDER_05.md`, NOT `STATUS_BUILDER_5.md`). Consequences:
- `monitor_fleet.py`'s regex `STATUS_BUILDER_(\d+)` handles this fine — it captures "05"
  and int()s it to 5, so ledger row `BUILDER_5` maps to disk file `STATUS_BUILDER_05.md`.
- **Manual cross-checks must use the padded name (or grep the actual `ls` listing).** If you
  loop with the unpadded name `STATUS_BUILDER_5.md` you get a FALSE "ghost/file-not-found"
  even though the builder is happily on disk. Grep the `ls builds/STATUS_BUILDER_*.md`
  listing for the padded name instead of stat-ing an unpadded path.
- The OLD "BUILDER_5 was IN-PROGRESS but STATUS_BUILDER_5.md was absent (only ..._50.md
  matched)" ghost anecdote is **OUTDATED** — that was a pre-padding naming quirk. Do not
  reproduce it as a live finding; re-verify against the padded listing first.
- Subfleets (DEMIURGE3D, STOCKBOT) can have today-staged FIFOs with no live workers —
  that's "staged but not dispatched," distinguish it from an active build in flight.
- **Supporting infra is NOT evidence of builders working.** These daemons run 24/7
  independent of fleet activity and will appear in any `ps grep`:
  `hermes`/`hermes gateway`, `free_router.py`, `swarm_turbocharger.py`,
  `eni_controller.controller serve`, `airllm_server.py`, `eni_kb_daemon`. When you
  `ps aux | grep -i eni|hermes` to judge liveness, ignore these ever-present procs —
  only a **per-builder worker** (a process tied to a STATUS_BUILDER_* task, e.g. a
  Demiurge AppImage build loop) counts as "a builder working". A box showing only
  infra + stale STATUS files is a **quiescent/idle fleet**, which is the expected
  healthy state when there's nothing to build. See Aug 2026 run: 40 DONE / 8 stale
  IN-PROGRESS / 1 BLOCKED with zero builder workers up — idle, not broken.

## Pitfall — a FRESH status file ≠ an actively-building builder
`fresh_today` / newest-mtime can be a **false "alive" reading**. A builder on an
IDLE watchdog (e.g. `# STATUS_BUILDER_N — IDLE — <timestamp>`, waiting for its
`/tmp/eni_ctl_BUILDER_N` control FIFO to be created) touches its own status file
on a schedule, so it shows up as the newest/freshest file while doing **no real
work**. Observed Aug 2026: `fresh_today=1` and the freshest file was BUILDER_37
reporting `IDLE ... no directive issued ... await LO's directive via FIFO` — parked,
not building. Before claiming "a builder is active" from freshness, read the file
body: a heartbeat-only IDLE/dormant marker (plus no per-builder worker process) is
the parked healthy state, not evidence of progress. Freshness + a real worker
process together = active; freshness alone only tells you the watchdog is alive.

## Pitfall — STALE `[IN-PROGRESS]`/`[BLOCKED]` markers inflate the ledger
`monitor_fleet.py` regex-matches the state token literally (any `[IN-PROGRESS]`,
`# STATE: IN-PROGRESS`, `[BLOCKED]` line anywhere in the file) and carries it into
the ledger **regardless of how old the file is**. So a burst of builders that went
IN-PROGRESS weeks ago and then went quiet leaves `[IN-PROGRESS]` text in their
STATUS files that the monitor re-flags every run — the ledger's IN-PROGRESS /
BLOCKED counts look alive when they're actually stale leftovers.

Observed Aug 2026: 8 builders listed `[IN-PROGRESS]` + 1 `[BLOCKED]` in the ledger,
but ALL 9 had status-file mtimes ~2 weeks old (Jul 25–26); the only genuinely
touched-today file (B37) reported IDLE. The true fleet posture was idle/dormant,
not 8 builders mid-task.

**Resolution:** any time a ledger line says IN-PROGRESS or BLOCKED, verify the
builder's OWN status file mtime is recent (same day / recent hours) before calling
it active. Stale mtime on a flagged builder = leftover marker from a prior cycle,
map it to IDLE/DONE in your report. Optionally clear the stale markers so the
monitor reflects truth next run. A clean ledger for an idle fleet is mostly `[DONE]`
(monitor maps IDLE→DONE) with a handful of fresh-IDLE heartbeat files — that is the
healthy quiescent state, NOT a sign of broken builders.

### PITFALL — "worker"/"kworker" pattern noise in liveness checks
Do NOT use `pgrep -af "STATUS_BUILDER|directive|worker"` or `ps aux | grep -i worker`
to count live builders. `worker` matches **kernel kworker threads**
(`[kworker/R-rcu_gp]`, `mm_percpu_wq`, `slub_flushwq`, `netns`, etc.) which are
ALWAYS present and flood the output with dozens of false hits. Same trap hits
`rcu*_kthread_worker` lines. Correct patterns:
- Use builder-specific tokens that never collide with kernel threads: `eni_ctl_`,
  `STATUS_BUILDER_`, `status_hub`, the model-server name (`airllm_server.py`).
- If you must match broadly, pipe through `grep -v kworker` **and** `grep -v '\[kworker'`
  (they show as `PID [kworker/..]`), and drop `*_kthread_worker`.
- For inventory, `ps aux | grep` beats `pgrep -af` because it shows full cmdline to
  eyeball which matches are real.

### PITFALL — status_hub MASTER_STATUS aggregate counters are NOT liveness
`status_hub.py` (cron every 5 min) consolidates the WHOLE tree (598 minis) and its
Summary line (e.g. "207 done / 388 in-progress / 3 blocked, 391 ALERTS") looks
alarming. In a quiescent fleet nearly all of those IN-PROGRESS + ALERT rows are the
same stale-marker artifact (STATE != DONE AND age > 10 min) across STATUS_ENI*/
and mirror pairs — NOT live builds. When someone asks "fleet status", read it as:
the hub's aggregate is a tree-wide noise floor; real activity lives in fresh mtimes
on build-floor STATUS_BUILDER_* files. Don't report 391 alerts as a fire.

### PITFALL — builder status files are ZERO-PADDED to 2 digits
`builds/STATUS_BUILDER_*.md` are named with two-digit zero-padding — e.g.
`STATUS_BUILDER_04.md`, `STATUS_BUILDER_05.md`, NOT `STATUS_BUILDER_4.md`.
A naive `open(".../STATUS_BUILDER_4.md")` will return "FILE MISSING" for a file
that exists (builders 4 and 5 in this fleet). Always glob `STATUS_BUILDER_*.md`
and parse the number from the filename rather than constructing the path from a
bare int. Same lesson applies to any per-builder artifact on the floor.

### ZOMBIE vs LIVE — only mtime recency separates them
A STATUS file declaring `[IN-PROGRESS]` / `# STATE: ACTIVE` / `BUILDING` does NOT
mean work is happening. If its mtime is OLD (e.g. ~19,900 min ≈ 14 days), it is a
frozen/zombie marker from a quiesced session — same as the tree-wide IN-PROGRESS
noise. Real, live work has a FRESH mtime (minutes). When the whole floor is quiet,
a single builder with a fresh (seconds/minutes) mtime may be the ONLY live member,
and one fresh file may be `[IDLE]`, not `[IN-PROGRESS]`.

### IDLE-with-reason is CORRECT behavior — don't flag it as a stall
A live builder that reports `[IDLE]` because it verified its control FIFO does not
exist and recognized its cron dispatch was only "a scheduling template, not a
directive" is behaving CORRECTLY (refusing to invent work), not stalled. Before
reporting "builder X is stuck", check what reason it recorded: an IDLE builder
with `blocker=none` + a verified-absent FIFO is healthy and waiting for LO. Only a
builder that is IN-PROGRESS/ACTIVE with a fresh mtime yet no forward progress is a
genuine stall worth surfacing.

### PITFALL — fresh keep-alive ≠ building floor
A **healthy keep-alive cron** (`*/5 * * * * ... status_hub.py`, plus an ENI compression
watchdog) touches disk every ~5 minutes: it refreshes `MASTER_STATUS.md`, rewrites
`status_hub.cron.log`, and can touch one or a few `STATUS_BUILDER_*.md` files (e.g. a
builder parked at IDLE). So **a fresh mtime on MASTER_STATUS/log is NOT evidence the
floor is building.** To report whether builders are actually executing, do BOTH:
1. Check for real worker processes: `ps aux | grep -iE "eni_swarm|product_lead|builder"` — if **zero** builder processes, the floor is parked/idle regardless of fresh status files.
2. Check the STALENESS of IN-PROGRESS status files: `ls -lt builds/STATUS_BUILDER_*.md | head`. If an IN-PROGRESS file has an old mtime (e.g. ~2 weeks), it is frozen proof the builder stopped, not that it is working.
A fresh-keep-alive + fresh-IDLE-file + zero-builders + stale-IN-PROGRESS combination means: **infra healthy, floor parked awaiting LO directives via FIFO** — recommend a restart/kick, do not claim a stall.

### MASTER_STATUS "merged fleet" counts are a STALE VIEW, not current work
`status_hub.py` summarises the full ~598-mini MERGED fleet (across STOCKBOT /
DEMIURGE / DEMIURGE3D / LUMEN) as e.g. "207 done / 388 in-progress / 3 blocked".
These numbers are dominated by stale entries "from Jul 9-13" and only reflect the
landscape, NOT the ~50-builder `STATUS_BUILDER_*` build floor. When reporting fleet
health, **lead with the 50-builder ledger** (`HEARTBEAT_LEDGER.md`) and treat both the
688-count AND the merged in-progress count as coarse/possibly-stale background, not as
a measure of what is currently executing.

### Three-way triage: ACTIVELY BUILDING vs PARKED vs DOWN
When the ledger + mtimes are stale, don't just say "fleet dead" — run the three-state
discriminator. These three read identically in the ledger (many old-mtime IN-PROGRESS
rows) but differ in what to report to LO:

- **ACTIVELY BUILDING**: at least one `builds/STATUS_BUILDER_*.md` fresh within the
  stall window AND a live builder proc (`ps aux | grep -iE 'STATUS_BUILDER|eni_build'`).
  Report builders working by name.
- **PARKED / quiescent (the common idle state; NOT a fire)**: status files cluster
  weeks old, no builder procs, BUT infrastructure is healthy. Verified signals to
  confirm "parked, not crashed":
  - `curl -s http://127.0.0.1:8922/health` → `{"status":"ok","proxy":"swarm_turbocharger",...}`
    (free_router :8920 and claude_cli_proxy :8912 also up in `ps aux`).
  - A tmux session exists (`tmux ls`, e.g. `eni2p`), meaning the floor shell is alive.
  - `status_hub.cron.log` (cron every 5 min) keeps emitting the SAME MASTER_STATUS
    snapshot verbatim across many runs — no changing counters = no work being routed.
  Report: "fleet parked awaiting LO directive", and list the un-issued
  `/tmp/eni_ctl_BUILDER_<n>` FIFOs as the action item to resume.
- **DOWN / crashed**: stale status files AND infra ALSO missing — no turbocharger/free_router
  procs, no tmux, FIFOs absent. That is a recovery situation (see eni-swarm-floor-recovery),
  not a quiescent report.

Rule: infra-health (proxies + tmux + snapshot-delta) is what separates "parked" from
"down". Ledger staleness alone cannot.

### Don't over-index on exact state COUNTS
A fresh classifier scan can disagree with `monitor_fleet.py`'s ledger on how many
builders are IN-PROGRESS (regex mapping differs — e.g. an UNKNOWN state falls
through to DONE in the monitor). Cite a range ("6–8 IN-PROGRESS") and describe
which builders, not a brittle exact count, and note that ledger [DONE] may include
files that internally say ACTIVE.

### PITFALL — `monitor_fleet.py` misses the auxiliary ENI_Swarm_NEW watcher
`monitor_fleet.py` only reads `builds/STATUS_BUILDER_*.md` under the swarm dir
(`/home/hunter/Commander/eni_swarm`). It does NOT see a separate live thread:
`/home/hunter/Desktop/Projects/ENI_Swarm_NEW/STATUS_BUILDER_50.md`, kept fresh by
`/home/hunter/.hermes/scripts/builder_50_watcher.sh` (a persistent process).
So when the 50-builder Commander fleet is all-parked (mtimes clustered ~14 days) but
`ENI_Swarm_NEW/STATUS_BUILDER_50.md` is freshly written, the correct reading is
"fleet parked EXCEPT one warm auxiliary builder (BUILDER_50, usually [IDLE] waiting for a
task)", NOT "all 50 builders dead". Before declaring the fleet fully stopped, always check
both roots: `ls -lt` on `Commander/eni_swarm/builds/` AND `cat`
`Desktop/Projects/ENI_Swarm_NEW/STATUS_BUILDER_50.md`. A parked fleet is an operational
status, not an outage — report it as "parked awaiting LO directives," not as a crash.

### PITFALL — a fresh mtime can be an IDLE re-verification ping, NOT live work
A freshly-written STATUS file is not always an IN-PROGRESS builder. A parked builder that
runs a periodic re-verify will re-check its control FIFO, find no directive, and REWRITE its
STATUS file with fresh content marked **IDLE** — so its mtime looks "today" while it is doing
nothing. Symptom of this case: the fresh file is a verbose status like:
`# STATUS_BUILDER_N — IDLE — <ts> MDT` / "Control FIFO /tmp/eni_ctl_BUILDER_N does not exist
(re-verified empirically ...)" / `blocker=none`. 

### QUICK NUMERIC SNAPSHOT (before deep-reading individual files)
Run a one-liner over the fresh `HEARTBEAT_LEDGER.md` for a compact numeric read:
```bash
cd /home/hunter/Commander/eni_swarm && python3 -c "
from collections import Counter
c=Counter(); ents={}
for ln in open('HEARTBEAT_LEDGER.md'):
    t=ln.split(); s=t[0].strip('[]'); n=int(t[1].split('_')[1])
    c[s]+=1; ents[n]=s
print('TOTAL',len(ents)); print(dict(c))
print('IN-PROGRESS',[n for n,s in ents.items() if s=='IN-PROGRESS'])
print('BLOCKED',[n for n,s in ents.items() if s=='BLOCKED'])
print('gaps',sorted(set(range(1,51))-set(ents)))"
```
This surfaces, at a glance: total tracked builders, per-state counts, the exact
non-DONE list, and **numbering gaps** (missing `STATUS_BUILDER_N` — e.g. a gap at
20 with no file means a builder was never spawned or its file vanished, worth a
mention in the report). Pair it with the mtime-cluster check; count + mtime
together are faster and more reliable than reading all ~50 files individually.

**ALWAYS read the fresh file's state token before calling a builder "working".** Fresh mtime
+ `[IDLE]` / "IDLE" state = warm idle waiter (parked, primed, not building), NOT activity.
The warm idle aux can be in EITHER root: this session it was `Commander/eni_swarm/builds/`
BUILDER_37 (fresh IDLE re-verify), not the ENI_Swarm_NEW BUILDER_50 the runbook previously
assumed. When the fleet is otherwise ~14-day-parked and only 1–2 files are fresh IDLE, report
"fleet parked, alive waiters primed for directives" — not "builders are working."

### PITFALL — a `[BLOCKED]` ledger line is usually a DISPATCH GAP, not a real stall
When `monitor_fleet.py` forces/list-parses a builder as BLOCKED, read the file body before
calling it an infrastructure failure. The two common BLOCKED spellings are:
- `no task assigned` / `awaiting PRODUCT_LEAD dispatch via FIFO or master routing` →
  the builder is **parked and unrouted**, not faulted. It is waiting for a directive to be
  written to its `/tmp/eni_ctl_BUILDER_<N>` FIFO or for PRODUCT_LEAD to route it a task.
- A "false block" where the builder's own notes say its underlying streams are DONE on disk
  (e.g. B4-the-flag marked BLOCKED while the status note says "3 BLOCKED — false — all DONE
  on disk"). Confirm against the actual STATUS file content rather than trusting the flag.

Neither is a crash/stall requiring intervention. Correct verdict: "swarm parked, N builders
waiting to be dispatched" and the recommended action is to **write a directive to the FIFO
(`/tmp/eni_ctl_BUILDER_<N>`) or run PRODUCT_LEAD routing** — NOT to restart/repair anything.

### PITFALL — infra procs up ≠ builders running (use `ps aux` to disambiguate)
Stale clustered STATUS mtimes TELL you the fleet halted, but you must still distinguish
"swarm parked / dispatchable" from "infrastructure is down". Before reporting a hard outage,
verify infra is alive with the ACTUAL queries from a 2026-08-09 run:
```
ps aux | grep -iE "builder|eni|swarm|demiurge" | grep -v grep
ps aux | grep -iE "python.*build|swarm" | grep -v grep
```
Expected-survives set when only the PARKED infra is running: `eni_controller.controller`,
`eni_local_chat.py` (under tmux), `daemon.eni_kb_daemon`, `swarm_turbocharger.py --port …`,
postgres backing demiurge DBs — and NO per-builder worker procs. Per-builder FIFOs
(`/tmp/eni_ctl_BUILDER_*)` de-confirm further: their existence means agents but nothing active.
If the grep-only matches infra procs (no `python*status*builder` worker), that is the
**definitive cross-check confirming "parked, not crashed"** — report dispatch-needed, never restart.

### MISSING/EMPTY `HEARTBEAT_ALERTS.md` = BLOCKED comes from the STATUS file alone
`monitor_fleet.py` reads `HEARTBEAT_ALERTS.md` to force listed builders to BLOCKED, but the
file is often absent/empty (verified: not present at monitor's expected path on a fresh run).
Consequences: (1) any `[BLOCKED]` in the ledger is then sourced purely from the builder's own
STATUS file text (`[BLOCKED] … Blocked on: …`), NOT the alert override — so before trusting a
BLOCKED flag, `cat builds/STATUS_BUILDER_<N>.md` and confirm it actually self-labels BLOCKED;
- a builder whose
block lives only in HEARTBEAT_ALERTS.md will be misread. Check `ls HEARTBEAT_ALERTS.md` and
note its absence in the report rather than assuming the alert system participated.

### PITFALL — TWO aggregators, same interpretation: don't let MASTER_STATUS alarm you either
`HEARTBEAT_LEDGER.md` is NOT the only status aggregator. `status_hub.py` (worker w2) separately
regenerates `MASTER_STATUS.md`, which sweeps the WHOLE fleet (`eni_swarm/STATUS_ENI*.md` +
`demiurge_scaffold/` recursive) and is far bigger: hundreds of `[STALLED IN-PROGRESS] quiet
>10m` rows and a large ALERT count (e.g. 598 minis / 207 DONE / 388 IN-PROGRESS / 3 BLOCKED /
**391 ALERTS**). When it genuinely refreshes (mtime updates each cycle), that only proves the
status_hub worker is alive — not the fleet. The MASTER_STATUS alerts are the SAME stale-
IN-PROGRESS condition already explained above, scaled up. A regenerated MASTER_STATUS with a
huge alert count, co-existing with healthy controller infra (`curl :8940/health` -> queue
pending:0), dead per-builder procs, and no per-builder FIFOs, is encore-dormancy — NOT a live
stall wave. Treat MASTER_STATUS exactly like the ledger: regenerate + cross-check
mtime-spread / procs / FIFOs before reporting "the fleet is broken." The two files are
parallel lenses on the one underlying (stalled) fleet.

### PITFALL — a FRESH per-builder mtime is NOT evidence of one live builder
When assessing a mostly-idle fleet, don't be fooled by a single STATUS file whose mtime is
TODAY while every other builder is weeks stale. A builder can re-touch its own file to
declare `IDLE` / `# STATUS ... IDLE` with `blocker=none` and `next=awaiting LO directive via
FIFO` — a cron/heartbeat survivor that never exits. Verify before reporting "1 builder
alive":
- read the file body: does it say `IDLE`, and does `next=` reference a control FIFO that has
  NOT been created (`ls /tmp/eni_ctl_BUILDER_<n> 2>/dev/null` -> absent)?
- is there a matching live proc (`ps aux | grep <builder>`), not just the generic
  `status_hub.py` / `swarm_turbocharger.py` / `free_router.py` / `claude_cli_proxy.py` infra
  daemons that are always present?
A file touched today + IDLE body + no FIFO + no per-builder proc = parked/idle, not live.
The correct fleet verdict in that case is "idle/awaiting directive", and the action is to
create the FIFO + write a directive — not to celebrate an active worker. Sorting the
`STATUS_BUILDER_*.md` listing by mtime (`ls -lt`) and inspecting only the newest few is the
fastest way to spot this lone-fresh-IDLE-file case.

### PITFALL — stale [IN-PROGRESS] markers are NOT live work
The reverse of the fresh-IDLE trap: a ledger line of `[IN-PROGRESS]` does NOT mean a
builder is working. It only mirrors whatever state token is written in the status FILE,
which may be days/weeks old. `monitor_fleet.py` performs no age check — a builder that
wrote `[IN-PROGRESS]` on Jul 25 and hasn't been touched since still lands as
`[IN-PROGRESS]` in today's ledger. Before ever reporting "N builders are actively
building," cross-check the **mtime** of every status file that reads non-DONE:
`ls -la --time-style=long-iso builds/STATUS_BUILDER_*.md | awk '$6>="<today>"'` or
`scripts/fleet_mtime_staleness.py`. Verified 2026-08-11: 49 of 50 files were 17 days
stale; only BUILDER_37 had touched its file that day. Verdict was "fleet parked/idle —
no live worker procs (`ps aux | grep builder` = 0), only B37 re-verified its FIFO," NOT
"8 builders actively building." group IN-PROGRESS count with staleness: if every
IN-PROGRESS file is old, the correct story is "stale markers from a prior snapshot," not
live load.

### Cross-check infra liveness via the ENI Controller HTTP API
When builder procs are 0 (fleet parked) but you want to confirm the CONTROL PLANE is
alive before concluding "everything is down", hit the controller (usually
`127.0.0.1:8940`):
- `GET /health` -> JSON `{"checks":{...}}` with airllm/free_router/secrets broker
  sub-checks all `ok:true`. This is the authoritative "infra healthy" signal.
- `GET /status` -> controller version + free-router model list (verifies model backend
  is serving). No builder/agent sub-state here — it proves the plan, not the fleet.
- `GET /` and any `/flights /fleet /builders /swarm /active /jobs` return **404** —
  the controller has no fleet-state endpoints despite the name; don't waste probes on
  them, use the /health + /status pair only.
Corroborate with `pgrep -af STATUS_BUILDER` / `pgrep -af eni_swarm` (0 = no live
workers) and presence of `/tmp/eni_ctl_BUILDER_*` FIFOs. A healthy controller + zero
builder procs = parked fleet awaiting LO directive, which is the correct story when the
ledger is full of stale IN-PROGRESS markers.

### GOTCHA — ledger state-count vs raw file-scan state-count disagree
`monitor_fleet.py` collapses anything not explicitly `IN-PROGRESS`/`BLOCKED` down to
`DONE` (its last branch maps every other token to DONE; it also forces BLOCKED for
builders named in HEARTBEAT_ALERTS.md and skips blank/crash files). So a naive
`grep -c BLOCKED` or an independent state tally over the STATUS files will NOT match
the ledger. This session: monitor's ledger reported 1 BLOCKED / 8 IN-PROGRESS / 40 DONE,
while an independent raw-text scan (BLOCKED if "BLOCKED" appears anywhere, etc.) gave
4 BLOCKED / 5 IN-PROGRESS / 1 BLANK. Both are "correct" under different definitions.
**When reporting fleet state, quote the monitor ledger (the canonical artifact), and
only cite a raw scan count if you state its heuristic.** Don't present the two as a
contradiction or chase the mismatch — the ledger's DONE bucket silently absorbs stale
and ambiguous files by design.

### Speed tip: start with MASTER_STATUS.md, not the per-file crawl
For a WHOLE-fleet triage, `MASTER_STATUS.md` (`status_hub.py`-generated,
self-healing, regenerated fresh every ~5 min) consolidates every project STATUS +
the complete consolidated ALERTS list in ONE file — with the explicit alert rule
itself (BLOCKED, OR non-DONE older than 10 min is an alert; DONE is never a stall).
Read it BEFORE crawling the 50 builder files. Honor its `Generated:` timestamp, and
confirm any finding you'd act on against the raw STATUS file first. For a quick
staleness anchor: if nearly every alert is `quiet ~49-52k m` with last-update in
early Jul, the whole swarm has been dormant for weeks — that's the "stale snapshots,
not live work" verdict. See `references/master-status-hub.md`.
