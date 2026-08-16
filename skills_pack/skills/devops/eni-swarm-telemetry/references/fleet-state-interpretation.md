# Interpreting real fleet state (not just ledger tokens)

Session-verified pattern (2026-08-11 fleet-monitor cron run). The ledger
(`HEARTBEAT_LEDGER.md`) and the state tokens inside each
`builds/STATUS_BUILDER_N.md` are NOT a reliable picture of what the fleet is
doing. Always cross-check three independent signals before reporting.

## The three signals
1. **File mtime** — the single most trustworthy liveness signal. Bucket each
   `STATUS_BUILDER_N.md` by age: fresh (<72h) vs stale (days+). A whole field of
   stale files (this run: ~394h ≈ 16 days) means the fleet is parked, not dead.
2. **State token** (`[IN-PROGRESS]` / `[BLOCKED]` / `[IDLE]`) — UNRELIABLE.
   These are written once at launch and never rewritten while a builder sits
   parked. A `[IN-PROGRESS]` tag on a 2-week-old file is a leftover, NOT live
   work. Cross-check against mtime before trusting it.
3. **File content** — read the body: does it say `IDLE` + `blocker=none` +
   "awaiting LO directive via FIFO"? Does the control FIFO (`/tmp/eni_ctl_N`)
   actually exist?

## The subtle trap: fresh mtime ≠ actively building
This run only BUILDER_37 had a fresh mtime (2.3h), but its body read `IDLE`,
FIFO does not exist, no directive issued. Conclusion: a builder can **wake
purely to heartbeat-and-go-IDLE** (a keep-alive touch) without doing any work.
So:
- Many fresh mtimes + `IN-PROGRESS`/"building" content  → fleet genuinely busy.
- ONE fresh mtime + body says IDLE/no-FIFO + 49 stale  → infra alive but fleet
  **idle-awaiting-input**. This is a "kick needed", not a "stall" and not a
  "crash".
- Fresh mtime + `[BLOCKED]` + real blocker text   → genuine stall to escalate.

## Reporting grammar for an idle fleet
State distribution alone is misleading (40 DONE / 8 IN-PROGRESS / 1 BLOCKED in
this run looks alarming, but the ledger "DONE" really means IDLE/READY and the
IN-PROGRESS were stale). Lead the report with the mtime verdict (live vs stale,
how many fresh), then the infra liveness (controller/swarm procs up?), then the
action: "dispatch/kick needed to wake swarm" vs "genuine stall". Distinguish
cleanly: **idle-awaiting-input ≠ blocked ≠ crashed**.

## Recon shortcut
Use `ls -lt --time-style=+%m-%d_%H:%M builds/STATUS_BUILDER_*.md | head` plus a
stdlib mtime-bucket pass to separate fresh from stale in one glance. Corroborate
with `pgrep -af` for swarm/controller procs and `wmctrl -l` for builder windows.
