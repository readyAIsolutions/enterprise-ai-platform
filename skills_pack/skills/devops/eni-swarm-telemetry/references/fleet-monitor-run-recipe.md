# Verified run recipe for the fleet monitor / heartbeat (cron)

## 0. TWO DISTINCT FLEET-STATUS SCOPES — do not conflate their counts
This box has TWO separate fleet-status aggregations with different scopes,
inputs, output files, and builder counts. When LO asks for "fleet status" /
"how many builders" / a heartbeat pulse, state which scope you mean:

| | monitor_fleet.py | status_hub.py (worker w2) |
|---|---|---|
| Input | `builds/STATUS_BUILDER_*.md` only | ALL `STATUS_ENI*.md` + every project `STATUS_*` (recursive) |
| Output | `HEARTBEAT_LEDGER.md` | `MASTER_STATUS.md` |
| Scope | ~49-50 builders | ~77+ minis (ENI + STOCKBOT/DEMIURGE/DEMIURGE3D/LUMEN) |
| Row shape | `[STATE] BUILDER_N` | tabular per-mini with last-update/age/alert |

The `status_hub.cron.log` line "77 minis (…)" and the ledger's "49 builders"
are DIFFERENT views — not a contradiction or data loss. `status_hub.py` is the
"eyes of the master" consolidation; `monitor_fleet.py` is the builder-floor pulse.
Do not report one as a regression of the other.

## 1. Regenerate the ledger (always exit 0 = aggregation ran, NOT liveness)
```bash
cd /home/hunter/Commander/eni_swarm && python3 monitor_fleet.py
```
NOTE: must be `python3` — bare `python` is NOT on PATH on this box (cron env),
so a `python: command not found` exit 127 is the expected symptom if something
calls it as `python`. Always invoke as `python3`.
Writes `HEARTBEAT_LEDGER.md` from `builds/STATUS_BUILDER_*.md`. Crash-guard skips
empty files (e.g. `STATUS_BUILDER_20.md` = 0 bytes → absent from ledger). That is
expected, not an error.

### Expected ledger-row deficit vs status-file count — do NOT call it data loss
The ledger has one row per non-empty status file, so `ls builds/STATUS_BUILDER_*.md | wc -l`
(will often be 50) is typically ONE MORE than `wc -l < HEARTBEAT_LEDGER.md` (49) whenever a
builder file is 0 bytes (here: `BUILDER_20`). A row-count that equals file-count-minus-one is
is NORMAL, not a missing builder. Before reporting "builder N lost", confirm WHICH number is
absent via a range loop. **CRITICAL: the status files are ZERO-PADDED**
(`STATUS_BUILDER_01.md`, not `STATUS_BUILDER_1.md`), so the missing-builder check MUST use
`seq -w` (leading-zero) padding to match filenames, or it will FALSE-POSITIVE on every
single-digit builder:
```bash
for i in $(seq -w 1 50); do [ -s builds/STATUS_BUILDER_$i.md ] || echo missing BUILDER_$i; done
```
(`-s` = exists AND non-empty). An UN-padded `seq 1 50` loop reports BUILDER_1–9 as
"empty/missing" even when they're present — a false alarm, not a real gap. Only a number
absent from BOTH file-list and ledger is a real gap. Verify a specific file with
`[ -s builds/STATUS_BUILDER_01.md ]` (padded) and `ls` it directly before flagging data loss.

## 2. Liveness probe — ON-DISK PATH INCLUDES THE devops/ CATEGORY DIR
Do NOT guess `~/.hermes/skills/eni-swarm-telemetry/...` (does not exist).
The real path on this box is:
```bash
bash /home/hunter/.hermes/skills/devops/eni-swarm-telemetry/scripts/fleet_liveness_probe.sh /home/hunter/Commander/eni_swarm
```
Pass the swarm dir as `$1` (the probe guards against running from the wrong cwd,
which would otherwise return an all-zero "fleet dead" FALSE ALARM).

### Robust general rule (applies to ANY skill's support scripts)
Skill scripts that are category-homed (this one under `devops/`) live at
`~/.hermes/skills/<category>/<skill>/scripts/`. Never guess — locate with:
```bash
find /home/hunter -name fleet_liveness_probe.sh   # or the script you need
```

## 3. Interpret (see fleet-interpretation-runbook.md)
In a quiescent fleet the ledger's `[IN-PROGRESS]` / `[BLOCKED]` rows are STALE
markers (old mtimes), NOT live builds. Cross-check the probe's freshness block:
`fresh_today`, newest mtimes, and `live builder processes`. Only report "builders
working" when status files are fresh (< stall window) AND a builder proc is alive.
An idle/parked fleet (all mtimes weeks old, no procs, 1 fresh IDLE self-check) is
expected between campaign runs — report it as quiescent, not as a fire.

## 4. Pitfall: monitor maps IDLE → [DONE] (parked builders inflate the DONE count)
`monitor_fleet.py` has no IDLE branch: its parser collapses every non-BLOCKED and
non-IN-PROGRESS state to `DONE`. So a builder whose status file explicitly reads
"IDLE — no directive, do not invent work" (e.g. BUILDER_37, Aug 08 12:46) lands in
the ledger as `[DONE]`. Do NOT read every `[DONE]` row as completed work — a parked
builder waiting on its `/tmp/eni_ctl_BUILDER_<n>` FIFO also shows up there. To tell
real completions from parked/idle: grep the fresh builder's status file for `IDLE`
before trusting a DONE entry, and cross-check mtimes. A single fresh `[DONE]` row
that is actually an IDLE self-check means the fleet is quiescent, not productive.

## 5. Ledger counts can truncate under ENI-COMPRESSED reads
Reading `HEARTBEAT_LEDGER.md` via `read_file` may return an ENI-COMPRESSED carrier
with a truncated head, so naive regex counting will report a wrong total (e.g. 49
rows parsed as 41). Get exact counts with `terminal: cat HEARTBEAT_LEDGER.md` and
count line-by-line, or grep the raw file — do the aggregation in shell, not by
parsing a possibly-truncated read_file snapshot.

## 6. Pitfall: `wc -l < HEARTBEAT_LEDGER.md` can be one SHORT of the true row count
`monitor_fleet.py` writes rows joined by `\n` with NO trailing newline on the last line,
so a 49-row ledger shows `wc -l` = 48 (49 newlines vs 48). This is NOT a dropped builder.
When reconciling ledger vs disk: compare the SET of ledger builder numbers (via
`grep -oE 'BUILDER_[0-9]+' HEARTBEAT_LEDGER.md | sort -u`) to the set of non-empty disk
files, not raw `wc -l`. ### Zero-padding gotcha when reconciling by name (verified Aug 2026)

Disk filenames are zero-padded (`STATUS_BUILDER_01.md` … `STATUS_BUILDER_50.md`) but the
ledger writes **unpadded** names (`BUILDER_1` … `BUILDER_50`). So a naive name comparison —
`grep -oE 'BUILDER_[0-9]+' builds/STATUS_BUILDER_*.md | sort -u | comm -13 <(grep -oE 'BUILDER_[0-9]+' HEARTBEAT_LEDGER.md | sort -u) -` — reports `BUILDER_01`..`BUILDER_09` as "missing from ledger" even though they ARE present as `BUILDER_1`..`BUILDER_9`. This is a false alarm, NOT data loss.

**To reconcile correctly, normalize both sides to the same padding before comparing** — e.g. strip the file two-digit pad:
```bash
cd /home/hunter/Commander/eni_swarm
disk=$(ls builds/STATUS_BUILDER_*.md | sed -E 's/.*STATUS_BUILDER_0*([0-9]+)\.md/BUILDER_\1/' | sort -u)
led=$(grep -oE 'BUILDER_[0-9]+' HEARTBEAT_LEDGER.md | sort -u)
comm -13 <(printf '%s\n' "$led") <(printf '%s\n' "$disk")   # genuinely missing (0-byte files)
```
The only real gap is zero-byte files (skipped by the crash-guard) — a 0-byte `STATUS_BUILDER_20.md` correctly absent from the ledger is expected, not an error. Never call the padding artifact "data loss."

If the sets match exactly, the ledger is complete — trust the
set-membership check over a raw line count. (This is the zero-padded .md follow-on to the
truncation caveat in sec. 5 — always reconcile by name, never by line/byte count.)

### Parser state-collapse gotcha: IDLE → [DONE] (verified 2026-08)
`monitor_fleet.py` has THREE mapped states only: DONE / IN-PROGRESS / BLOCKED. It
explicitly tests for IN-PROGRESS and BLOCKED; **everything else — including a freshly
written explicit `IDLE` status — collapses to `[DONE]`.** So a `[DONE]` ledger row does
NOT mean "builder finished work." It can mean "builder explicitly parked / awaiting a
directive." This is a real misread risk on the heartbeat: a genuinely active-but-idle
builder (fresh mtime, `IDLE` in body) shows as `[DONE]`, which at a glance looks like
completion rather than dormancy.
Rule when reporting fleet status: if the freshest status file's body says `IDLE` but the
ledger row reads `[DONE]`, report IDLE — trust the status-file body over the ledger label.
"Fleet is idle/parked" and "fleet completed work" are different states; don't let the
parser's DONE default conflate them.

### Reconcile-by-name shell gotcha (verified 2026-08)
A naive `for f in builds/STATUS_BUILDER_*.md; do n=${f####*/}; grep -q "${n#STATUS_BUILDER_}" ...`
lookup FAILS on zero-padded names: `${n#STATUS_BUILDER_}` strips the prefix leaving `01`,
but the ledger row says `BUILDER_1` (no zero pad), so EVERY file falsely reports MISSING.
Reconcile by the rounded number, or strip the prefix AND the zero pad:
```bash
for f in $SWARM_DIR/builds/STATUS_BUILDER_*.md; do
  num=$(basename "$f" | sed -E 's/^STATUS_BUILDER_0*//; s/\.md$//')
  grep -qE "BUILDER_${num} " "$LEDGER" || echo "MISSING: $(basename "$f") ($(stat -c%s "$f") bytes)"
done
```
Expected MISSING = only 0-byte files (crash-guard skip). Any non-zero file missing is a real gap.

## Invocation + what "success" means
- Run the monitor with **`python3 monitor_fleet.py`** — the `python` alias is NOT on PATH in this shell (system only ships `python3`). Using `python` yields `python: command not found` and the ledger is NOT rewritten. The crontab itself uses `python3 -W ignore status_hub.py`, confirming python3 is the interpreter of record.
- The script only rewrites `HEARTBEAT_LEDGER.md` from `builds/STATUS_BUILDER_*.md`; it is **report-only** — it never edits STATUS files, dispatches tasks, or spins up builders. Treat any claimed "action" beyond writing the ledger as a red flag.
- Ledger state rows (DONE / IN-PROGRESS / BLOCKED) are **stale STATUS-file snapshots**, not live activity. The authoritative freshness check is the mtime cross-check in section above: when all/most STATUS mtimes share one old "parking date" (e.g. all Jul-25 except one daily-touch IDLE builder like `STATUS_BUILDER_37.md`), the fleet is DORMANT regardless of the IN-PROGRESS/BLOCKED row counts. A 0-byte STATUS file (e.g. `STATUS_BUILDER_20.md`) is silently dropped by the crash guard → ledger rows < file count is expected, not a lost worker.

## PITFALL: don't hand-roll a fresh regex to "reclassify" the fleet
When characterizing fleet state, it is tempting to write an ad-hoc loop that
re-parses every STATUS file into state buckets (DONE/IN-PROGRESS/BLOCKED/IDLE).
Status files use many mutually-incompatible token forms (`[IDLE]`, `[READY]`,
`# ... — IDLE —`, `[IN-PROGRESS]`, "checking in", plain `[BLOCKED]`, ...), so a
hand-rolled matcher almost always lands a wall of `UNKNOWN` (observed: 34/50 UNKNOWN
on a genuinely idle fleet) and over-counts "non-DONE" rows as if they were activity.
That UNKNOWN-heavy tally is a parsing artifact, NOT a fleet problem.
**Correct approach (verified 2026-08-10):** don't reclassify — (1) use the scripts
in this skill (`fleet_liveness_probe.sh` / `heartbeat.py`) as primary source,
(2) mtime-cross-check to find the real freshness (one clustered old date + one fresh
file = dormant), and (3) actually read that single fresh file's token (IDLE → parked,
not building). Report those, not your regex counts.

## 4. CRON DISPATCH FRAME ≠ ASSIGNMENT — do not invent work (verified 2026-08-10)
A monitor/heartbeat cron fires every cycle with a DEFAULT GOAL STRING baked into its
dispatch frame. That string is a **scheduling template, NOT a task assignment** — no
directive has been routed to any builder unless a real control FIFO
(`/tmp/eni_ctl_BUILDER_*`) actually exists and carries an instruction. When the fleet
is dormant, the correct verdict is **IDLE / parked-and-healthy**, and the agent must
NOT fabricate work, re-dispatch builders, or "opportunistically" start building just
because a cron fired. This is exactly what BUILDER_37's own status states verbatim:
"cron dispatch frame is a scheduling template, not an assignment — goal string is a
default, not a task. IDLE — do not invent work." Respect it. If LO wants builds, a real
directive must arrive via FIFO/chat; a bare monitor tick is never that signal.
