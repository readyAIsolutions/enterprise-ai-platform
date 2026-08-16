# Fleet Monitor — Full Diagnostic Workflow (cron execution)

When dispatched as a scheduled cron to run `monitor_fleet.py`, follow this complete checklist to produce a reliable fleet-status report. This ties together the diagnostics in other references.

## Step 1 — Run the script

```python
terminal("cd /home/hunter/Commander/eni_swarm && python3 monitor_fleet.py")
```

## Step 2 — Read the ledger

```python
read_file("/home/hunter/Commander/eni_swarm/HEARTBEAT_LEDGER.md")
```

Count the state distribution (DONE / IN-PROGRESS / BLOCKED). Note any missing builder numbers — they indicate blank/empty STATUS files (the script's crash guard skips them).

## Step 3 — Check freshness (mtime cross-check)

```python
terminal("stat -c '%y %n' builds/STATUS_BUILDER_*.md")
```

Focus on:
- **All single-date cluster**: builders parked since that date = dormant floor.
- **One recent file**: inspect its body. If it says "re-verified empirically", "FIFO does not exist", or "IDLE — awaiting directive" — it's a **ghost update** from a cron watchdog, NOT a live builder.
- **Multiple recent files across dates**: possible live activity — inspect each.

## Step 4 — Check the wider fleet (MASTER_STATUS.md from status_hub.py)

```python
read_file("/home/hunter/Commander/eni_swarm/MASTER_STATUS.md", limit=20)
```

The `status_hub.py` cron (5-min interval) is the ACTIVE monitor covering all 598 minis across `eni_swarm/` and `demiurge_scaffold/`. Extract:
- Generation timestamp
- DONE / IN-PROGRESS / BLOCKED / ALERTS counts
- Note whether these are stale (ages > 10 min on non-DONE = carried-over alerts)

## Step 5 — Verify the cron scheduling

```python
terminal("crontab -l | grep -E 'monitor_fleet|status_hub'")
```

This tells you:
- Which monitors are actively scheduled (vs. ad-hoc runs)
- Whether `monitor_fleet.py` itself has a cron entry (it may not — only `status_hub.py` may be scheduled)

## Step 6 — Produce the report

Structure should follow this pattern:

```
**`monitor_fleet.py` [ran/did not run]**

## ENI Builder Fleet Status (N active status files)

| State | Count | Builders |
|-------|-------|----------|
| **DONE** | N | list OR range |
| **IN-PROGRESS** | N | list |
| **BLOCKED** | N | list |
| **Blank/skipped** | N | numbers |

### Freshness Assessment — DORMANT or LIVE

- Date range of STATUS file mtimes
- Report any ghost updates (recent mtime + IDLE/FIFO-missing body text) — name them explicitly
- Note the dormancy duration

### Wider Fleet (via status_hub.py MASTER_STATUS.md)

- N total minis: X DONE / Y IN-PROGRESS (stale, from date range) / Z BLOCKED
- N ALERTS — all stale/carried-over or new?

### Bottom Line

**No change / [specific delta].** One-sentence summary of fleet health.
```

## Pitfalls

- **Do NOT dispatch tasks, edit STATUS files, or spin up builders from this cron.** It is report-only.
- **Do NOT flag stale IN-PROGRESS as new failures.** If all mtimes are from the same old date range, the 388/391 LONG-STALE burden is not newsworthy.
- **Do NOT confuse ghost updates with live builders.** A file touched by a cron watchdog with "re-verified empirically" body text is NOT a builder resuming work.
- **Check crontab.** The monitor script may not be scheduled as a cron at all — only `status_hub.py` runs on a timer. Your invocation may be ad-hoc.