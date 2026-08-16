# Fleet Monitor — Full-Pass Confirmation Checklist

A single verified end-to-end pass of `monitor_fleet.py` run as the scheduled
cron (Aug 2026). Use this as the "what a healthy dormant report looks like"
template and to confirm you've gathered every corroborating signal before
declaring DORMANT (not broken).

## The one-line verdict shape
"Ledger shows N DONE / M IN-PROGRESS / K BLOCKED — **but mtimes all stale →
fleet dormant, no active tasks → no action required.**"

## Confirm ALL of these (do not stop at the ledger)
1. **Run** `cd /home/hunter/Commander/eni_swarm && python3 monitor_fleet.py` —
   it writes `HEARTBEAT_LEDGER.md` (report-only; never dispatch from this cron).
2. **Ledger counts** — parse the `[STATE]` prefix column:
   `[DONE] <x> / [IN-PROGRESS] <m> / [BLOCKED] <k>`.
3. **mtime by-date cross-check — THE source of truth**:
   `stat -c '%y' builds/STATUS_BUILDER_*.md | awk '{print $1}' | sort | uniq -c`
   - All (or all but one) on one old date = dormant regardless of ledger claims.
4. **Zero-byte / truncated STATUS file** → report as "silently dropped by crash
   guard (empty STATUS file)", NOT a lost worker. Confirmed real: B20 was 0 bytes.
5. **ALERTS file empty** = no blocked-builder entries. Corroborates "no true
   blockage; BLOCKED rows are stale disk states."
6. **Infra alive check** — gateway / free-router / turbocharger / controller
   (`pgrep -af hermes|free_router|swarm_turbocharger|airllm`) can be UP while
   the builder VLAN is dormant. Infrastructure up is not evidence of a live
   fleet.

## Single-fresh-IDLE-builder signature (additive, verified this session)
If exactly ONE status file is fresh (today) and it self-records **IDLE** —
"Control FIFO does not exist, no directive issued, *do not invent work*" — that
is a **healthy parked builder**, not activity. It is a builder that was woken
(here by the master driver) and correctly recognized there was no task. Fold it
into the same "dormant, no action" verdict; it REINFORCES the report-only
mandate rather than contradicting dormancy.

## Don'ts
- Don't dispatch tasks, edit STATUS files, or spin up builders from this cron —
  report-only. Resurrecting dormant builders requires a live-session directive
  (master driver / PRODUCT_LEAD dispatch) or creating control FIFOs.
- Don't mistake `verified=unknown blocker=unknown next=unknown` ledger rows for
  errors — they corroborate "idle, nothing routed."