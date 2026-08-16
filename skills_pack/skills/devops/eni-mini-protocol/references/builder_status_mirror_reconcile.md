# Builder STATUS-mirror reconcile (empirically confirmed, Aug 2026)

Correction to `builder_control_fifo_idle.md`: the note saying a fourth mirror "is NOT
present on disk — do not hunt for it" is OUTDATED. As of Aug 2026 (BUILDER_37 pass),
there are now **FIVE** STATUS mirrors for a builder (four markdown + one INI under
`.cache`), and ALL must be reconciled to the same state + timestamp each pass. The
authoritative source of truth is the shipped verifier `scripts/check_builder_idle.sh`
— it scans exactly these five. Don't trust a hand-maintained count; run it.

## Confirm mirrors at runtime
The canonical list lives in `scripts/check_builder_idle.sh` (`mirrors=(...)`). For a
self-contained pass you can also enumerate with
`search_files(pattern='*STATUS_BUILDER_<N>*', target='files', path='/home/hunter')`
(for exact-name) plus a `*STATUS*` glob under `~/.cache/eni_swarm/builder_logs/`.
The FIVE confirmed mirrors on disk for BUILDER_37 were:
1. `/home/hunter/Desktop/Enterprise Builder/ENI_Swarm_NEW/STATUS_BUILDER_37.md`
2. `/home/hunter/Desktop/Enterprise Builder/ENI_Swarm_NEW/tasks/status/STATUS_BUILDER_37.md`
3. `/home/hunter/STATUS_BUILDER_37.md`
4. `/home/hunter/Commander/eni_swarm/builds/STATUS_BUILDER_37.md`
5. `/home/hunter/.cache/eni_swarm/builder_logs/BUILDER_37_STATUS.md`
   (⚠️ ALTERNATE naming + format: `<NAME>_STATUS.md`, an INI `[STATUS]` block writing
   `status=[IDLE]`, NOT the `STATUS_<NAME>.md` markdown header used by the other four.
   Its state token is `status=[IDLE]`, so grep tokenize BOTH the markdown H1 and the
   INI form — `grep -Eo 'STATUS_[A-Za-z0-9_]+ — [A-Z-]+|status=\[[A-Z-]+\]'`.)

(`Commander/eni_swarm/builds/` is the workdir named in the STATUS card itself, which is
why it is easy to spot if you enumerate broadly instead of trusting the old "three only"
note.)

## Reconcile loop
1. Read ALL mirrors first (state the truth from the newest/tasks one, else from disk).
2. Write the identical `[IDLE]` + SAME timestamp (`date '+%a %b %d %H:%M %Y'`) body to
   every mirror path. Use `templates/STATUS_BUILDER_IDLE.md` as the canonical known-good
   IDLE body (fill `<N>` = builder number, `<TS>` = the `date` output) so all mirrors
   stay byte-identical and never drift across passes.
   ⚠️ THE CACHE MIRROR IS A DIFFERENT FORMAT — do NOT paste the markdown template there.
   The four `STATUS_<NAME>.md` mirrors take the markdown H1 body, but
   `~/.cache/eni_swarm/builder_logs/<NAME>_STATUS.md` must be an INI `[STATUS]` block
   (its state token is `status=[IDLE]`, verified by the verifier's grep). Observed
   BUILDER_37 Aug 2026: writing the markdown body to the cache mirror still tokenizes
   as IDLE (the H1 `STATUS_BUILDER_37 — IDLE` is greppable too), but it is WRONG and
   breaks the mirror's INI contract. Write it as:
       [STATUS]
       name=BUILDER_<N>
       status=[IDLE]
       checked=<TS>
       <remaining fields ...>
   The timestamp still comes from the same `date` call so the cycle stays unified.
3. Re-verify HEAD of each with one loop: `for f in <paths>; do head -2 "$f"; done`
   confirm the state token AND timestamp landed on every path.

## Run the SHIPPED verifier (with the arg), never a stray /tmp copy
The authoritative check MUST be invoked as
`bash <skill>/scripts/check_builder_idle.sh <BUILDER_NAME>` (e.g. `... BUILDER_37`),
run from the skill's own `scripts/` dir or with its absolute path. The `<NAME>` arg is
mandatory (`${1:?usage: ...}`) and the script sets `set -u`.
⚠️ Do NOT run a loose copy of `check_builder_idle.sh` sitting in `/tmp` (or anywhere else
outside the skill dir). A stale copy observed Aug 2026 lacked the arg-guard and `set -u`,
so without an argument it errored `line 4: 1: usage: check_builder_idle.sh <BUILDER_NAME>`
and returned a misleading `EXIT=1` — the same code the script uses for "mirrors NOT
reconciled". That false signal could push a genuinely-idle pass into needless rewrite
work (or trigger a bogus reconcile+report instead of the correct bare `[SILENT]`). If the
run emits a bare usage/arg error, re-invoke the canonical shipped script with the builder
name before concluding anything about reconcile state.

## Twins/pitfalls
- Mirrors already `[IDLE]` are normal steady state — refresh the timestamp, do not treat
  as an error, do not invent work (control FIFO still absent = IDLE).
- Only reconcile paths that EXIST on disk. Do not invent a mirror that is not present.
- The write is idempotent (same state+timestamp), so sibling concurrency converges;
  re-writing is the fix, not aborting.
- This reunites state across all mirrors so a planner reading any single path sees the
  same picture.