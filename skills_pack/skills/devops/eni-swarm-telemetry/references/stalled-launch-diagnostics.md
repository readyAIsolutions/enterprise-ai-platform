# Stalled-launch & false-alive diagnostics (heartbeat session 2026-08-07)

The runbook's mtime+proc+FIFO cross-check is the baseline. This file adds the two
"false positive / false negative" signatures that tripped up a real heartbeat run,
plus the exact commands to confirm them. Use these when the ledger looks live (fresh
mtimes / logs) but `ps` shows no workers — and vice-versa.

## Signature A — fresh-mtime status file with an IDLE token is a SELF-PROBE, NOT a live builder

Observed: `builds/STATUS_BUILDER_37.md` had today's mtime (12:37) while all 49 other
status files were 12+ days old. A naive mtime check flags it "live today." But the
token said `IDLE` and the body read like an empirical self-check:

```
# STATUS_BUILDER_37 — IDLE — Fri Aug 7 12:37 MDT 2026
Control FIFO /tmp/eni_ctl_BUILDER_37 does not exist (re-verified empirically...
No directive issued to BUILDER_37.
```

Rule: **a fresh mtime is not liveness by itself.** A genuinely live builder carries an
`[IN-PROGRESS]` or `[BLOCKED]` token from a build. An `IDLE` token with "no directive /
awaiting FIFO" text means something probed the floor (a watchdog / status_hub / outer
agent checking the workspace) but did NOT dispatch work. Report it as "floor probed,
idle, awaiting directive" — not as an active builder.

Confirmation command:
```bash
stat -c '%y %n' builds/STATUS_BUILDER_*.md | grep "$(date +%F)"   # today-mtime files
```
Then read the token line of any hit before claiming it's live.

## Signature B — a big batch of today-mtime `*_B*.log` files with ZERO worker procs = launch that opened then exited

Observed: 49 logs (`/tmp/{eni_,}[STOCKBOT|DEMIURGE|DEMIURGE3D]_B01..B12.log`) all stamped
06:16 today, but `ps` showed **no** `hermes chat`/worker procs and nothing written to
those logs for 7.5h. This is a **stalled launch**: the build swarm was kicked off, the
hermes PTY sessions opened (logs end at the interactive banner + model prompt), then
the processes exited before issuing any build directive. The logs look like activity
but the floor did no work.

Confirmation commands:
```bash
find /tmp -maxdepth 1 -name '*.log' -newermt "$(date +%F) 00:00" | wc -l   # fresh logs
ps aux | grep -E "python.*(chat|worker|mini|builder)" | grep -v grep        # expect ZERO besides infra
find /tmp -maxdepth 1 -name '*.log' -newermt "$(date +%F) 06:16:00"        # empty = frozen since launch
```
A frozen log tail ends at the PTY banner / hermes prompt (⟡ ⚕ model │ ctx … │ ❯),
not at a completed-phase line. Same tell as Signature A: **launch ≠ liveness.**

## Signature C — a gap in the ledger row count is a BLANK status file, not necessarily a missing builder

`monitor_fleet.py` has a crash-guard: it silently **skips any STATUS file that is blank** (no
non-whitespace content). Those builders simply never appear in `HEARTBEAT_LEDGER.md`. So an
unexplained row gap (e.g. ledger goes BUILDER_19 then jumps to BUILDER_21) is usually a blank
file — NOT a vanished/never-launched builder.

Confirmation:
```bash
# find zero-byte / blank status files
find builds -name 'STATUS_BUILDER_*.md' -size 0
ls -la builds/STATUS_BUILDER_20.md   # non-zero size may still be all-whitespace; eyeball it
```
When reporting ledger counts, note the disk-vs-ledger mismatch rather than flagging a
"missing builder." A builder genuinely absent from disk (no file at all) is a different,
stronger signal than a blank one.

## Infra vs worker proc census (so you don't miscount "workers")

⚠️ **Don't grep `worker` broadly** — `ps aux | grep -i worker` matches kernel `[kworker/…]`
threads (there are dozens of them) and floods the output, drowning the real signal and
making it look like the machine is busy. Always anchor on the actual python binaries /
process names. A clean liveness census for the swarm floor:
```bash
ps aux | grep -iE 'python.*(chat|worker|mini|builder|eni_controller|eni_kb|turbocharger|free_router|claude_cli_proxy|airllm)' | grep -v grep
```
If you want infra vs builders separately, split into two greps: infra names (below) vs
`python.*(chat|worker|mini|builder)`.

These are ALWAYS present and are NOT builders — subtract them when counting:
`eni_controller` (port 8940), `eni_kb_daemon`, `swarm_turbocharger`, `free_router`,
`claude_cli_proxy`, `airllm_server.py` (local model server), `pyright-langserver`.
A leftover `/tmp/eni_ctl_BUILDER_N` FIFO with no matching proc is a dead pipe, not a worker.

## Signature D — clean exit + CORRECT ledger + ENTIRE fleet stale = monitor healthy, fleet dormant (kick, don't fix the monitor)

Observed 2026-08-13: `python3 monitor_fleet.py` exited 0 and regenerated a well-formed
`HEARTBEAT_LEDGER.md` (49 rows, correct state parsing, sorted), while EVERY
`builds/STATUS_BUILDER_*.md` was 2+ weeks old (Jul 25–26) and the 8 IN-PROGRESS / 1 BLOCKED
rows were that same old dispatch with nothing progressed since. A naive reading says "monitor
is broken / stuck" — but the monitor did its job perfectly; it faithfully reports that the
fleet hasn't received a dispatch in weeks.

Rule: **a stale fleet on a clean monitor is a dispatch problem, not a telemetry problem.**
Before touching the monitor, confirm it's healthy: (1) exit code 0, (2) ledger rows match
disk (use `grep -c "BUILDER_"`, not `wc -l`), (3) state tokens parsed correctly. If all three
hold and every status file is old, the correct verdict is "monitor healthy; swarm dormant /
needs a kick (PRODUCT_LEAD routing or FIFO directive)" — do NOT "fix" the monitor.
An absent `HEARTBEAT_ALERTS.md` (no blocked-builder override list) plus old status files is
consistent with silent dormancy, not a monitor fault.

## Bottom-line phrasing for a quiet fleet
If ledger rows are mostly `[DONE]` from an old run, non-DONE files are days-old artifacts,
no alerts file, no worker procs, and any today-mtime hits resolve to Signatures A/B →
report "fleet quiescent / settled, floor awaiting directive" — no alert.