# Fleet Monitor — "fresh mtime" does NOT always mean "alive"

Refinement to `fleet-staleness-interpretation.md`. The mtime freshness cross-check is
the source of truth for dormant-vs-live — but a SINGLE fresh file among an otherwise
stale fleet is NOT automatically a wake-up.

## The trap (observed 2026-08-12)

Fleet fully dormant: 49/50 `builds/STATUS_BUILDER_*.md` dated 2026-07-25 (~2.5 wks old).
Exactly one file, `STATUS_BUILDER_37.md`, touched TODAY (2026-08-12 01:17). Naive reading
says "a builder woke up." Actual content:

```
# STATUS_BUILDER_37 — IDLE — Wed Aug 12 01:17 2026
Control FIFO /tmp/eni_ctl_BUILDER_37 does not exist (re-verified empirically ...).
No directive issued to BUILDER_37.
blocker=none
next=await LO's directive via /tmp/eni_ctl_BUILDER_37 FIFO creation
```

It was a **status_hub / worker re-verify touch** that rewrote an IDLE parking note —
re-confirming FIFO absence. Zero real activity.

## The rule

When exactly one (or a couple of) STATUS file(s) is fresh while the rest of the fleet is
stale:
1. **Read the fresh file's CONTENT before concluding anything.** Distinguish:
   - IDLE parking note (re-verified FIFO absence, `blocker=none`, `next=await LO directive`)
     → still dormant. The fresh touch is just a watchdog / status_hub rewrite.
   - Actual in-progress task text (`# TASK: ...`, progress, verified=...) → genuinely live.
2. Corroborate with process + FIFO checks: `ps aux | grep -E 'eni_builder|builder_'`
   (a live builder shows a working python proc) and `ls /tmp/eni_ctl_*` (a fresh FIFO
   with a writer = a builder waiting on directive).
3. In the report, name the fresh-touch builder explicitly and label it "parked/re-verified
   IDLE, awaiting FIFO directive" rather than "actively working."

A fleet can show a same-day mtime and STILL be fully dormant — the ledger's stale
IN-PROGRESS rows plus a fresh parking-note touch are both alert noise, not failures.
