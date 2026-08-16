# Builder cron idle pass — delivery contract (steady state)

Companion to `builder_cron_dispatch_idle.md`. Covers the FINAL delivery of a
cron-dispatched builder pass that found itself IDLE, once detection is done.

## The rule (empirically confirmed BUILDER_37, Aug 2026)

For a cron-fired builder pass where `check_builder_idle.sh` reports all mirrors
agree on [IDLE] and the control FIFO is absent, the correct terminal delivery is
a **bare `[SILENT]`** — a code block containing exactly `[SILENT]` and nothing
else. It must NOT be:

- a verbose IDLE narrative / recap of the five-mirror check,
- a `[SPREADSHEET]`-style stray formatting artifact,
- any prose at all, even "nothing to report."

The outer cron harness treats `[SILENT]` as "suppress delivery — nothing new."
The detection work (FIFO absence + 5/5 mirror reconciliation) is already
persisted in the STATUS mirrors; repeating it in the delivery is noise.

## Failure mode seen in the wild

A BUILDER_37 cron pass correctly determined IDLE, then emitted a long English
recap plus a stray `[SPREADSHEET]` marker line before finally settling on
`[SILENT]` in a later block. The harness delivered the noise. Lesson: once the
idle check exits 0 (see `scripts/check_builder_idle.sh`), emit the bare
`[SILENT]` immediately. Do not narrate the pass.

## PITFALL: exit-0 from check_builder_idle.sh is necessary but NOT sufficient for [SILENT]

`check_builder_idle.sh` exits 0 when the control FIFO is absent AND all found
mirrors agree on the IDLE state token. It does NOT compare mirror timestamps for
cross-cycle currency. So exit-0 alone does NOT license a bare `[SILENT]`.

Before emitting [SILENT], ALSO confirm the mirrors share the current cycle: compare
each mirror's state timestamp (`verified=` / `verified_at=` / the `— <TS>` in the H1)
and disk mtime against the others and the current date. All-matching-and-recent =
same cycle = silent. One-or-more old / mixed / from-a-previous-day = cross-cycle =
reconcile the stale mirror(s) to the current cycle body + timestamp, then REPORT
(not [SILENT]).

Observed on BUILDER_37 (Mon Aug 10 2026): `check_builder_idle.sh BUILDER_37` exited
0 (5/5 mirrors IDLE) yet `~/STATUS_BUILDER_37.md` carried a stale `Sun Aug 09 22:40`
timestamp while the other four were `Mon Aug 10 01:15`. That is a genuine cross-cycle
drift — reconciled the stale mirror and reported instead of going silent. Trust exit-0
only for "no directive"; decide silent-vs-report from timestamp currency.

## Second clean-pass confirmation (BUILDER_37, Mon Aug 10 03:45 MDT 2026)

The full pipeline ran green end-to-end and a bare `[SILENT]` was correctly
delivered: FIFO NO_ENTRY → `check_builder_idle.sh` exit 0 (5/5 mirrors present,
5/5 IDLE, all disk mtimes `2026-08-10 02:31:00`) → in-file H1 state timestamps
checked and ALL five read `Mon Aug 10 02:30 2026` (same cycle as `date`,
no drift) → bare `[SILENT]`. This confirms the currency gate above is
sufficient: matching-and-recent H1 timestamps + mtimes across all five mirrors
licenses silence without re-writing the mirrors.

## Propagation-side drift: home mirror CURRENT, four satellites STALE (BUILDER_37, Mon Aug 10 03:52 2026)

Reverse of the "home stale" pitfall above, and just as real. On an idle pass the
H1 timestamps came back MIXED: `~/STATUS_BUILDER_37.md` read `Mon Aug 10 03:47 2026`
while the other four mirrors still read `Mon Aug 10 02:30 2026`. Bodies were
byte-identical (diff clean) — the only delta was the H1 + in-body verification
timestamp. That means a PRIOR cycle had updated the home mirror (canonical write
path) but the four satellite mirrors were never re-propagated (mirror
propagation step silently dropped).

Very important: `check_builder_idle.sh <NAME>` STILL exits 0 here — 5/5 state
tokens are `IDLE`, so exit-0 alone is NOT enough to go silent. Only the
in-file-H1-timestamp currency check (not the mtime scan; the script prints
mtimes but does not compare them) reveals the drift. Trust the gate, not exit-0.

Reconcile + REPORT (not [SILENT]):
  1. Confirm bodies are identical except the timestamps (`diff` the home vs one
     satellite) — identical bodies prove drift, not a real state change.
  2. Propagate the NEWEST body to the stale satellites:
       SRC=~/STATUS_<NAME>.md
       for f in <4 satellite paths>; do cp "$SRC" "$f"; done
  3. Re-run `check_builder_idle.sh <NAME>` — all five mtimes should now match.
  4. Since a genuine cross-cycle drift was reconciled, emit a REPORT (the
     delivery contract forbids [SILENT] after a reconcile), noting WHICH mirrors
     were stale and that bodies were identical.

## Manual fallback when `check_builder_idle.sh` can't be located (verified BUILDER_37, Aug 2026)
The delivery rule is gated on the check script reporting "all mirrors agree on
[IDLE]". But the script's canonical path is NOT guaranteed on disk (its recorded
path in `builder_tooling_paths.md` / the skill's category dir may be wrong for
this checkout). Do NOT stall on "script not found" — the rule is equivalently
provable by hand, which BUILDER_37's idle pass actually did:
  1. `[ -p /tmp/eni_ctl_<NAME> ]` → must be ABSENT (FIFO is a named pipe, so `-p`
     is the correct probe; a bare `ls` shows a stray `ENI2`/zero-size entry only
     if the FIFO exists).
  2. `find / -iname "*STATUS_<NAME>*"` to enumerate ALL mirrors (Commander, .cache,
     Desktop Enterprise Builder, home root, tasks/status), then `head -2` each and
     confirm every one carries the `[IDLE]` banner.
  3. `stat -c '%y'` each mirror: all mtimes must cluster within a few seconds and
     be current (same pass cycle). Mixed/old mtimes = cross-cycle = reconcile +
     report, NOT silent.
All three holding == identical verdict to `check_builder_idle.sh` exit 0. Then the
bare `[SILENT]` delivery below applies unchanged.

## When to NOT use this

Any pass where the control FIFO `/tmp/eni_ctl_<NAME>` EXISTS, or where a mirror
is out of sync (check exits non-zero), is NOT silent — it must reconcile and
report. This delivery contract only applies to the genuinely-idle steady-state
case: FIFO absent AND 5/5 mirrors already [IDLE] (check exit 0).

Tooling note: for the canonical on-disk script paths and the pitfall of guessing
the skill's category directory, see `references/builder_tooling_paths.md`.