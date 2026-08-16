# Fleet cron report — canonical format

> **⚠️ NEVER `[SILENT]` A FLEET MONITOR RUN.** The fleet-status pulse IS the deliverable,
> not a freshness signal. A dormant/unchanged fleet is STILL a report to send — "nothing
> new" is itself the finding (it confirms the floor is parked/healthy and re-states what
> would wake it). The ONLY legit `[SILENT]` is if the monitor itself did not run or the
> job is not actually the fleet monitor. This rule OVERRIDES the cron runner's default
> "suppress on no-change" instinct. (See the full rationale in the footer of this file.)

Copy/adapt this shape for the daily fleet-status cron deliverable. It keeps
the report legible and SKIM-ABLE (LO watches it live on a monitor). Every
section earns its place; do NOT pad with a full ledger dump.

## Assembling sequence (do in this order)
1. `cd /home/hunter/Commander/eni_swarm && python3 monitor_fleet.py` — regen ledger. Exit 0 only means aggregation ran, NOT liveness.
2. `bash ~/.hermes/skills/devops/eni-swarm-telemetry/scripts/fleet_liveness_probe.sh /home/hunter/Commander/eni_swarm` — the freshness/proc cross-check that tells dormant from live.
3. Read the probe output, then write the report below.

## Report template
```
## 🐝 ENI Swarm Fleet Monitor — report

**Monitor monitor_fleet.py:** ✅ ran clean (exit 0), regenerated HEARTBEAT_LEDGER.md (N lines).

### Ledger state distribution (N status files on disk)
| State | Count | Builders |
|---|---|---|
| DONE | n | — |
| IN-PROGRESS | n | 5, 17, ... |
| BLOCKED | n | 46 |

### ⚠️ The real signal: fleet is DORMANT / PARTIALLY LIVE / LIVE
- Only N status file(s) touched in last 24h: (list, newest mtime). Use `fresh_last24h`, NOT `fresh_today` — on early-morning cron runs (e.g. 03:30) `today 00:00` excludes files touched yesterday evening, hiding the one genuinely-live heartbeat. Prefer the `-24h` window for the "marginal liveness" verdict.
- All others stale ~N days old (last touched YYYY-MM-DD)
- Live builder processes: NONE / list
- The IN-PROGRESS/BLOCKED rows are **stale relics, not live work** (unless mtimes prove otherwise)

**Verdict (per fleet_mtime_staleness.py pattern):** <state> — with only BUILDER_N marginally fresh.

### Other notes
- HEARTBEAT_ALERTS.md empty **or entirely absent** (missing file) → no forced BLOCKED; BUILDER_N's BLOCKED is leftover, not active alert. `monitor_fleet.py` guards with `os.path.exists(ALERTS_PATH)` so a missing alerts file is the normal parked-fleet state — do NOT flag it as an anomaly in the report; note "does not exist" plainly.
- Control FIFOs present for: (list) — no builder currently running against them.

### Bottom line
Fleet is <healthy-but-parked / building / stalled>. No crashes, no active stalls, just <idle awaiting directives>. Non-DONE rows are stale — do not read as live blockages. To wake: issue directive via <FIFO>.
```

## Pitfalls observed
- Tool-output compression: many reads (MASTER_STATUS.md, status_hub.cron.log, skills_list, big cats) return wrapped as `<ENI-COMPRESSED ... carrier=...png>` with only head/tail — NOT an error. Sidestep by emitting small/targeted output (counts, greps, sed ranges, per-builder `stat`). See `references/eni-compressed-output-wrapper.md` for recovery.
- The 8-10 IN-PROGRESS / 1 BLOCKED rows are the same parked set week over week when the fleet is dormant — ALWAYS verify with mtime/proc before reporting them as blockages.
- A regenerated ledger is NOT a sign of activity; only mtime freshness is.
- Output both the emoji header and the ⚠️ freshness block — that's the line LO actually reads.
- **Process-grep false positives:** a broad `ps aux | grep -iE 'builder_|stockbot|demiurge|lumen'` returns UNRELATED infra — avahi hostname `demiurge-linux.local`, odoo processes + their postgres connections with db names/users `demiurge` / `demiurge_mkt`. Those are NOT build workers. To assert "no live builders," confirm against real builder-writer signals (a hermes CLI proc on the fleet session, `swarm_turbocharger.py`, per-builder `/tmp/eni_ctl_*` FIFOs) — not the substring grep alone. Mention the grep hits and why they're ignored so a future reader isn't misled.
- **Masked exit code:** if you run monitor_fleet.py in a compound command ending in `cat HEARTBEAT_ALERTS.md`, the ABSENT alerts file makes `cat` return nonzero and the whole chain reports `exit_code=1` — falsely suggesting the monitor failed. Read monitor_fleet.py's exit on its own line (`python3 monitor_fleet.py; echo exit=$?`) to report "ran clean (exit 0)" accurately; the missing alerts file is normal parked state, not an error.
- Ledger line count can be LESS than the on-disk STATUS file count: `monitor_fleet.py` skips empty/0-byte files as a crash guard (e.g. `STATUS_BUILDER_20.md` is 0 bytes → 50 files on disk, 49 real ledger entries + 1 skipped). This is expected, not data loss — note it in the report rather than treating it as an anomaly. The probe reports DISK_STATUS_FILES and LEDGER_LINES separately for exactly this reason.
- **`wc -l` UNDERC0UNTS the ledger:** `monitor_fleet.py` writes `"\n".join(lines_out)` with NO trailing newline, so a 49-entry ledger reports `wc -l = 48`. Count with `grep -cE '^\['` (total) — or `awk '{print $1}' HEARTBEAT_LEDGER.md | sort | uniq -c` for the DONE/IN-PROGRESS/BLOCKED split + true line total in one command — NOT `wc -l`. A "48 ledger / 50 disk" pair means ONE 0-byte skipped, not two.
- **`IDLE` status files map to `[DONE]` in the ledger.** `monitor_fleet.py` only detects IN-PROGRESS and BLOCKED markers; an `IDLE` builder (e.g. a `— IDLE —` header) falls through to the final `else` branch and is recorded as `[DONE]`. So the single marginally-fresh file can read as DONE while the fleet is actually parked — the freshest file is often (counterintuitively) the live-one-to-wake, not finished throughput. Always trust mtime freshness over the ledger's DONE count to spot it.
- A fresh-today STATUS file ≠ doing work. The single freshest file can be IDLE/parked (e.g. BUILDER_37 touched 07:50 but body said "IDLE, awaiting LO directive, no FIFO"). So `fresh_today=1` on an otherwise-stale floor is STILL a DORMANT verdict — always read the freshest file's BODY (does it show an in-flight task/cycle, or is it parked awaiting a directive?) before upgrading the verdict to LIVE. One ticking file is not a live swarm.
- `status_hub.py` (runs every 5 min via crontab into `status_hub.cron.log` + `MASTER_STATUS.md`) continuously reports LARGE plateau counts: "598 minis (207 done / 388 in-progress / 3 blocked), 391 ALERTS". Do NOT let that log line drive the report — those 391 alerts and 3 blocked (ENI9_w3, DEMIURGE_GATE, SB_AVR) are the SAME stale Jul 9–12 relics across demiurge_scaffold, not live blockages. The fleet-monitor deliverable's verdict comes from the BUILDER_status mtime/proc cross-check, not the MASTER status-hub aggregate. Mention it as an informational note (the alert-rule spans all mini projects, so its counts overwhelm the builder floor) but never as a stall signal.
- **execute_code `terminal()` + f-string brace trap:** when building a shell command inside an f-string that itself contains regex braces (`{IN-PROGRESS|BLOCKED}`), Python interprets the braces as f-string format placeholders → `NameError: name 'IN' is not defined`. Fix: build the shell command OUTSIDE the f-string (plain string + `.format()`-free concatenation), or escape the braces as `{{...}}`, or run the grep via the real `terminal` tool instead of `execute_code`.
- **execute_code `terminal()` JSONDecodeError on large reads:** calling `terminal("tail -N <biglog>")` through the sandboxed `hermes_tools.terminal()` can come back as `JSONDecodeError: Expecting value` when stdout is large/noisy. Pull log tails with the standalone `tail`/`terminal` tool (foreground) or `read_file` instead of the execute_code wrapper; keep execute_code `terminal()` calls emitting small/filtered output.
- **Borderline-`fresh_last24h` verification:** when the newest STATUS mtime sits ~20–26h back, the probe may report `fresh_last24h=0` even though one file was touched "yesterday" — but that is a genuinely DORMANT verdict, NOT the early-morning `today 00:00` trap (that trap hides files touched *yesterday evening*; this one is genuinely >24h old). Before writing a fully-dead verdict, run `date '+%F %T %Z'` and compute the newest mtime's exact age so you can state it in the report (e.g. "BUILDER_37 last touched 24.5h ago") and don't overclaim LIVENESS from a file that just crossed out of the window.
- **Ledger line-count vs parsed-entry reconciliation (don't report data loss on the recount):** `wc -l HEARTBEAT_LEDGER.md` can read LOWER than the probe's parsed entry count because the final ledger line has no trailing newline. Example observed: disk=50, `wc -l`=48, but the probe's state distribution summed to 49 (40 DONE + 8 IN-PROGRESS + 1 BLOCKED) = the true entry count; the 1 missing-on-disk file was a 0-byte `STATUS_BUILDER_20.md` skipped by the empty-file crash guard (50 disk − 1 empty = 49 entries). Report the *parsed* entry count as authoritative and note the 0-byte skip explicitly; don't flag "48 lines vs 50 files" as a discrepancy.
- **Cron-mode deliverable semantics:** a DORMANT fleet is STILL a report to send — the fleet-status pulse IS the deliverable, not a freshness signal. Do NOT suppress with `[SILENT]` on a no-change run just because the verdict repeats last week's. The report's value is *confirming* the floor is parked/healthy and re-stating what would wake it; "nothing new" is itself the finding. Freshness only upgrades/downgrades the verdict word (DORMANT → PARTIALLY LIVE → LIVE) inside the report — it never makes the whole report skippable.

