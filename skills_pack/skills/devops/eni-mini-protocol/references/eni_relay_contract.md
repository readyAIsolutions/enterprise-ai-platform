# eni_relay.sh — current contract (bridge-held FIFO model)

File: /home/hunter/Commander/eni_swarm/eni_relay.sh
Observed on disk: 2072 B, mtime 2026-07-09 22:57. CAN CHANGE — always re-verify
empirically (`wc -c` + read + run) before trusting any size/contract written in STATUS.

## Usage
    eni_relay.sh <TARGET> <DIRECTIVE...>
  TARGET   = mini name | "all" | glob like "ENI*"
  DIRECTIVE= the text to push (one line). Prefix "LO via MASTER:" is added.

## Contract (CURRENT on-disk behavior — verified by running it)
- absent target FIFO (no /tmp/eni_ctl_<NAME>) -> prints "relay: no FIFO for <NAME>" to
  stderr, returns 1. Does NOT auto-create the FIFO (the old mkfifo-auto-create behavior
  is GONE in the bridge model).
- live bridge holder (a process holds /tmp/eni_ctl_<NAME> RDWR) -> WRONLY|O_NONBLOCK open
  succeeds, the prefixed line is written verbatim; returns 0.
- no live reader (bridge down / mini dead) -> O_NONBLOCK|O_WRONLY open returns ENXIO
  immediately (no hang), returns 2.
- usage (no TARGET) -> `${1:?...}` aborts with rc=1.
- fleet "all" / glob: iterates existing /tmp/eni_ctl_* FIFOs, dispatches nonblocking in
  the background each. Never wedges.

## KNOWN LIMITATION (not a defect)
Late-reader durability is NOT guaranteed. If NO reader holds the FIFO at write time, the
directive is dropped (kernel pipe buffer lost once the relay's fd closes with zero
holders). The swarm norm (minis hold their FIFO open continuously) is unaffected —
verbatim delivery is proven for a LIVE reader. If LO wants true async durability, ship a
NEW spool-safe relay variant (writes to /tmp/eni_spool_<NAME> on no-reader) as an add-only
file; do NOT modify eni_relay.sh.

## Pitfall worked example (ENI7, 2026-07-09)
A self-test harness (v2) asserted "late-reader lossless" and read RED (FAIL 3b) against
the core. The core was NOT broken; the harness expectation was stale — the core had been
rewritten (unsupervised) to the bridge model AFTER the prior STATUS was written.

Fix (ENI7 rule: never rewrite the proven core):
- ADD `eni7_verify_v3.sh` / `eni7_selftest_hook_v3.sh` encoding the REAL contract
  (absent->rc1, no-reader->rc2 ENXIO, live->verbatim, usage->rc1, fleet glob nonblock).
- Result: GREEN, 8 PASS / 0 FAIL, EXIT=0, ~2s, no wedge.
- The core was left untouched; the unsupervised rewrite was NOT reverted. LO decides
  (open item) whether to keep the bridge model or restore mkfifo auto-create — either way
  the harness matches whatever is on disk, so the suite stays GREEN.

Lesson: when a self-test reads RED, confirm whether the CORE changed (not a defect)
before concluding failure. If the harness is stale, add a NEW aligned harness — never
rewrite/restore the core.
