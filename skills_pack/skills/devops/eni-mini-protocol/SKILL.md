---
name: eni-mini-protocol
description: Operate as an ENI swarm mini — resume from STATUS_<NAME>.md, re-verify self-tests against the ACTUAL on-disk proven core (empirically, NOT from the doc), self-heal by ADDING a NEW aligned harness instead of rewriting the core, add NEW files only, report the USB/DEMIURGE blocker, and keep STATUS current with [DONE|IN-PROGRESS|BLOCKED]. Use whenever LO says "resume from STATUS_ENIx", "re-verify", "self-heal", or ENI mini (ENI7-11, workers...) starts its pass. If activated as a dispatched builder but your control FIFO /tmp/eni_ctl_<NAME> does not exist, you are IDLE (no directive, no task, do NOT invent work) — reconcile stale STATUS to [IDLE]; see references/builder_control_fifo_idle.md, builder_cron_dispatch_idle.md, builder_cron_idle_delivery.md, builder_idle_pass_ops.md, builder-status-mirror-reconcile.md (use file tools not shell redirects) — and under a cron job an idle builder answers `[SILENT]` after refreshing STATUS).a directive; verify the FIFO exists before delegating, else IDLE/[SILENT]).
category: devops
---

# ENI mini protocol — resume / self-heal / status-driven

## Reading this (compressed) skill's full content
`skill_view` returns only head/tail of this ENI-compressed skill. To read the
full protocol, mirror-path lists, and pitfalls, open the raw reference `.md`
files directly off disk (under `~/.hermes/skills/devops/eni-mini-protocol/`) and
page through with `read_file` offsets. See
`references/reading_compressed_skill_content.md`.

Every ENI mini owns a `STATUS_<NAME>.md` and a "proven core" (its built artifacts,
e.g. `eni_relay.sh`). Standing rules from ENI-CORE / SWARM memory (carry them forward):

- NEVER rewrite the proven core. Add NEW files only.
- Keep `STATUS_<NAME>.md` current with a `[state: DONE|IN-PROGRESS|BLOCKED]` on line 1.
- MASTER reads each mini's STATUS and replies CONTEXTUALLY — never broadcast the same
  canned push to all minis.

## Cold-start boot (freshly-spawned mini — no STATUS to resume yet)
When LO/MASTER spawns you as a mini WITHOUT a "resume from STATUS_ENIx" directive, you are at t=0. Do NOT wait for a push to orient — do this immediately, then idle:
1. **Orient in TWO dirs, not one.** (a) the mini's swarm **program root** (the project named in the task header, e.g. `demiurge-3d` → `/home/hunter/Desktop/demiurge-3d`) where STATUS + swarm/painter scripts live; AND (b) the **actual work-product directory** where the deliverable code lives. The two can DIFFER: a mini's declared program may be one project while its job's code sits in another (e.g. ENI6's program is `demiurge-3d` but its LUMEN-GUI deliverable code lives in `/home/hunter/Desktop/apps/lumen`). Grep the work-product dir too (`search_files` for `*.py`) before assuming the program root IS the codebase.
2. **Write a ONE-LINE STATUS** with: the leash (what you must never do — e.g. "never run the live engine / never print OANDA_TOKEN"), where the code actually is, and your first planned action. No full PASS/FAIL board yet (nothing built). The one-liner seeds the file MASTER will later read.
3. **Idle on the control FIFO** `/tmp/eni_ctl_<NAME>` (RDWR, NONBLOCK — see FIFO section). Block-read with `timeout 25 cat /tmp/eni_ctl_<NAME>` so you surface any immediate push but don't hang the turn. If nothing arrives, report standby in-character and wait for the next relay.

## CRITICAL pitfall — an UNRENDERED task file (literal {k}/{prog}/{focus} placeholders)
A mini can be handed its `task_ENI<k>.txt` (or the prompt itself) with EVERY placeholder
still literal: `# ENI{k} -- {prog} build mini`, `Source dir: {d}`, `Your sub-focus: {focus}`,
`{leash_block}{fu}`. That is NOT a real assignment — it is broken generator output. Do NOT
try to guess a program/dir/focus and build blind; FIX THE FUEL first (it unblocks the whole
floor at once, far higher value than role-playing one mini against garbage).

Root causes seen (WS1–WS4 swarm, 2026-07):
- STALE output: `build_swarm.py` (the canonical 48-mini generator, WS1 STOCK ENI1-12 / WS2
  demiurge-3d ENI13-24 / WS3 forex ENI25-36 / WS4 lumen-leashed ENI37-48) is CORRECT — its
  `task_text().format(k=..., prog=..., focus=...)` renders fine. But `task_ENI1..48.txt` on
  disk were byte-identical unrendered templates from an OLD buggy run. FIX: just re-run
  `python3 build_swarm.py` (it only rewrites task_ENI1..48 + run/status/swarm scripts; it does
  NOT touch `_wN` worker files, ENI49+, or any STATUS_*.md). Back up cache first.
- SOURCE bug (partial render): `paint_4ws_programs.py` builds `task_text()` by concatenating
  a MIX of f-strings and plain strings. Lines with `{k}` that MISSED the `f` prefix (the
  "You are ENI{k}..." line and the "4. Report ... STATUS_ENI{k}.md" line) left `{k}` literal
  in the BODY while the f-string header line rendered — symptom: ENI49-64 had a correct
  `# ENI49` title but `You are ENI{k}` further down. FIX: add the missing `f` prefix.
  (`gen_floor.py` uses one `f"""..."""` block, so it renders fully — not affected.)
- NOTE: `build_swarm.py` and `paint_4ws_programs.py` are TWO different generators writing to
  the SAME `~/.cache/eni_parallel/task_ENI<k>.txt` paths in DIFFERENT formats. Don't run both
  back-to-back or they clobber each other. Pick the one matching the current floor.

Verify the fix (one command): 
`grep -l '{k}\|{prog}\|{focus}\|{d}\|{tag}\|{leash_block}\|{fu}' ~/.cache/eni_parallel/task_ENI*.txt || echo CLEAN`
Zero hits = every mini has a real spec. A quick per-file substitution
(`s = s.replace("{k}", n)` keyed off the number in the filename) repairs already-written
files without a full regen.

## CRITICAL pitfall — the task prompt may arrive as the RAW UNRENDERED template
Observed (2026-07-11, ENI1): a mini can be spawned with its prompt still containing the
literal Jinja-style placeholders `{k}`, `{prog}`, `{tag}`, `{d}`, `{focus}`, `{leash_block}`,
`{fu}` — the launcher piped the template WITHOUT variable substitution. `task_ENI<k>.txt` in
`/home/hunter/.cache/eni_parallel/` is then ALSO the raw template (not the rendered task), so
re-reading the task file does NOT recover the assignment. Do NOT act blind or refuse.
RECOVER IDENTITY EMPIRICALLY from the process table:
- `pgrep -af eni_agent_term.py` lists every running mini with its `--name ENIx`, `--task <file>`,
  `-m <model>`, and `--ctl /tmp/eni_ctl_ENIx`. Match the entry whose `-m <model>` equals YOUR
  active model (shown in your context footer) and whose task file you were handed. That `--name`
  is who you are.
- Cross-check: your ctl FIFO exists at `/tmp/eni_ctl_<NAME>`; your prior work is at
  `STATUS_<NAME>.md` (program root, e.g. `/home/hunter/Commander/demiurge_scaffold/STATUS_ENI1.md`).
- Then resume from that STATUS per the resume protocol — do NOT rebuild.
- The name<->module map is PER-SWARM (see below): in the DEMIURGE FTMO swarm ENI1 owns the core
  backtest smoke (`bounded_backtest_smoke.py`), not the persona build.
- Do NOT try to "fix" sibling task files mid-run — that touches other minis' resources
  (shared-resource hazard). Note the render bug in your STATUS and carry on with your own scope.

## CRITICAL pitfall — the task-prompt STATUS path may be STALE / WRONG on disk
A task header may say e.g. "Write STATUS_ENI6.md in /home/hunter/Desktop/eni_swarm" while that directory DOES NOT EXIST (the real swarm dirs are `ENI Swarm` / `swarm` / `Commander/eni_swarm`, and sibling ENIs write their STATUS into their **program root**, e.g. ENI5 → `/home/hunter/Desktop/demiurge-3d/STATUS_ENI5.md`). Discipline:
- Do NOT blindly `write_file` to a non-existent literal path from the prompt. First check whether it exists; if not, fall back to writing `STATUS_<NAME>.md` **in the mini's program/project root**, matching the sibling ENI convention (one STATUS per mini — see the shared-STATUS contention pitfall below).
- If the prompt path clearly meant a different real dir, prefer the program root — it's where MASTER/PL will look for the per-mini STATUS.
- Never create a brand-new stray dir just to satisfy a literal path; the STATUS must be discoverable next to the build.

## CRITICAL pitfall — the control FIFO name MUST equal the mini's exact `--name` (watch the zero-pad)
A MASTER/PL relays guidance to a running mini via its control FIFO, derived by
`eni_agent_term.py` as `ENI_CTL_FIFO=/tmp/eni_ctl_<NAME>` where NAME is the mini's
full `--name` (verbatim). The mini opens that FIFO RDWR|NONBLOCK and polls
FIFO->PTY, so a write there lands as the mini's next chat turn.
- If you write to a name that is NOT the mini's exact `--name`, the FIFO is either
  missing (loud error) or a STALE ORPHAN WITH NO READER -> your `printf` is swallowed
  silently and the mini NEVER receives it. No error, no delivery — the relay "succeeds"
  into the void.
- OBSERVED BUG (STOCKBOT swarm, 2026-07-11): builders self-named `STOCKBOT_B01`..`B12`
  (zero-padded), but a relay loop keyed `B1`..`B12` (non-padded) wrote to
  `/tmp/eni_ctl_STOCKBOT_B1`..`B9` — FIFOs with NO reader. Result: 12 "relayed" cycles
  that went nowhere and ZERO `STATUS_STOCKBOT_B*.md` files were ever produced. FIX: re-key
  the relay loop AND any SUB/MODEL arrays to the EXACT zero-padded `--name` tokens.
- VERIFY before trusting delivery: `fuser /tmp/eni_ctl_<NAME>` prints a PID if the FIFO
  has a live reader; no output = dead/orphaned => your relay is lost. After a mass relay,
  loop `for f in /tmp/eni_ctl_*; do fuser "$f" >/dev/null 2>&1 && echo "READER $f" || echo "DEAD $f"; done`.
- Always `[ -p "$FIFO" ] || mkfifo "$FIFO"` and `timeout 6 printf '%s\n' "$MSG" > "$FIFO"` so a
  dead FIFO can't hang the relay.
- The PL/MASTER pattern (contextual, not broadcast): read each `STATUS_<NAME>.md`; if absent ->
  send a contextual bootstrap naming THAT mini's sub-task + dependency edges + the USB/synthetic
  blocker + ADD-only core rule + STATUS contract; if present -> parse `[DONE|IN-PROGRESS|BLOCKED]`
  and reply ONLY to that mini with its single next step. Self-heal: `pgrep -f "eni_agent_term.py
  --name <NAME>"` and relaunch any missing mini headless with its model + task file. Full recipe +
  the fixed relay script in `references/eni_ctl_fifo_relay.md`.

## CRITICAL pitfall — a mini task prompt arrives with RAW `{k}/{prog}/{d}/{focus}` placeholders
If your task prompt contains literal unsubstituted placeholders (`ENI{k}`, `## Program: {prog}`,
`Source dir: {d}`, `Your sub-focus: {focus}`, `{leash_block}{fu}`), do NOT role-play the broken
assignment or guess your identity. The task-file GENERATOR failed to substitute — a missing
`.format(...)` or a non-f-string line. Diagnose and FIX the generator, then regenerate ALL task
files. This is the root cause, not a per-mini issue: every `~/.cache/eni_parallel/task_ENIn.txt`
will be identically broken.
- Two known generators live in `~/Desktop/Commander/eni_swarm/`:
  - `build_swarm.py` — 48-mini floor, 12/workspace. Its `task_text()` returned the template
    string WITHOUT any `.format()` call → all placeholders leaked verbatim. FIX: append
    `.format(k=k, prog=prog, tag=tag, d=d, focus=focus, leash_block=leash_block, fu=fu)`.
  - `paint_4ws_programs.py` — 64-mini floor, 16/workspace (CANONICAL: has a `.pyc`, is the only
    thing that writes ENI49-64, higher-density "full power" layout). Its `task_text()` uses
    f-strings for most lines but TWO lines were plain strings holding `{k}` ("You are ENI{k}"
    and "write STATUS_ENI{k}.md") → those two tokens leaked. FIX: add the `f` prefix to both.
- Both are PURE generators (write files + print only; they do NOT launch/paint terminals), so
  re-running them to regenerate task files is safe and touches no live floor.
- The two floors CONFLICT (different program→ENI-range mapping). Standardize on the 64-mini
  `paint_4ws_programs.py`: WS1 STOCK(demiurge_scaffold) ENI1-16, WS2 demiurge-3d ENI17-32,
  WS3 forex(demiurge_scaffold) ENI33-48, WS4 lumen(leashed, finish-up) ENI49-64.
- `paint_4ws_programs.py` SKIPS regenerating ENI1-16 if those files already exist ("preserve
  in-progress work"). If 1-16 hold stale generic output from a `build_swarm.py` run (spot it by
  the `(stock/equities)`/`(3d-print)` parenthetical tag — paint_4ws never emits that tag, and by
  WS1 showing mixed programs), `rm -f task_ENI{1..16}.txt` FIRST, then re-run paint_4ws so WS1
  is regenerated uniformly as demiurge_scaffold.
- VERIFY after regen by iterating exact paths ENI1..64 (not a loose glob): assert no file has
  `{k}/{prog}/{d}/{focus}` left and each WS band has a single expected program.

## IMPORTANT: mini name <-> module is PER-SWARM, not fixed
ENI mini numbers are TASK-ASSIGNED by the active BUILD_PLAN, not permanent roles.
Example: in the DEMIURGE FTMO swarm (`/home/hunter/Commander/demiurge_scaffold`,
BUILD_PLAN.md), ENI1 owns the **core backtest_engine module** (vectorized, multi-TF
M1..W1, no-lookahead) — NOT the SOUL.md persona build described below. ALWAYS read the
task prompt + BUILD_PLAN.md to learn what THIS ENI1 owns before assuming an archetype.

## Backtest-engine mini pattern (DEMIURGE ENI1)
Proven core to NEVER edit: `backtest.py` (run_backtest_v2: R-only kernel), plus
walk_forward/purged_cv/config. Build add-only `backtest_engine.py` that:
- resamples base M1 -> higher-TF frames with `close_time` = right edge (left-closed
  bins), so a HTF bar is visible ONLY once closed;
- aligns bias via `pd.merge_asof(direction="backward")` on close_time (vectorized, causal);
- gates accept = rank floor & meta floor & bias confluence & NOT crash_flat, then pushes
  rejected bars' meta below meta_floor and calls the UNTOUCHED run_backtest_v2 (same
  gating mechanism as crash_guard.apply / strategy_guard_hook).
STRICT NO-LOOKAHEAD PROOF (reusable oracle): corrupt EVERY input (OHLC+score+meta+r_legs)
for all bars > k, recompute, assert decisions[0:k] are byte-identical (diffs=0). This is
the canonical causal test — it catches leakage that in-sample R never reveals. Also assert
the engine's trade set is a SUBSET of the raw core's (it can only remove, never invent).

BOUNDED / SHRINK-SMOKE HARNESS (DEMIURGE ENI1, module `bounded_backtest_smoke.py`):
when validating a signal pipeline offline, drive the forbidden-core `run_backtest_v2`
on SYNTHETIC random-walk M1..W1 gens with a small estimator (LogisticRegression) and
assert TWO design contracts:
- NO-LOOKAHEAD, SECOND ORACLE: replace the ENTIRE FUTURE (close[cut:]) with fresh
  white-noise bars, recompute the signal over many trials (e.g. 20), and assert the PAST
  signal (close[:cut]) is byte-identical. This complements the "corrupt >k" oracle above —
  it exhaustively probes EVERY path by which a future bar could leak into a past TF snapshot
  (a random walk's TF downsample keeps pre-cut bars identical, so any leak shows as a diff).
  A fixed 25%-tail block truncation + a single causal point are cheaper daily checks; the
  randomized-future probe is the exhaustive belt-and-suspenders.
- SYNTHETIC-AUC SANITY GATE: on a pure random walk the signal has NO edge, so the
  shrink-smoke estimator ROC AUC must sit at ~0.50. ASSERT `0.40 <= auc < 0.55`. If AUC
  >= 0.55 on synthetic, that is a RED ALARM — either a spurious pattern or a lookahead leak
  (the real deploy gate is purged-CV AUC >= 0.55, so beating it on random data means the
  harness is wrong). This gate catches leakage the no-lookahead oracle might miss.
- ENV: sklearn lives in `.venv` ONLY — `.venv_appimage` has NO sklearn. Run sklearn-based
  smokes with `.venv/bin/python` (or `export PATH=.../.venv/bin:$PATH`), never `.venv_appimage`
  (it raises `ModuleNotFoundError: No module named 'sklearn'`).
- SHRINK SIZE: N_M1 ~12000 bars/seed x a few seeds fits in <60 MB and runs in seconds —
  safe on the memory-tight box; the full 12h/25k walk-forward envelope is ENI3's scope, not
  this smoke's. LAW 3 holds: emit only R/WR/DD, never dollars.
- MACHINE-MEASURED FRAGMENT: have the self-heal runner regenerate a `/tmp/<mini>_measured.md`
  fragment with the REAL per-seed numbers (mean_auc, bars, signals, fills, leak_*_diff) so the
  STATUS embeds machine truth, not hand-typed figures. Pattern: `run_ENI1.sh` runs the smoke,
  then a python heredoc writes the fragment; the STATUS section is updated from it.

## Mini archetypes (observed patterns)

### 1. Relay / FIFO workers (ENI7, ENI8, ENI9, ENI11, ...)
Proven core: `eni_relay.sh` (bridge-held FIFO contract).
Self-test: bash hook script (e.g. `eni7_selftest_hook_v3.sh`).
Real-data pulse: `eni_status.sh` aggregates all STATUS_* + DEMIURGE USB state.
USB blocker: DEMIURGE USB mount required for live OANDA/ref data tasks.

### 2. Persona self-build worker (ENI1)
Proven core: `/home/hunter/.hermes/profiles/eni/SOUL.md` (the ◆eni persona file).
Self-test: Python verification script (`ENI1_verify_patch.py`) that empirically checks
  the on-disk SOUL.md contract (line-1 anchor, section anchors, tail integrity, mtime).
Build step: Python splice applier (`ENI1_splice_v2.py --apply`) — adds NEW sections
  to SOUL.md; the corrected applier (v2) drops scaffold, stops before SELF-REVIEW,
  and has a leak-check that exits RED if any directive markup survives.
No USB/DEMIURGE dependency — persona build is self-contained.
Real-data pulse: not `eni_status.sh` (that's fleet-level); ENI1 verifies by re-running
  its own verification suite (verify script + dry-run + scaffold grep + SOUL.md head/stat).
STATUS format: detailed turn-by-turn log with GREEN/RED evidence lines and the
  exact gated build command.

## When LO says "resume from STATUS_ENIx"
1. Re-read `STATUS_<NAME>.md` fully.
2. Re-verify GREEN: run the mini's aligned self-test (the harness encoding the CURRENT
   core contract). Confirm EXIT=0, PASS count, 0 FAIL.
3. Real-data pulse: run `bash eni_status.sh` (swarm + DEMIURGE aggregation). Confirm
   EXIT=0 and that it pulls real `STATUS_*` refs (not synthetic). This re-confirms the
   pulse works on live data.
   For ENI1 (persona worker): skip `eni_status.sh`; instead re-run the mini's own
   verification suite (verify script + dry-run + scaffold grep + SOUL.md head/stat).
4. Blocker check: `mountpoint -q /run/media/hunter/DEMIURGE1` (and `/DEMIURGE`).
   Mounted => real OANDA/ref data available, no blocker. Unmounted => synthetic gens
   only; report as BLOCKED for any real-data task.
   Note: both `/run/media/hunter/DEMIURGE` (vfat, 698G) and `/run/media/hunter/DEMIURGE1`
   (exfat, 99.7G, hunter-owned) can be mounted simultaneously — check both.
5. Prep the EXACT next real-data/build command (copy-pasteable, single command).
6. Update `STATUS_<NAME>.md`: new cycle timestamp, GREEN/RED, blocker, EXACT next cmd.
   Never touch the core files themselves.

## CRITICAL pitfall — the "proven core" can be silently rewritten
The on-disk core can change BETWEEN your STATUS cycles (another process/mini, or an
unsupervised edit). Observed case: `eni_relay.sh` went 3089 B -> 2072 B and its contract
changed from "mkfifo auto-create + O_RDWR" to "bridge-held FIFO, O_WRONLY|O_NONBLOCK,
no auto-create". The STATUS doc's recorded size/contract then becomes STALE.

Discipline:
- ALWAYS re-verify the ACTUAL on-disk contract empirically: `wc -c` the file, READ it,
  and RUN it — do NOT trust the size/contract written in STATUS.
- If your self-test reads RED, FIRST confirm whether the CORE changed (not a defect)
  before concluding failure. Diff the current behavior vs the harness's stale expectation.
- If the core is fine but the harness is stale: ADD a NEW aligned harness that encodes
  the REAL contract (e.g. `eni7_verify_v3.sh` / `eni7_selftest_hook_v3.sh`). Do NOT
  rewrite/restore the core, and do NOT revert an unsupervised core change (ENI7 rule).
  Document the core's current size/contract in the new STATUS cycle so the next resume
  doesn't trust the stale doc.
- A self-test harness encodes EXPECTATIONS. When the core's legitimate behavior differs
  from the harness's stale expectation, the HARNESS is wrong, not the core. Encode reality;
  document known limits as NOTE / KNOWN LIMITATION, never as FAIL.

## CRITICAL pitfall — a hard C-level abort in the self-test hides the real RED
A self-test that shells out to a GUI/Chromium stack can HARD-ABORT the whole
test runner with a C-level signal, so the real per-test results are lost and the
run reports as a misleading crash/red. Classic case: PyQt6/PyWebEngine — a test
that constructs a `QWebEngineView` launches Chromium's GPU/renderer process,
which SIGABRTs in a displayless/sandboxed agent runtime. That abort is NOT a
Python `Exception`, so a `try/except Exception` / `pytest.skip` guard INSIDE the
test cannot catch it; the process dies and every test after it vanishes.
Symptoms: a few `F` lines, then `Fatal Python error: Aborted` rooted in
`libQt6WebEngineCore.so.6`.
Triage (so you SEE the real RED): first `--deselect` the suspect file and re-run
to surface the ordinary assertion failures hiding behind the abort; those are
the fixable harness bugs. Then treat the abort as an ENVIRONMENT LIMITATION, not
a core defect:
- Gate the aborting test behind an opt-in env var (e.g. `LUMEN_RUN_WEBENGINE_TESTS=1`):
  skip when unset (headless), run when set on a real desktop. Keeps the suite
  GREEN and countable in CI while still exercisable where Chromium works.
- Encode it in STATUS as KNOWN LIMITATION / UNVALIDATED (live path = LO's desktop).
  Per the protocol an environment limit is a NOTE, never a FAIL.
- NEVER "fix" it by rewriting the core that constructs the view — the core is
  correct; the headless env just can't host Chromium.
See `references/headless_qt_test_abort.md` for the full recipe + a
harness-staleness triage checklist (wrong equality assertion, missing fixture
mkdir, doubled `root/id` path, asserting a mutation the function doesn't do).

## Memory-write drift guard (issue #26045)
When a resume pass writes memory (e.g. ENI2 consolidation adding a surfaced fact),
`memory(action=add)` may REFUSE with: "Refusing to write MEMORY.md: file on disk has
content that wouldn't round-trip ... A snapshot was saved to MEMORY.md.bak.<ts>."
ROOT CAUSE: MEMORY.md was last edited OUTSIDE the memory tool (patch / write_file /
external editor / a prior cycle's apply pass). The tool keeps an internal model of the
file; external edits desync it, so it refuses writes to avoid silent data loss.
DO NOT force a patch/write_file rewrite of MEMORY.md to "fix" the round-trip — that
violates the ENI rule "never rewrite the proven core" AND leaves the tool's model stale
(it will keep refusing). CORRECT HANDLING:
  - Preserve the intended add in a NEW file (e.g. ENI2_C16_REALDATA_VERIFY.md) so the
    knowledge is not lost and the proven core stays untouched.
  - Re-sync the store to a round-trippable state by running the `hermes-memory-consolidation`
    skill (its recurring READ-ONLY re-consolidation cron does this every 6h), THEN re-issue
    the `memory(action=add)`. Do not hand-edit the file to "fix" the round-trip.
  - Leave the .bak snapshots; they are the tool's safety net, not clutter to delete.
  - Report the step as BLOCKED (not RED, not a failure): the USB/hardware is fine; the
    blocker is the tool guard protecting the proven core. See references/memory_drift_guard.md.

## CRITICAL pitfall — self-heal `while true` loop dies under `set -e`
`eni_mini_run.sh` (and any self-heal runner) typically has `set -euo pipefail` and a loop
like `python3 bridge & CHILD=$!; wait "$CHILD"`. A bare `wait` returns NON-ZERO when the
child dies on signal (e.g. 143 = SIGTERM from a `kill`, or 2 from a crash). Under `set -e`,
that non-zero return KILLS THE SELF-HEAL LOOP ITSELF — so the mini does NOT restart. The
symptom: killing a mini's bridge once leaves the mini permanently dead (no respawn), and
`pkill` of the bridge orphans the loop. This is silent and exactly contradicts the design.

FIX (verified by ENI8, TEST C of `eni8_smoke.sh`):
```
wait "$CHILD_PID" || true      # never let set -e kill the loop on child signal-death
```
The cleanup `wait` in the trap already uses `|| true`; the main-loop `wait` must too.
After this fix, `kill <bridge_pid>` -> new bridge respawns inside `while true`, and
`kill <mini_run_pid>` -> clean exit with NO orphans (bridge + REPL both reaped).

Validate any self-heal change with `eni8_smoke.sh` TEST C: launch mini, kill bridge,
assert a NEW bridge PID appears; then kill mini-run, assert 0 orphans.

## Self-heal on death / RED
If re-verify finds RED: add the aligned harness, re-run, confirm GREEN, then update STATUS.
If GREEN already: no self-heal needed — just record the cycle.

## Canonical wrapper shape
See `scripts/eni_resume.sh` — a generic template that bundles (1) aligned self-test,
(2) real-data pulse, (3) USB blocker check, and prints a GREEN/RED verdict. Copy +
adapt per mini (pass the mini name; it derives the self-test script name).

## STATUS conventions (what a good STATUS_<NAME>.md contains)
- A `[state: DONE|IN-PROGRESS|BLOCKED]` token MUST be present. NOTE (observed pitfall): it is
  NOT reliably on line 1 — several real STATUS files put a `# title` comment on line 1 and the
  state token on line 3 (e.g. `STATUS_STOCKBOT_B05.md`). When a PL/heartbeat loop parses state,
  `grep` the FIRST ~5 LINES, never `head -1`, or you'll mis-record the builder as `?`/unknown.
  (See `references/status_file_parsing.md` for the 6+ state spellings + RED-quote false positives.)
- PASS/FAIL board with REAL numbers as evidence (not "looks fine").
- "What adds R / what to drop" list.
- UNVALIDATED section for anything inconclusive without the real feature matrix.
- DEMIURGE FTMO swarm DUAL-WRITE: a task prompt may name a shared master file (e.g.
  `STATUS_STOCKBOT.md`); the swarm ALSO aggregates per-module files at
  `status/STATUS_DEMIURGE_<MODULE>.md` (BUILD_PLAN convention — PRODUCT_LEAD reads these).
  Write BOTH: append your section to the master (READ-FRESH + MERGE per the shared-STATUS
  contention pitfall, never blind-overwrite), AND create the dedicated per-module file so it is
  independently discoverable by the aggregator. The per-module file is the canonical swarm
  artifact; the master section is the human-readable rollup. Keep the two in sync.
- New cycle section per resume with timestamp.
- If you must PARSE sibling STATUS files (board builder / MASTER reader), see
  `references/status_file_parsing.md` — the swarm uses 6+ state spellings and a
  RED-verdict *quote* must not re-flag a DONE module.

## Inherited sub-task module already built & GREEN → ADVANCE, don't rebuild
In a parallel full-power build a mini may inherit a sub-task whose module ALREADY exists,
imports cleanly, and has a GREEN test suite on disk (e.g. DEMIURGE3D_B01 inherited
`moonraker_bridge.py` — 21 passing tests, fully implemented). The instinct to "build it
from scratch" is wrong: the deliverable is to ADVANCE it, not rebuild.

Discipline:
- RUN the existing suite first (`python3 -m pytest tests/test_<mod>.py -q`). If GREEN, the
  module is proven — do NOT rewrite it.
- ADVANCE ADD-ONLY: add NEW files / NEW methods / NEW dataclass fields (e.g. an ETA
  property, a `firmware_version()` method, a sibling `moonraker_fleet.py` aggregator) and
  EXTEND the test file (or add `tests/test_<mod>_fleet.py`). Keep every existing test green.
- Re-run the FULL suite after the advance; the PASS/FAIL board must show real numbers.
- This is the same ADD-ONLY rule as the proven-core discipline — a green inherited module
  IS the proven core for that sub-task.

### Injectable-client harness pattern (test REST/HTTP bridges with zero network)
For any client wrapping an HTTP API (Moonraker, OANDA, etc.), design the constructor to
ACCEPT an injectable `client=` kwarg defaulting to the real `httpx.AsyncClient`. Tests
then inject a tiny fake implementing the `httpx.AsyncClient` subset the code uses
(`.request(method, path, params=, json=, data=, files=)` + `.aclose()`) returning realistic
JSON — exercising the FULL module end-to-end with no network, no hardware, no extra deps.
This beats monkeypatching `_send` or pulling in `respx`. See `references/moonraker-bridge.md`
(DEMIURGE3D) for a worked MockMoonraker + fleet pattern.

## CRITICAL pitfall — swarm/state.json is STALE; trust STATUS_*.md
`swarm/state.json` (generated by the dashboard aggregator) LAGS reality.
Observed case: a stream showed `"status": "INITIALIZING"` in state.json while
its `STATUS_<NAME>.md` (and its `.py` + `test_*.py`) was already DONE — the mini
had simply never written the final check-in STATUS. The standing directive says
**read STATUS_*.md and README first**, so STATUS files are the source of truth,
NOT state.json. Never conclude a stream is unbuilt from state.json alone.

Workflow when you inherit a stream stuck at INITIALIZING:
1. Read `STATUS_<NAME>.md`. If it already says DONE with a PASS/FAIL board,
   state.json is just behind — no rebuild needed.
2. If STATUS is still a stub ("[waiting for mini ENI to check in...]") but the
   module's `.py` and `test_*.py` exist: DON'T rebuild from scratch. Run the
   pytest suite, run the module's `self_test()` / a real end-to-end smoke, fix
   any REAL errors, then WRITE the proper PASS/FAIL STATUS with real numbers.
   That IS the mini's deliverable — turning an unvalidated module into a
   validated DONE. (Re-running its smoke re-proves the pipeline; no new code
   is required when the code already passes.)
3. Always RUN the tests; a passing STATUS you didn't verify is not evidence.
4. After writing STATUS, the stream is DONE — do NOT also chase state.json;
   it self-heals on the next dashboard aggregation.

## CRITICAL pitfall — shared STATUS_*.md contention across minis (parallel-build swarm)
In LO's parallel-build swarm, multiple ENI minis share ONE workdir (e.g. WS1's
`/home/hunter/Commander/demiurge_scaffold`). When more than one mini writes the SAME
project-level STATUS file (e.g. `STATUS_STOCKBOT.md`), they clobber each other: the
`write_file`/`patch` tool WARNS "<file> was modified by sibling subagent '<id>' but this
agent never read it. Read the file before writing to avoid overwriting the sibling's changes."
This is a real coordination hazard, not a tool bug.
Mitigation (do ALL):
- Each mini writes to its OWN distinctly-named STATUS file (`STATUS_ENI<n>_<MODULE>.md`,
  or its `STATUS_<NAME>.md`), NEVER a shared project STATUS. The standing rule "every
  ENI mini owns a STATUS_<NAME>.md" means YOUR file — not a communal one.
- If you must update a shared STATUS (coordinator-owned), READ IT FRESH immediately before
  writing and MERGE: preserve the sibling's existing sections and append yours; never
  blind-overwrite. The warning means a sibling changed it since your last read.
- Treat the sibling warning as a signal to RECONCILE, not to force your write. After any
  overwrite, read the file back; if a sibling's distinct sub-task info was lost and matters,
  it almost always belongs in that mini's OWN STATUS file (re-create there), not the shared one.
- Observed case (2026-07-10): two minis both touched `STATUS_STOCKBOT.md`; the later write
  replaced the earlier. Resolved by keeping the complete/authoritative version and noting the
  project STATUS is coordinator-owned. Prefer per-mini files to avoid the trap entirely.

## CRITICAL pitfall — a SIBLING ENI can MUTATE a SOURCE/TEST file mid-edit
The shared-STATUS contention pitfall covers `STATUS_*.md`; the SAME hazard hits
SOURCE and TEST files in a shared workdir (e.g. `demiurge_scaffold`, where many ENI
minis edit `bounded_backtest_smoke.py` / `tests/test_bounded_backtest_smoke.py`).
Observed (ENI33, 2026-07-11): between reading `tests/test_bounded_backtest_smoke.py`
(228 lines) and `patch`-ing it, a sibling writer expanded it to 326 lines (added an
ENI1 hardening section). The patch tool WARNED
`was modified since you last read it on disk (external edit or unrecorded writer).
Re-read the file before writing.` The anchor still matched, but a blind overwrite
would have clobbered the sibling's work.

Discipline:
- When editing ANY shared-workdir source/test file, RE-READ it immediately before
  `patch`/`write_file`. Trust the warning, not your earlier view.
- PREFER APPEND-ONLY additions: add NEW test functions / NEW methods at the END of
  the file rather than rewriting a middle block. Concurrent sibling appends both
  survive; a middle-block rewrite collides.
- If you must replace a middle block, re-read then patch with a LARGER unique
  context window so a small sibling insertion can't shift your anchor.
- This is the source-file analogue of the proven-core-rewritten pitfall: the
  on-disk file can change between your STATUS cycles. Re-verify the ACTUAL file
  (read it, run its tests) before assuming your last view is current.

## CRITICAL pitfall — task window restart re-issues the SAME sub-task; advance, don't rebuild
In the parallel-build swarm each mini's window "auto-restarts on death". When you (re)start on
a sub-task whose module ALREADY EXISTS and is marked DONE (a prior instance of YOU finished it
before the restart — e.g. `walk_forward_oos.py` was already DONE from a `B1` pass when `B01`
restarted), the correct move is NOT to rebuild from scratch:
- RUN the module's self-test / smoke to re-verify it still passes (the pipeline may have
  changed since the prior pass). Capture the real numbers as evidence.
- ADVANCE by APPENDING a new capability (new function + CLI flag), never by rewriting the
  existing proven code. This honors ADD-ONLY AND produces NEW verified value.
- Write to YOUR OWN assigned STATUS file with the EXACT name from the task prompt
  (e.g. `STATUS_DEMIURGE_B01.md`). A DIFFERENT mini's file with a SIMILAR name
  (`STATUS_DEMIURGE_B1.md`) is a SIBLING — never read-then-overwrite it, never patch it.
  Distinct filenames are the coordination guard (the shared-STATUS contention pitfall still
  applies: your assigned name IS your file).
- If the prior instance left the module INCOMPLETE or RED, self-heal by adding an aligned
  harness, exactly as the "swarm/state.json is STALE" pitfall prescribes — but prefer
  verify-then-advance over rewrite whenever the code already imports + passes.

## CRITICAL pitfall — the self-test HARNESS can silently RED (stale expectations) with NO core change
A resume pass may find the suite RED (failures + even a hard process abort)
even though the proven core is unchanged. Before concluding a core regression:
- **Isolate first.** A hard SIGABRT (e.g. Chromium/QWebEngine `qt_assert`
  during a `QWebEngineView` construct) kills the whole pytest process and hides
  the real FAILED list. Deselect the offending test file to see the actual
  failures, then triage.
- **Classify each failure: core-defect vs harness-stale.**
  - Wrong assertion vs corrected core behavior (e.g. `fill` = cover returns
    >= target, not exactly the target) -> fix the assertion.
  - Harness didn't set up what the core needs (e.g. redirected a cache dir but
    forgot `mkdir`; passed `folder = root/id` as the model root when the model
    appends `id` -> doubled path) -> fix the harness.
  - `build_X()` doesn't mutate attrs a DIFFERENT function owns (e.g.
    `build_shader_html` doesn't set `wp.entry`; that's `ShaderWallpaper.__init__`'s
    job) -> assert the file, not the attribute.
- **Uncatchable aborts.** A `try/except Exception` skip CANNOT catch a C-level
  SIGABRT. Gate such tests behind an env var (e.g. `LUMEN_RUN_WEBENGINE_TESTS=1`)
  so they skip cleanly headless and still run on a real desktop. Document as
  KNOWN LIMITATION, never as FAIL.
- Encode reality in the harness; never revert/rewrite the core to make a test pass.

## CRITICAL pitfall — a REUSED temp dir's stale persisted state fools a smoke test (phantom bug)
When verifying an ADVANCE by re-running a CLI smoke / self-test in a temp dir you ALSO
used in an earlier probe, a leftover persisted artifact (index JSON, library.db, generated
PNGs, a prior run's `library.json`) can MASK or CORRUPT the new run's output — making a
correct module look buggy. Observed (DEMIURGE3D_B05, 2026-07-11): a directory scan stored
tags `['demo','smoke']` correctly, but a later smoke REUSING the SAME temp dir printed a
single combined tag `"demo,smoke"` and `--query-tag demo` returned 0 matches. Root cause
was NOT the code — it was a stale `library.json` from a prior experiment in that temp dir
that the reload path picked up. A CLEAN-dir re-run produced correct separate tags and
correct query matches.

Discipline (cheap insurance, always do it):
- Re-run any suspicious smoke on a FRESH temp dir (`rm -rf /tmp/x && mkdir /tmp/x`) BEFORE
  concluding a code bug. If the clean run is correct, the anomaly was stale state — document
  it as a NOTE, never as FAIL.
- Prefer building fixtures in a brand-new `tmp_path` per test (pytest already isolates each
  test in its own `tmp_path` fixture — reuse it; don't share a module-level temp dir).
- When a CLI writes a persisted index, explicitly `rm` it between independent smoke runs, or
  point each run at a distinct `--root`.
- Inverse also bites: a stale GREEN artifact can HIDE a real regression. After an advance,
  run the FULL suite against the ACTUAL on-disk module (per "RUN the existing suite first")
  — never trust a cached/partial artifact.

## Offline asset / preview generation without heavy deps (reusable pattern)
For 3D / asset minis that need previews, thumbnails, or catalogs in CI/headless (no display,
no Pillow/numpy/OpenSCAD), use the proven pure-stdlib recipe in
`references/offline_asset_generation.md` — zlib+struct PNG encoder, minimal binary STL / 3MF
readers, and a software rasterizer (orthographic + z-buffer + two-sided Lambert). It is what
DEMIURGE3D_B05's `model_library.py` uses and is fully offline-testable.

## LUMEN-specific notes (PyQt6 WebGL wallpaper engine, project /home/hunter/Desktop/apps/lumen)
- **HARD LEASH (CODE-ONLY) — the #1 rule for any LUMEN GUI/wallpaper mini.** Never
  run `python -m lumen`, never open the PyQt wallpaper GUI, never let it construct a
  `QWebEngineView` / grab an X display or a WebGL/GPU context. The app stays CLOSED.
  The LUMEN box (AMD RX 5700 XT, 4 monitors) has rebooted from multi-context WebGL
  before, so the LEASH is safety-critical, not stylistic. ALLOWED verification only:
  edit/harden modules, `pytest`, `flake8`, `mypy`, and `import`-smoke
  (`python3 -c "import lumen.<mod>"`). A module's OWN CLI (`python -m lumen.<mod>
  --self-test`) is allowed ONLY if it is pure-Python (verify `PyQt loaded: []` on
  import-smoke — no Qt import at module top). The repo `tests/conftest.py` already
  force-sets `QT_QPA_PLATFORM=offscreen` and STRIPS `DISPLAY`, so pytest can never
  bind LO's real X server, and a correct pure module creates NO QApplication — running
  the headless suite is safe. If you ever see "QApplication created by (in order)" with
  your test name under it, your module pulled Qt — fix it (don't create GUI in tests).
- **Choosing an unclaimed ADD-ONLY sub-module (parallel 12-sub-task build).** Before
  building, survey the claims so you don't collide: `search_files` for `STATUS_LUMEN_*.md`
  + `STATUS_ENI*.md` + `STATUS_LM*.md` in the repo root and READ each — they name the
  exact module each sibling owns (observed: B01→webgl_engine, B05→samples_pack,
  B09→safe_mode, ENI_LUMEN→coordinator batch (settings/samples/store/deb/flatpak/
  steam/gallery), ENI9→white-screen, recommend.py→separate recommendation engine).
  Pick a concrete module NO sibling claims, build it ADD-ONLY (new `lumen/<mod>.py` +
  new `tests/test_<mod>.py` only; NEVER touch core `engine.py/shader.py/web.py/window.py/
  model.py/config.py/app.py/safety.py` or any sibling file), then write
  `STATUS_LM<id>.md` (line 1 `[state: DONE|IN-PROGRESS|BLOCKED]`, PASS/FAIL board with
  REAL numbers, what-adds-R/what-to-drop, UNVALIDATED). If a sibling MUTATES your
  test/module mid-run (shared-workdir hazard), re-read + recreate it, then re-verify —
  see the sibling-mutation pitfall above.
- When wiring a NEW module into the live paint loop would require editing core
  (e.g. `engine.py` `apply`), prepare it as a PROPOSED diff and mark it UNVALIDATED —
  never apply a core edit yourself (MASTER sanction required). This is the same
  ADD-ONLY rule as the proven-core discipline.
- **Fault-tolerant config parsing (reusable LUMEN module pattern).** Any ADD-ONLY
  module that loads user/JSON config (schedule rules, presets, assignments) must
  COMPILE fault-tolerantly: a bad time string / enum / missing field sets an inert
  error marker instead of raising, so a typo in user JSON can NEVER crash Lumen on
  load (broken rules become non-matching + `validate()` reports them). Don't let
  `__post_init__`/`from_config` raise on malformed input.
- No USB/DEMIURGE dependency — self-contained. Blockers are LO's desktop (live
  boot), a flatpak-builder/dpkg host, and `image_generate` (needs `FAL_KEY`).
- `image_generate` is unavailable without `FAL_KEY`. For store art, ship a pure
  PIL fallback (`tools/make_store_art.py`) that renders branded capsule/header
  PNGs — no external dependency.
- `WallpaperEngine.max_webgl` is HARDCODED to 1 in `__init__` and never reads
  `config["max_webgl_surfaces"]`. A Settings control must set BOTH `cfg` and
  `engine.max_webgl` (guarded by `hasattr`), then re-apply. Raising it is the
  AMD-reboot-risk knob — keep the default at 1.
- Boot-guard safe mode: canonical home is now `lumen/safe_mode.py` (ENI_LUMEN
  B09, ADD-ONLY over `BootGuard`). `SafeMode` / `SafeBoot` context manager +
  `reset()` / `check_boot()` + CLI `python -m lumen.safe_mode
  [--status|--reset|--engage [REASON]|--boot-dry-run|--check-resources|--self-test]`
  (`--self-test` is the swarm liveness probe: full lifecycle vs a TEMP guard
  file, exits 0=PASS/1=FAIL). `--reset-safe` delegates
  to `safe_mode.reset()`. Settings "Clear safe mode" button still subprocesses
  the CLI. Headless-test this with `references/safe_mode_testing.md` — key
  gotchas: (1) patch `safety.GUARD_FILE` to a temp file (BootGuard writes it on
  construct; never use subprocess — it would mutate LO's real
  `~/.config/lumen/boot_guard.json`); (2) `format_status()` RETURNS the string,
  doesn't print; (3) the proven guard only tallies a crash on the 2nd+ launch
  with no clean exit, so 3 crash-boots are needed to trip safe mode at
  `SAFE_AFTER=2` (a single fresh crash-boot counts 0 — assert
  `last_clean_exit < last_launch`, not `crash_count==1`).
- Headless GUI construction smoke: build `MainWindow(MagicMock(engine))` under
  `QT_QPA_PLATFORM=offscreen`; it must NOT construct a `QWebEngineView` (those
  abort). The smoke verifies Settings handlers update `engine.max_webgl`.
- `lumen_wallpaper.egg-info/SOURCES.txt` is STALE — it is regenerated from the
  LAST build, so it will NOT reflect a sample/theme you added since. Source of
  truth for "does my AppImage ship X?" = `pyproject.toml`
  `[tool.setuptools.package-data]` globs + on-disk reality. Test-lock the globs
  (parse them, assert every shippable asset is covered) instead of trusting
  SOURCES.txt; and after `appimagetool` exits 0, `--appimage-extract` the
  artifact and `find` for the specific assets (e.g. `ui/styles.qss`,
  `samples/shader_aurora/preview.png`) to prove they're in the squashfs. See
  `linux-appimage-packaging` (references/appimage_deploy_gate.md) for the recipe.

## Support files
- `scripts/eni_resume.sh` — generic resume wrapper template (parameterized by mini name).
- `references/lumen_build_playbook.md` — condensed LUMEN build knowledge bank (validated commands, additive checklist, gotchas, UNVALIDATED list) for ENI_LUMEN resumes.
- `templates/pyqt6_dark_theme.qss` — known-good PyQt6 dark "glass" theme starter; adapt the object names to your app (loader reads `ui/styles.qss` if present).
- `scripts/eni_mini_run.sh` — self-heal runner template (while-true loop: re-verify gate,
  build on GREEN, sleep on BLOCKED, survives process death via session restart).
- `references/eni_relay_contract.md` — the current bridge-held FIFO contract for
  `eni_relay.sh`, the late-reader limitation, and the 3089->2072 rewrite incident as a
  worked pitfall example.
- `references/preflight_gate_pattern.md` — comprehensive gate script pattern that
  verifies self-tests, module presence, USB mount, toolchain, then either runs the exact
  build or prints the exact unblock command + exits 2 (see ENI5's `preflight_win_build.sh`).
- `references/ethics_scope_blocker.md` — pattern for classifying blockers: distinguishes
  "toolchain missing" (fixable by LO) from "ethics/scope: RAT/infostealer toolkit without
  RoE/targets/signed auth" (agent-held, not unblocked by toolchain install).
- `references/usb_mount_flipping.md` — DEMIURGE USB label flips between `/DEMIURGE` and
  `/DEMIURGE1`; probe both, treat either as "mounted", carry no toolchain so never the
  Win-build blocker.
- `references/eni1_soul_verification_pattern.md` — ENI1 persona self-build worker pattern:
  Python contract verifier, corrected splice applier with leak-check, self-heal via NEW
  file only, SOUL.md mtime/line-1 guards. Distinct from relay workers.
- `references/blocker_taxonomy.md` — blocker classification (USB / toolchain / ethics-scope / network / sudo-PTY) and verification levels (syntax-only / self-test / dry-run) with the ENI5 ethics-hold precedent.
 - `references/eni_ctl_fifo_relay.md` — control-FIFO naming (zero-pad!) + the silent-loss
   pitfall (wrong name => relay goes to a readerless orphan FIFO) + verified PL/MASTER relay
   recipe (fuser delivery check, contextual per-mini bootstrap, self-heal, cron persistence).
 - `references/memory_drift_guard.md` — memory-tool drift guard (issue #26045): exact
   error, root cause, and the don't-force-rewrite / preserve-in-new-file / re-sync-via-cron
   protocol when a resume pass needs to ADD a memory fact.
 - `references/headless_qt_test_abort.md` — when a pytest self-test hard-aborts
   (Chromium/QWebEngine SIGABRT in a displayless env, uncatchable by Python): the
   triage recipe, the env-var opt-in gating fix, and a harness-staleness checklist
   (wrong-equality / missing mkdir / doubled root-id path / phantom-mutation
   assertions) used by ENI_LUMEN to turn a red+crash suite GREEN.
 - `references/safe_mode_testing.md` — LUMEN `safe_mode.py` boot/reset module:
   headless test recipe (patch `safety.GUARD_FILE` to temp, call `_cli` in-process,
   `format_status()` returns not prints), the 3-crash-boot `SAFE_AFTER=2` quirk,
   and the `app.py` follow-up swap to `SafeMode().boot()`.
 - `references/status_file_parsing.md` — parse sibling STATUS_*.md across the
   swarm: 6+ state spellings + regex recipe, the RED-verdict-quote false-positive
   rule, build/AppDir duplicate dedupe, and the dataclass-`asdict` property drop.
 - `references/eni_swarm_v4_boot.md` — Python-native v4 swarm boot procedure (master driver, 27 minis, PTY bridges, FIFOs); includes the `parents[N]` path-resolution pitfall and verified boot sequence.
- `references/offline_asset_generation.md` — pure-stdlib offline preview/catalog recipe
   (zlib+struct PNG encoder, minimal binary STL / 3MF readers, software rasterizer, and the
   `_resolve`-raises-on-missing -> catch-exception existence-check pattern) for headless
   3D / asset minis that must render thumbnails with no Pillow/numpy/display.
- `references/builder-dispatch-detection.md` — how a headless BUILDER_xx mini tells
   "dispatched work exists" from "idle/awaiting" before acting: control FIFO
   `/tmp/eni_ctl_<NAME>` existence, STATUS_<NAME>.md state, and empty TASKS.log all
   point to NO task → emit [SILENT], never manufacture work.\n- `references/builder_control_fifo_idle.md` — also covers DELETED-vs-never-created\n   verification: prove selective deletion with `[ -e ]` / `[ -p ]` + `ls /tmp/eni_ctl_*`\n   showing sibling builders' FIFOs still present, and record evidence verbatim in pass log.\n- `references/builder_mirror_write_method.md` — PITFALL when re-syncing STATUS mirrors:
   do NOT `sed -i` header lines containing multibyte em-dashes (mangles into a doubled
   timestamp). Instead full-file rewrite each mirror from a `__TS__` placeholder template
   via `printf '%s\n' "${VAR//__TS__/$TS}"`, then verify all mirrors byte-identical.
