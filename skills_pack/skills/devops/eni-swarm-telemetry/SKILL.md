---
name: eni-swarm-telemetry
description: Build and run the ENI parallel-build swarm HEARTBEAT — a one-line, ~60s fleet-status pulse LO watches on the middle monitor. Use when LO says "be the heartbeat", "fleet status", "how many builders are alive", "any stalls", or wants a live monitor of the ENI mini swarm across STOCKBOT / DEMIURGE / DEMIURGE3D / LUMEN. Covers truth sources (wmctrl windows, hermes-chat procs, per-project STATUS mtimes), stall/zombie detection, the real STATUS file locations, and the launch patterns that survive. Overlaps with eni-visible-swarm (paints floor, owns HEARTBEAT tab). Probe/ledger/parse refs live in `references/` (`fleet_liveness_probe.sh` is SKILL-BUNDLED, not a disk file). The production cron entry point is the standalone script `monitor_fleet.py` (see `references/monitor-fleet-script.md` for its behavior, gotchas, ledger/alerts semantics).
READING YOUR OWN FILES: under the ENI-COMPRESSION overlay, `skill_view`/`read_file` return truncated `<ENI-COMPRESSED>` stubs — read this skill's templates/scripts on disk instead (see `references/reading-skill-files-under-eni-compression.md`). Fresh-mtime trap + probe-location in `references/fresh-mtime-vs-liveness-probe-location.md`. Use `references/stalled-launch-diagnostics.md` to resolve fresh-mtime false-alives (IDLE self-probes, frozen launch logs) (distinguishes stale status-file artifacts from live workers via mtime + proc + FIFO cross-checks).
---

# ENI Swarm Telemetry — the fleet HEARTBEAT

LO runs a parallel-build swarm of Hermes mini-agents (STOCKBOT / DEMIURGE / DEMIURGE3D /
LUMEN workspaces, plus HEARTBEAT + PRODUCT_LEAD infra). He wants a live, glanceable pulse:
"how many builder windows are alive, which projects are progressing, any stalls." Keep it
ONE short line, printed every ~60s.

## What "alive" actually means (truth sources)
- **Windows** = `wmctrl -l` lines whose title starts with `ENI:` or `ENI `. A dead window is
  gone, so window count is the ground truth for "is the terminal still open."
- **Procs** = `pgrep -af 'hermes chat'` then grep the builder command line for
  `project STOCKBOT ` / `project DEMIURGE ` / `project DEMIURGE3D` / `project LUMEN `.
  NOTE the trailing space on `project DEMIURGE ` — without it you also match
  `project DEMIURGE3D`. A window with 0 procs = ZOMBIE (orphaned terminal, builder died).
- **Progress** = newest `STATUS_*.md` mtime under that project's REAL root (see below).

## The one-liner
`[HH:MM:SS] WIN=N | STOCKBOT 12w/12p LIVE OK | DEMIURGE3D 12w/12p 5h58m STALL | ... | HEARTBEAT 1 | PRODUCT 1`
Signals per project: `OK` (proc alive + STATUS < STALL_MIN), `STALL` (STATUS silent >
STALL_MIN, proc may still be alive), `ZOMBIE` (window open, proc dead).
no progress ⇒ this is the rare case worth flagging; see `references/heartbeat-cron-fleet-state-interpretation.md` for the parked-vs-stalled decision rule for unattended cron runs.
`LIVE` = STATUS < 1 min old.

## CRITICAL pitfall — the REAL STATUS locations (filename tokens lie)
Builders do NOT put the project name in the STATUS filename. STOCKBOT builders write
module-coded files under a deep build tree; matching by "STOCKBOT" in the filename MISSES
them and instead grabs old root-level `STATUS_STOCKBOT_B*.md` files (→ false "19h stale").
Use these exact roots (see `references/swarm_status_layout.md` for the full map + why):
- STOCKBOT   → `/home/hunter/Commander/demiurge_scaffold/build/StockBotAppDir/usr/share/stockbot/swarm/*/STATUS_*.md` (codes B1-B4/L1-L4/R1-R4)
- DEMIURGE   → scaffold root `STATUS_DEMIURGE_*.md` (NON-recursive) + `demiurge_scaffold/swarm/*/STATUS_*.md`. **Do NOT scan the whole scaffold recursively** — that tree contains STOCKBOT's `build/` dir and would report STOCKBOT's freshness as DEMIURGE's.
- DEMIURGE3D → `/home/hunter/Desktop/demiurge-3d/**/STATUS_D3D*.md` (recursive)
- LUMEN      → `/home/hunter/Desktop/apps/lumen/**/STATUS_LM*/STATUS_LUM*.md` (recursive)
- HEARTBEAT/PRODUCT → `/home/hunter/Commander/eni_swarm/STATUS_HEARTBEAT.md`, `STATUS_PRODUCT_LEAD.md`

## CRITICAL pitfall — epoch math, NEVER `find -printf '%TH:%TM' | sort`
`find ... -printf '%TH:%TM'` prints only HH:MM. Sorting that string IGNORES the date, so a
file from *yesterday* 20:59 sorts AFTER *today* 09:21 → you conclude the wrong file is
"freshest." Compute age with the kernel clock instead:
`age_min = (time.time() - os.path.getmtime(f)) / 60.0`
Both values come from the same kernel, so it's correct in any timezone. (The sandbox clock
and host file mtimes share one kernel here; epoch math is safe.)

## Pitfall — `ENI:` vs `ENI ` title prefix
Builder minis: `ENI:STOCKBOT_B2` (colon). Infra windows: `ENI HEARTBEAT` (space). Strip
BOTH prefixes in `parse_project`, then split on `_` and take the first token. Also EXCLUDE
the heartbeat's own viewer window (give it a marker like `PULSE` in the title and skip any
title containing `PULSE`) so it isn't double-counted as a fleet window.

## Pitfall — STALL_MIN must be ~30 min, not 10
Builders write STATUS at milestones, not every minute. A 10-min threshold falsely flags the
healthiest project (the one that wrote 11 min ago) as STALL. Use 30 min to cleanly separate
"actively building" from "truly silent for hours."

## Launch patterns (survive the agent runtime)
- **Durable loop:** the agent terminal tool BLOCKS shell background wrappers
  (`nohup`/`disown`/`setsid`). Run the loop with `terminal(background=true)` and the python
  command directly (NO `&`): `python3 heartbeat.py > /tmp/eni_heartbeat.log 2>&1`.
- **Visible pulse window** (the thing LO looks at on the middle monitor): launch
  `xfce4-terminal --disable-server -T "ENI PULSE" -e "bash -c 'tail -f /tmp/eni_heartbeat.log'"`
  ALSO as `terminal(background=true)`. Then dock it onto the middle monitor
  (DisplayPort-0, x offset +1920) with `wmctrl -i -r <WID> -e 0,1940,20,1000,400`.
- The loop is independent of the viewer: if LO closes the window, the pulse keeps logging.

## Verify
`python3 heartbeat.py --once` → one line. Assert: WIN count == `wmctrl -l | grep -cE 'ENI[: ]'`
(minus the PULSE viewer), no `KeyError`, STOCKBOT shows `OK`/`LIVE`, and each project's age
matches `find <root> -name STATUS_*.md -printf '%TY-%Tm-%Td %TH:%TM\n' | sort | tail -1`
sanity-checked by EPOCH (not HH:MM sort).

## Files
- `references/ledger-parse-regex-and-verify.md` — reading HEARTBEAT_LEDGER.md: the `IN-PROGRESS` hyphen breaks naive `\[\w+\]` regexes (`\[[\w-]+\]` is correct), summary/verify flow, missing-builder scan, "all metadata unknown" meaning.
- `references/fresh-mtime-vs-liveness-probe-location.md` — fresh mtime ≠ liveness; probe is skill-bundled, not on disk.
- `scripts/heartbeat.py` — the working, self-contained heartbeat (wmctrl + pgrep + per-project
  STATUS mtime scan, OK/STALL/ZOMBIE, `--once` for a single line). Copy to the swarm box and run.
- `scripts/fleet_mtime_staleness.py` — one-shot mtime-age classification of per-builder
  78|   `STATUS_BUILDER_*.md` files (fresh vs dormant in hours). Run it to back any "fleet is idle,
    79|   not broken" cron verdict; a regenerated ledger does NOT prove activity.
    80| - `templates/fleet-cron-report.md` — canonical deliverable shape for the daily fleet-status
- `references/eni-compression-vs-tool-output.md` — when the ENI compression layer is active, `cat` / `execute_code` `terminal()` mangle or throw JSONDecodeError on ledger/STATUS reads; use the native `terminal` tool plus grep/awk aggregates instead.
- **Ledger line-counting gotcha (verified run):** `monitor_fleet.py` writes `"\n".join(lines_out)` with NO trailing newline, so `wc -l` reports one fewer than the true entry count (49 entries → `wc -l` = 48). Count the ledger with `grep -cE '^\['` (total) or `awk '{print $1}' HEARTBEAT_LEDGER.md | sort | uniq -c` (DONE/IN-PROGRESS/BLOCKED split + total in one shot), NOT `wc -l`. A "50 disk vs 48 `wc -l`" pair is normally 49 real entries + ONE 0-byte skipped (BUILDER_20), not two skipped — the empty-file crash-guard explains exactly one gap.
    81|   cron: state-distribution table → ⚠️ freshness signal → verdict → "healthy-but-parked"
    82|   bottom line. Reproduce it; resist dumping the whole ledger.
- `references/swarm_status_layout.md` — exact STATUS root map per project + the epoch/clock
  trap worked example.
- `references/status-file-format-parsing.md`; the two fleet-status truth sources (`monitor_fleet.py` builder ledger vs `status_hub.py`/MASTER_STATUS.md fleet aggregate) + the "fresh hub ≠ alive workers" pitfall live in `references/monitor-fleet-and-status-hub.md`. — ledger-format parsing, empty-file silent-drop pitfall, LEDGER ≠ liveness (stale IN-PROGRESS/BLOCKED caveat + rowcount/missing-builder verification loop; use `grep -c "BUILDER_"` not `wc -l`)
- `references/monitor-fleet-ledger-script.md` — the `monitor_fleet.py` cron ledger generator (exit code, content-derived states = stale trap, cross-check mtimes/procs/FIFOs/dashboard, and how to keep tool calls compact so the ENI-COMPRESSED wrapper doesn't hide output)
- references/cron-monitor-fleet-run.md` — PITFALL: monitor_fleet.py misclassifies builders
  that write `# STATE:` / `# ... IN-PROGRESS` header format instead of `[STATE]` brackets. Parse the
  WHOLE file for state markers, not just the first line; robust `re` snippet + empty-file crash-guard note.
- `references/fleet-idle-interpretation.md` — recognize a PARKED fleet: stale IN-PROGRESS/BLOCKED
  entries from a past cycle, no daemon processes, "awaiting directive" file content. CHECK process
  liveness + mtime age BEFORE alerting; a [BLOCKED] "no task assigned" is waiting, not crashing.
- `references/fleet-interpretation-runbook.md` — HOW to READ a ledger before reporting. KEY: monitor_fleet.py has no staleness threshold — if all STATUS_BUILDER mtimes cluster at one old age (~14d), the swarm is halted and ledger IN-PROGRESS/BLOCKED are frozen-file artifacts. Also: support services (gateway/free_router/turbocharger/eni_controller) can be UP while the builder fleet is DOWN — check STATUS mtimes, not those.
 - `references/liveness-probe-pitfalls.md` — concrete monitor-side cross-checks that bite every cron run: `pgrep -af STATUS_BUILDER` SELF-MATCHES the cron/wrapper shell line (filter with `ps … | grep -v bash -c`); builder filenames are ZERO-PADDED (`_01.md`..`_09.md`) so a naive `[ -f _$(i).md ]` loop fake-reports 1–9 missing; empty STATUS files are crash-guard-skipped so ledger lines < file count is normal; controller port set is 8420/8421/8422/8000 — 8080 is signal-cli, NOT the swarm.
