# Fresh mtime ≠ liveness; the liveness probe is skill-bundled, not on disk

Verified across the 2026-08-12 and 2026-08-13 cron monitoring passes.

## 1. The liveness probe script is NOT a disk file — fetch it from the skill

The SKILL.md body and fleet-interpretation-runbook tell you to run
`scripts/fleet_liveness_probe.sh`. That path is inside the SKILL BUNDLE, NOT at
`/home/hunter/Commander/eni_swarm/scripts/`. Running the bare path fails with:

    bash: .../eni_swarm/scripts/fleet_liveness_probe.sh: No such file or directory

To get the probe: call `skill_view(name='eni-swarm-telemetry',
file_path='scripts/fleet_liveness_probe.sh')` and copy its logic inline, or just
re-type the probe steps directly (count status files, state distribution, mtimes
fresh_today, ps for build procs, /tmp/eni_ctl_* FIFOs, head of newest file). The
shell logic is short and stable — it is safe to reproduce inline rather than
depend on a disk file that may not be present.

## 2. A freshly-touched STATUS file can itself be an IDLE/parked marker

"Fresh mtime" is frequently treated as the real liveness signal — but it is not
sufficient. In the 2026-08-12 run, `STATUS_BUILDER_37.md` was the ONLY status
file touched in 2+ weeks (re-verified update at 01:17), yet its body read:

    # STATUS_BUILDER_37 — IDLE — Wed Aug 12 01:17 2026
    Control FIFO /tmp/eni_ctl_BUILDER_37 does not exist ...
    blocker=none
    next=await LO's directive via /tmp/eni_ctl_BUILDER_37 FIFO creation

i.e. a builder that re-checked in to say it is parked and waiting on a control
FIFO that has never been created. So when cross-checking liveness: a fresh mtime
confirms the process poked the file recently, but you must still read the STATUS
body to distinguish "actively building" from "re-confirmed parked/idle". The
signal to report to LO is the body ("IDLE, waiting for missing FIFO"), not the
mtime.

## 3. `status_hub.cron.log` spam is NOT a liveness signal

`status_hub.cron.log` in `eni_swarm/` rewrites the SAME aggregate line on every
hub-cron tick, e.g. hundreds of consecutive:

    MASTER_STATUS.md refreshed: 598 minis (207 done / 388 in-progress / 3 blocked), 391 ALERTS

Do not mistake a long tail of these for builder activity — it is a separate
`status_hub` integration refreshing `MASTER_STATUS.md`, and the counts it prints
are drawn from stale Jul-era minis (ages of 47,500+ min are visible in the
MASTER_STATUS table). It neither proves nor disproves live builders. Cross-check
against the actual `STATUS_BUILDER_*.md` mtimes instead. Similarly `391 ALERTS`
in that line can be stale and uncleared — read `HEARTBEAT_ALERTS.md` directly.

## 4. Decisive liveness cross-check on a fleet-wide stale pass (2026-08-13)

On the 2026-08-13 cron pass the tips above were re-confirmed and two sharper
signals emerged for distinguishing "down/abandoned" from "idle but up":

- **Empty process table is the tiebreaker.** When builder STATUS mtimes are
  frozen fleet-wide (~19 days for BUILDER_01–50 in this pass), run
  `pgrep -af "eni_swarm|STATUS_BUILDER|demiurge_freed_swarm|status_hub"` and
  filter out the cron harness itself (grep -v the `bash -c`/`__hermes`/`pgrep`
  wrapper lines). If that returns NOTHING, the fleet is down — no supervisor is
  running. mtime staleness is suggestive; an empty proc table is conclusive.
- **Control-FIFO inventory predicts liveness.** `ls -la /tmp/eni_ctl_*` is a
  cheap second probe: if only a handful of FIFOs survive (this pass: just
  `eni_ctl_BUILDER_50` + `DEMIURGE*_B01–B12`) while ~50 builders claim to exist,
  the fleets' control layer has collapsed and parked builders' own heartbeats
  will report "FIFO does not exist." That self-reported missing-FIFO line IS the
  parked/abandoned tell — report it verbatim.

## 5. Ledger "DONE" is status-collapse, not completed work

`monitor_fleet.py` / `status_hub.py` map ANY non-BLOCKED / non-IN-PROGRESS state
to DONE. A builder whose STATUS body reads `[READY]`, `[IDLE]`, or `[READY] ...
awaiting LO directive` therefore shows as **DONE** in the ledger even though it
never did work. So a ledger of "47 DONE / 2 IN-PROGRESS / 1 BLOCKED" does NOT mean
47 builds finished — most of those rows are parked/empty snapshots. When reporting
a fleet snapshot to LO, do not present ledger DONE counts as completed work; read
the STATUS bodies (or the probe's state distribution) for the real picture.

## Whole floor dormant → ONE file still looks "fresh" (watchdog self-refresh trap)

When the entire 50-builder floor has gone quiet (all STATUS mtimes weeks old, no
builder/heartbeat/watchdog procs running), a single builder file may still show a
RECENT mtime (e.g. `STATUS_BUILDER_37.md` 0.5h old among 49 at ~480h). Verify before
reporting it as "a live builder": read the file body — it often carries a line like
`# STATUS_BUILDER_37 — IDLE` plus `re-verified empirically via cron watchdog at
<ts>: [ -e ] NO_ENTRY. No directive issued.` That freshness is the **cron watchdog's
own idle re-touch**, not builder activity. If no control FIFO
(`/tmp/eni_ctl_BUILDER_37`) exists and no builder proc is running, it is IDLE, not
alive. Cross-check: fresh mtime from a watchdog write + `NO_ENTRY` FIFO + zero eni
procs = floor dormant, report as such (do NOT flag the fresh file as progress).

## Fleet-wide control-FIFO enumeration — fast infrastructure-dormancy probe

Beyond the per-builder `NO_ENTRY` check above, run a fleet-wide control-FIFO sweep
to size the whole control plane in one command:

    ls -la /tmp/eni_ctl_BUILDER_* 2>/dev/null | wc -l
    ls -la /tmp/eni_ctl_BUILDER_* 2>/dev/null

Observation from the 2026-08-14 pass: the ledger reported 8 IN-PROGRESS / 1 BLOCKED
builders, but a fleet-wide FIFO enumeration showed **exactly one** live control FIFO
(`/tmp/eni_ctl_BUILDER_50`, created days earlier). Zero or near-zero live FIFOs across
a 49-50 builder fleet is a decisive "control plane down / floor dormant" signal even
when the ledger's state distribution still shows IN-PROGRESS entries — those are stale
relics, not live workers. Use FIFO count as a cross-check against state distribution;
a big gap (many builder files, near-zero FIFOs) = dormant fleet. Pair with the status
file mtime sort (`ls --time-style` on `builds/STATUS_BUILDER_*.md`) to show how stale
the "active" states really are.

## Definitive dormant-vs-degraded cross-check: `ps aux` process table

Stale mtimes + FIFO gaps alone prove *idle*, not whether the swarm is parked-and-healthy
vs crashed. On cron monitor passes, settle it with a process-table cross-check (verified
2026-08-15 pass):

    ps aux | grep -iE "eni_|builder_|STATUS_" | grep -v grep

A **dormant-but-healthy** fleet shows ONLY the persistent controller/bridge/daemon procs
(e.g. `eni_controller.controller serve --port 8940`, `eni_local_chat.py`,
`daemon.eni_kb_daemon`) and ZERO builder-worker procs. That is the expected state for a
swarm parked waiting on LO/PRODUCT_LEAD dispatch — report as *dormant, not degraded* and
take no action (cron monitor must not re-dispatch). If a builder that claims
IN-PROGRESS has no corresponding worker proc AND its STATUS file is weeks stale, it's a
phantom in-flight relic, not a live build. This process check is the single most
decisive signal for the "dormant, not degraded" wording in the cron report.

## PITFALL: tool output is wrapped in an ENI-COMPRESSED carrier — parse the RAW file, not the wrapped terminal text

On this box, many tool results (`terminal`, `read_file`, even `skill_view`) come
back wrapped in an `<ENI-COMPRESSED ratio=Nx carrier=...png>` envelope that only
shows a truncated `--- head ---` / `--- tail ---` slice plus `{"output": ...}`.
Naive regex over that wrapped text silently misses lines (e.g. `read_file` adds
`N|` line-number prefixes, so `^\[STATE\]` matches nothing; the mid-list rows are
invisible in the truncated slice).

Workaround that worked on 2026-08-15:
- To actually parse a generated report, re-read it off disk and strip the
  `\d+|` line-number prefix: `sed -E 's/^[0-9]+\|//' HEARTBEAT_LEDGER.md | ...`.
- For mtime staleness, pull raw epochs yourself instead of trusting the wrapped
  listing: `for f in STATUS_BUILDER_*.md; do echo "$f $(stat -c '%Y')"; done`
  then diff against `date +%s`. This is exactly what `fleet_mtime_staleness.py`
  does. Keep probes small (use `head`/`-c`) so the carrier doesn't truncate the
  rows before they reach the enclosed `output` field.

## ⚠️ 3. The ENI compression carrier SKEWS terminal `ls` mtimes — read them other ways

Verified 2026-08-15 cron pass. `terminal` output round-trips through the ENI
compression carrier, and in that pass the `ls -la --time-style=+%H:%M` column
came back **looking fresh** (16:14, 17:53) while the actual write times were
**Jul 25 (~20.9 days stale)**. The `date +%H:%M` in the same call even showed a
different "now" than reality. Do NOT trust mtime columns surfaced through the
carrier.

Trustworthy sources instead:
- `read_file` on the STATUS file — its embedded header line carries the real
  author timestamp (`# STATUS — Fri Aug 14 15:57 2026`). The compressed head/tail
  view still exposes this first line, so a single read gives you the true age.
- `execute_code` with `os.path.getmtime(p)` and `datetime` — computes real
  staleness independent of the carrier (cheap, no compression on that path).

So to distinguish "fresh re-check-in" from "stale Jul 25 relic," read the file's
own header line and/or compute `getmtime`, rather than trusting a terminal `ls`
mtime column.

## Blank STATUS file ⇒ builder silently dropped from the ledger (not a dead worker)

Observed on the 2026-08-16 cron pass: the ledger listed **49 of 50** builders and
matched no BUILDER_20 line. Cause: `STATUS_BUILDER_20.md` existed but was **empty/blank
(0 bytes)**. `monitor_fleet.py` has a crash guard that skips any status file with no
non-whitespace content (`if not lines or not any(l.strip() for l in lines): continue`),
so a blank file never produces a ledger entry.

Interpretation rule:
- **A builder present on disk but absent from the ledger = its STATUS file is blank**, not
  a dead/failed worker and not a missing file. It's an uninitialized stub (or a crash
  wiped its status header). Treat it as a builder to (re)initialize, not investigate a
  lost process.
- `read_file` on the blank file reports `0 lines`, which matches the crash-guard skip.
- When reconciling ledger count vs `STATUS_BUILDER_*.md` file count, expect `ledger_count
  = file_count - <blank stubs>`. Builders 1–50 with 49 ledger rows ⇒ exactly one blank stub.

## Parsing quirk: ENI-compression carrier wraps terminal/execute_code output

On this box, terminal and `execute_code` stdout can come back wrapped in an
`<ENI-COMPRESSED …>` envelope (carrier PNG, `decompress(carrier)` to recover). That
wrapper corrupts naive parsing — in the 2026-08-16 pass, running the ledger through a
python regex in `execute_code` returned `unique builders: 0 / State counts: {}` because
the real bytes lived under the carrier. **Does NOT mean the fleet is empty.** For
authoritative counts read the ledger/status files directly with `read_file` (its content
is unwrapped and deduped) or `decompress()` the terminal output first. Prefer `read_file`
over shelling out for ledger parsing.

## Recommended triage order (if you re-dispatch, which the cron monitor must NOT)

Unblock the one builder that actually re-checked in first: create its missing
control FIFO (`/tmp/eni_ctl_BUILDER_37`) and/or re-dispatch via master-driver.
Then formally reset the stale IN-PROGRESS/BLOCKED relics (Jul 25-26 mtimes) so the
ledger stops showing phantom in-flight work.