# Fleet monitor cross-check (cron: monitor_fleet.py)

When running `monitor_fleet.py` and interpreting the resulting `HEARTBEAT_LEDGER.md`,
the ledger's raw states are frequently MISLEADING. Cross-check disk state against
liveness before reporting "N builders are working".

## Pitfall 1 — never `cat` a control FIFO to inspect it
Control FIFOs live at `/tmp/eni_ctl_*`. They are named pipes, NOT regular files.
Reading one with no writer on the other end **blocks indefinitely** — a `cat` in a
`for` loop will hang until your shell timeout fires (observed: exit 124 after 180s),
silently stalling the whole probe loop.

**Right way to check a FIFO's presence** (non-blocking):
```bash
if [ -p /tmp/eni_ctl_BUILDER_37 ]; then echo "FIFO exists (no writer reading)"; fi
```
Use `[ -p path ]` / `ls -la path` (shows the `p` type flag) / `find /tmp -iname '*eni_ctl*'`.
Never open a FIFO for reading just to "check it". If you must read one, use
`timeout 1 cat /tmp/...` and expect it to either return data or time out — treat the
timeout as "no writer", not an error.

## Pitfall 2 — stale IN-PROGRESS / BLOCKED flags are false positives
Ledger rows read from status files can be days/weeks old. A builder whose file says
`[IN-PROGRESS]` is NOT necessarily working now. Verify freshness before trusting it:
```bash
date                                   # today
ls -lt builds/STATUS_BUILDER_*.md      # mtimes — any older than ~today = stale
find builds -name "STATUS_BUILDER_*.md" -newermt "$(date +%F)"   # touched today
```
Observed: 8 IN-PROGRESS + 1 BLOCKED flags all dated Jul 25–26 while today was Aug 7
→ the fleet was actually DORMANT. Count only builders with status files touched today
as genuinely alive; mark the rest as parked/stale.

## Pitfall 3 — 0-byte status files
`monitor_fleet.py`'s crash-guard drops empty status files, so `wc -l HEARTBEAT_LEDGER.md`
is usually 1+ FEWER than `ls builds/STATUS_BUILDER_*.md | wc -l`. Expected, not a bug.
Check `find builds -name 'STATUS_BUILDER_*.md' -size 0 | wc -l` to confirm the missing
row is the empty file and not a real gap.

## Reading liveness signals (when it IS active)
- Fresh (today) status file mtime + non-zero content = live builder.
- `ps aux | grep -iE 'builder|hermes'` — look for ACTUAL worker procs (note: odoo/postgres
  match the "demiurge" keyword as background services — don't mistake them for fleet workers).
- Fresh FIFO (mtime today) but NO matching worker proc = **staged but not dispatched**,
  not an active build. Candidate for a dispatch kick.
- All statuses stale + no procs + idle FIFOs = fleet dormant; report placeholder.

## Pitfall 4 — monitor_fleet.py only watches STATUS_BUILDER_*.md
`monitor_fleet.py` scans exactly one naming scheme: `builds/STATUS_BUILDER_NN.md`.
If the floor has been re-deployed under a DIFFERENT builder naming (observed: live
DEMIURGE/DEMIURGE3D floors with FIFOs `/tmp/eni_ctl_DEMIURGE_B01..B12` and
`/tmp/eni_ctl_DEMIURGE3D_B01..B12`, STATUS files `STATUS_DEMIURGE_B*.md` /
`STATUS_DEMIURGE3D_B*.md`), the monitor will NOT see them. It will report the old
mini-floor's rows (stale) and completely miss the actual active fleet — yielding a
false "dormant" read while work is really happening under another name.

**Before reporting dormancy, enumerate ALL floor namings on disk:**
```bash
# every distinct control-FIFO prefix tells you which floors are named
for f in /tmp/eni_ctl_*; do echo "${f##*/eni_ctl_}"; done | sed 's/_B[0-9]*$//' | sort -u
# all STATUS* naming schemes + their newest mtime (any recency = a live floor)
find /home/hunter/Commander -maxdepth 3 -name 'STATUS*.md' \
  -newermt 'today 00:00' -o -path '*eni_swarm/builds*' | head -40
```
A control FIFO whose prefix matches a naming scheme the monitor does NOT scan is your
signal to check that scheme's STATUS files for fresh activity before calling the
fleet dormant. "No fresh STATUS_BUILDER_* mtime" only proves THAT mini-floor is idle,
never the whole fleet.

## Reporting a dormant fleet
Lead with the headline ("fleet is DORMANT — no active builds"), then give the state
table (DONE/IN-PROGRESS/BLOCKED counts), flag that the nonzero states are stale, list
the genuinely-fresh signals (today's idle check-in, today's staged FIFOs), and end with
the actionable threads (issue directive to parked builder, route the staged subfleet).
