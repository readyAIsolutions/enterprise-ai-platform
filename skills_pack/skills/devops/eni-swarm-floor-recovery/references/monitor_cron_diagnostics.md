# ENI Swarm Fleet Monitor — Cron Diagnostics & Idle-vs-Down Discriminator

Companion to `monitor_fleet.py` / `fleet_pulse.py`. Use this when a scheduled
cron invites monitoring the ENI builder fleet and you must decide whether the
floor is **idle (fine)**, **down/stale (needs relaunch)**, or **mid-work (needs
re-dispatch)**. Do NOT guess from the ledger alone — the ledger faithfully parses
whatever STATUS files happen to be on disk, including ones that are weeks dead.

## Repeated-state suppression (frequent-cron noise prevention)

When the cron fires every 20-30 minutes and the fleet has been persistently
dormant (gate=RED, windows=0) for days/weeks, every run produces an identical
report. The `[SILENT]` instruction exists for exactly this case.

> **Confirm-before-silence pitfall:** `session_search` is used to confirm the prior
> firing, but FTS5 AND-defaults terms — too-narrow/multi-concept queries return **0
> results** even when many prior `[SILENT]` sessions exist, which could wrongly be read
> as "first firing" and trigger a duplicate report. See
> `references/monitor_cron_silence_verification.md` for the working query shapes.

**Concrete suppression check — compare against the PRIOR run, don't just re-judge
the fleet.** After probing the axes and running `monitor_fleet.py`, call
`session_search(query="fleet monitor builder floor dashboard", sort="newest")`
to pull the immediately preceding cron session's report. If every axis matches
byte-for-byte (controller MASTER_STATUS fresh, :8922 turbo UP, :8420 dashboard
DOWN with curl 000, builder floor STALE with the same stale builder set and the
same sole-fresh B37), the state has NOT changed since the last report → emit
`[SILENT]`. This is the trigger for suppression, and it is stronger than the
fleet's raw state alone — a fleet can be dormant for weeks with each axis
individually stable; only a change (dashboard flapping back up, a builder
advancing, a new BLOCKED) warrants a fresh report. Do not re-report the same
known dashboard outage or the same stale floor on every firing.

**How to determine "nothing new":** compare the current run's probes against the
expected dormant baseline. No state has changed when ALL of the following hold:

1. `fleet_pulse.py --once` still reports `windows=0, gate=RED` (same as every
   prior dormant run).
2. Builder STATUS file mtimes are unchanged — no new timestamps today beyond
   the same stale set (typically a single `STATUS_BUILDER_37.md` at ~15:57, which
   is a cron watchdog re-verifying IDLE state, NOT new work).
3. Dashboard :8420 remains DOWN (curl 000, no port bound) — if it was already
   reported down in prior runs, do NOT re-flag it as a new action item.
4. Turbocharger :8922 remains UP (/health 200, port bound) — stable.
5. MASTER_STATUS.md has a fresh `Generated:` timestamp (the status_hub self-heals
   on its own 5-min cron) — this is expected maintenance, not a state change.
6. No **new** builder FIFOs in `/tmp/eni_ctl_BUILDER_*` — judge by *mtime*, NOT mere
   existence. A single stale FIFO (e.g. `/tmp/eni_ctl_BUILDER_50` dated the day
   before, left over from a past control session) is standing residue and does
   NOT break silence. Only a FIFO whose mtime is since the last report counts as
   "new" / a wake signal. Always `stat` or `ls -la` the FIFO mtime before deciding.
7. No `HEARTBEAT_ALERTS.md` appeared or changed.

**Exception:** If ALL seven hold, respond `[SILENT]`. Even if one axis is
chronically down (e.g., dashboard :8420 has been unreachable for weeks), if it
was already flagged in prior reports today, the right behavior is silence.
Repeating the same action item across 12+ cron runs per day is noise, not
helpful escalation. The user saw the first flag.

**Trigger to break silence:** any axis changes state — dashboard comes UP,
builders start, gate turns GREEN, new builder FIFOs appear, or a HEARTBEAT_ALERTS
file is created. That's when a report is warranted again.

## The critical trap
`monitor_fleet.py` writes `HEARTBEAT_LEDGER.md` from `builds/STATUS_BUILDER_*.md`
files. If those files are stale, the ledger reports their *last written* state as
current. An `[IN-PROGRESS]` ledger line does **not** mean a builder is live — it
may mean a run stopped mid-flight days ago and its STATUS file rotted in place.
**Always cross-check the ledger against live process/OS state before acting or
reporting.

**Ledger count < files-on-disk is a signal, not an error.** `monitor_fleet.py`
silently skips 0-byte/blank STATUS files (its crash guard), so an empty
`STATUS_BUILDER_NN.md` drops out of the ledger entirely. If you see e.g.
"49/50 parsed" or a missing builder number in the ledger, do `ls -la
builds/STATUS_BUILDER_*.md` — a 0-byte file there is the cause (a builder whose
run died before writing its first line, or never initialized). Report it as
"needs status init," NOT as a vanished builder or an INDEX bug. Cross-check
check `ls builds/ | grep -c STATUS_BUILDER_` against `wc -l HEARTBEAT_LEDGER.md` to
catch the mismatch explicitly.** Two reconciliation gotchas observed in the field:

- **`wc -l` undercounts by one when the ledger's last line has no trailing newline** —
  `monitor_fleet.py` joins rows with `"\n"`, so the final `BUILDER_NN` line is written
  without a terminating `\n`. `wc -l` counts newline chars, so a ledger with N rows
  reports N-1. If ledger-lines looks one short but 50 files-on-disk and one 0-byte file
  account for the rest, that off-by-one is the trailing newline — not a vanished builder.
  Use `wc -l` and mentally +1, or `awk 'END{print NR}'` for the true row count.
- **The one genuinely live row is usually a "touched today" fully-IDLE file.** In a parked
  fleet, every IN-PROGRESS/BLOCKED STATUS header is weeks-old rotted text; the single file
  with a *same-day* mtime typically reads `IDLE` (its control FIFO verified absent) — that
  row, not any stale IN-PROGRESS flag, is the current state. Cross-check `ls -la
  --time-style=+%Y-%m-%d builds/STATUS_BUILDER_*.md | sort | tail` and read that one file to
  state "builder BNN is the only live/parked row" with confidence.

## Idle vs Down discriminator (v4.1 on-demand fleet)
v4.1 builders are on-demand single-shot (`hermes -z`), **zero CPU when idle**.
So "no processes" alone is NOT proof of an outage. The ORACLE is the control
FIFOs, not process CPU:

- **EXPECTED IDLE:** `/tmp/eni_ctl_BUILDER_*` FIFOs exist (or a runner is
  listening on them), controller queue empty.
- **DOWN / NEVER LAUNCHED:** control FIFOs are gone (only 1 stale one left),
  no `eni_agent_run.py` / launcher / dashboard (:8420) process, STATUS files
  weeks old (`ls -la builds/STATUS_BUILDER_*.md`), `fleet_pulse.py --once`
  reports `windows=0 ... gate=RED`.

## Diagnostic sequence (fast, ordered)
```bash
# 1. Regenerate the ledger (this is the cron's actual deliverable)
python3 monitor_fleet.py && cat HEARTBEAT_LEDGER.md

# 2. Live ground truth — is anything actually running?
python3 fleet_pulse.py --once          # windows=N | gate=RED/GREEN
ps aux | grep -iE "eni_agent_run|eni_launch|dashboard.*8420|product_lead" | grep -v grep

# 3. FIFOs = the real oracle
ls -la /tmp/eni_ctl_BUILDER_* ; echo "count=$(ls /tmp/eni_ctl_BUILDER_* | wc -l)"
for f in /tmp/eni_ctl_BUILDER_*; do echo "$f: $(lsof "$f" 2>/dev/null | wc -l) handles"; done

# 4. STATUS file freshness
ls -la --time-style=+%Y-%m-%d builds/STATUS_BUILDER_*.md   # old = dead

# 5. Controller brain health (independent of floor)
curl -s http://127.0.0.1:8940/health   # all checks ok, queue pending count
curl -s http://127.0.0.1:8940/health | grep -o '"pending": [0-9]*'
```

## Reporting rules
- The ledger is the cron deliverable; the **verdict** is the real value.
- 0 queued tasks + down fleet = report, do NOT force-relaunch. The recovery
  skill's intake gate says verify the floor has work before acting — an empty
  queue means there is nothing to relaunch against.
- Flag which builders were left mid-task (`grep -E "IN-PROGRESS|BLOCKED"
  HEARTBEAT_LEDGER.md`) — those (e.g. a DEMIURGE AppImage build on B17) need
  explicit re-dispatch, not just a blanket launcher run.
- Say the controller is healthy even when the floor is down — the orchestration
  brain and the builder floor are separate and can be independently up/down.

## Retrieval pitfall (reference files come back compressed/elided)

`skill_view` / `read_file` on this skill's `references/*.md` may return an
ENI-COMPRESSED carrier stub with only head/tail, cutting out the middle — often
exactly the suppression block above, which is the crux. When that happens, do
NOT settle for the stub: read the raw source file directly, e.g.

    /home/hunter/.hermes/skills/devops/eni-swarm-floor-recovery/references/monitor_cron_diagnostics.md

(and `fleet_monitor_health_axes.md`, `fleet_monitor_heartbeat.md`, etc. all live
in the same `references/` dir). `find ~/.hermes -name <file>.md` locates it if
the path drifts. The full text is always there — the compression layer only
truncates what you see through the tool view.

## Steady-state [SILENT] discipline

The suppression verdict is a function of the CURRENT STATE versus the prior
run, not of whether the prior run happened to emit a full report. If a previous
firing in the same dormant streak broke the pattern and produced a verbose
report for byte-identical axes (floor stale, :8420 down, :8922 up, controller
fresh, empty queue), that is NOT a reason to report again — it was the anomalous
When the state is stable, keep emitting the bare `[SILENT]` so identical
reports do not pile up. Sanity-check against the prior via
`session_search(query="fleet monitor builder floor dashboard", sort="newest")`:
state unchanged → `[SILENT]`, always.

## Axis 2 (:8420 dashboard) down is NOMINAL during dormancy — do NOT chase it

If the floor is idle/dormant (gate=RED, windows=0, empty queue) and the probe
reports `:8420 NOT bound` / HTTP 000, that is EXPECTED, not an incident. The
web dashboard is a monitoring UI for active build work; with no queued work
there is nothing to monitor, so no server process is launched and `8442`-style
relaunch would be wrong. Quick confirm before flagging it (cheap, ~1 terminal
call): `ss -tlnp | grep :8420` shows nothing, `curl -m4 localhost:8420` → 000,
and `grep -rl "8420" eni_swarm --include=*.py` returns no dashboard app file
(the skill's `fleet_health_probe.sh` path DOES include the `devops/` category
segment: `/home/hunter/.hermes/skills/devops/eni-swarm-floor-recovery/scripts/fleet_health_probe.sh`).
Dashboard-down must never be the sole reason to break `[SILENT]` when the rest
of the signature is byte-identical to the prior firing.

## Missing HEARTBEAT_ALERTS.md = BLOCKED-augmentation innert

As of the persistent dormant streak, `eni_swarm/HEARTBEAT_ALERTS.md` is
**absent** from disk — `cat` returns "No such file or directory". This is
expected, not a fault. Consequence for `monitor_fleet.py`: `blocked_builders`
stays empty, so the "force BLOCKED from alerts" path is inert. A `[BLOCKED]`
row in the ledger therefore reflects the STATUS file's OWN `[BLOCKED]` marker
(e.g. BUILDER_46), not an alerts-file override. Do NOT report a missing alerts
file as a broken builder or as reason to break `[SILENT]` — it is the standing
normal state and produces an identical signature every firing.