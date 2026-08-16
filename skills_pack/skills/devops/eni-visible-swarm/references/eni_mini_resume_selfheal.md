# ENI7 stale-GREEN self-heal — case study (v2 → v3)

Problem class: a mini's STATUS claims its self-test is GREEN, but the shipped harness
is STALE against the CURRENT on-disk core. This happened TWICE on ENI7: v2 stale vs v1,
then v3 vs v2. The root cause each time: the proven core was rewritten AFTER the STATUS
was written, so the harness asserted the OLD contract.

## What happened (2026-07-09 23:01 MDT resume)
- STATUS_ENI7.md (written 22:36) claimed `eni7_verify_v2.sh` => 8 PASS / 0 FAIL / EXIT=0.
- On resume, `bash eni7_selftest_hook_v2.sh` TIMED OUT at 180s. A `bash -x` trace proved
  the script actually COMPLETED (reached `exit 1`) — it reported FAIL 1 + FAIL 4.
- Root cause: `/home/hunter/Commander/eni_swarm/eni_relay.sh` had been REWRITTEN at 22:40
  (after the 22:36 STATUS) into a DIFFERENT model:
    • no longer auto-creates the FIFO via mkfifo  (v2's PASS 1 expected that → FAIL)
    • opens WRONLY|O_NONBLOCK (needs a live "bridge" holder), not O_RDWR
    • exits 1 (not 2) on missing args              (v2's PASS 4 expected 2 → FAIL)
  The 22:36 STATUS documented the OLD 3089-B O_RDWR/mkfifo auto-create version. The 22:40
  rewrite was NOT directed by this mini and was NOT reverted (ENI7 rule: never rewrite the
  proven core).

## The 180s "hang" was a red herring
- The hook did `OUT="$(bash verify 2>&1)"` then printed `$OUT` only AFTER verify returned.
  Because verify spawns background `head` readers that inherit the capture pipe, the
  command-substitution never saw EOF → the tool waited → 180s timeout, zero output.
- Lesson: run self-test verify DIRECTLY; never wrap it in command-substitution capture.
  (The script logic itself finished in ~2s — proven by the `-x` trace to /tmp/v2run.log.)

## Self-heal (add-only, core untouched)
Added `eni7_verify_v3.sh` + `eni7_selftest_hook_v3.sh` encoding the REAL current contract:
  A  absent target        -> rc=1, returns 0s, never wedges
  B  live reader          -> prefixed body verbatim
  C  FIFO but no reader   -> rc=2 ENXIO, 0s, nonblocking
  D  usage guard          -> exits non-zero (rc=1)
  E/Eb fleet glob 'V*'    -> nonblocking dispatch, verbatim to live readers
  F/Fb eni_status.sh      -> aggregates STATUS_ENI* + demiurge_scaffold STATUS_*
Result: 8 PASS / 0 FAIL / EXIT=0 / GREEN, ~2s, no wedge. v2 SUPERSEDED.

## Repro recipe (re-run to see it)
```
cd /home/hunter/Commander/eni_swarm
# prove v2 is now RED against current core:
bash -x eni7_verify_v2.sh 2>&1 | tail -5      # shows FAIL 1 / FAIL 4, exit 1
# prove v3 is GREEN:
bash eni7_selftest_hook_v3.sh                  # direct run, no pipe-capture
# confirm the core's real contract (read, don't assume):
grep -n 'WRONLY\|O_NONBLOCK\|mkfifo\|exit' eni_relay.sh
# USB reality (NOT dir-existence):
mountpoint -q /run/media/hunter/DEMIURGE1 && echo MOUNTED || echo NOT_MOUNTED
ls -d /run/media/hunter/DEMIURGE*              # note the stale no-"1" dir
```

## OPEN ITEM flagged to LO
The 22:40 core rewrite was silent. Two options: (a) keep the new bridge-held FIFO model
(the v3 harness already matches it), or (b) restore the mkfifo auto-create / O_RDWR version.
LO decides; either way the v3 harness keeps the suite GREEN. Never revert the core without
LO direction (it would violate the add-only rule and could undo a deliberate change).

## Generic takeaway for ANY ENI mini
STATUS "GREEN" is a claim, not proof. On resume: RUN the hook. If RED, read the current
core, add a vN harness aligned to reality, update STATUS, and flag any un-directed core
change as an OPEN ITEM. Keep the proven core exactly as found on disk.
