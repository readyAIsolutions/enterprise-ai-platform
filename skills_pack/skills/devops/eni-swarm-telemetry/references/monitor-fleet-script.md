# The on-disk fleet monitor entry point: `monitor_fleet.py`

The real cron entry point for the fleet-status pulse on this box is a Python
script at `/home/hunter/Commander/eni_swarm/monitor_fleet.py` (NOT the skill's
`heartbeat.py` — the production floor runs the standalone script). Run it in
its directory: `cd /home/hunter/Commander/eni_swarm && python3 monitor_fleet.py`.

## What it does (confirmed behavior, Aug 2026)
- Scans builder STATUS files from the `builds/` subdir (falls back to cwd) via
  glob `STATUS_BUILDER_*.md` — all 50 builders expected.
- Parses each file's state token robustly: `[IN-PROGRESS]` line-prefixed,
  `# STATE: IN-PROGRESS`, `[BLOCKED]`, `[DONE]`, `[IDLE]`. Falls back to the
  first non-blank line's `[TOKEN]` if no marker match.
- Maps state: BLOCKED→BLOCKED, IN-(_)PROGRESS→IN-PROGRESS, else DONE.
- Reads `HEARTBEAT_ALERTS.md` for `- BUILDER_(\d+)` lines and forces those
  builders to BLOCKED.
- Extracts `verified=`, `blocker=`, `next=` key:value lines.
- Writes one line per builder to `HEARTBEAT_LEDGER.md` and exits 0.

## Pitfalls / gotchas observed
- **Does NOT create `HEARTBEAT_ALERTS.md`** — it only reads it ("optionally
  rewrite alerts, keep as-is"). A missing alerts file is normal, not an error;
  it means zero builders are force-blocked.
- **Zero-padding mismatch:** the STATUS files are `STATUS_BUILDER_04.md`
  (zero-padded) but the ledger emits `BUILDER_4` (no pad). Do not flag this
  as a discrepancy in the report — it's inherent to the script. To cross-check
  mtimes, derive the number from the glob filename, never reconstruct it
  (`int(re.search(r"STATUS_BUILDER_(\d+)\.md", basename(f)).group(1))`).
- **Number missing from the ledger usually = a 0-byte/blank STATUS file,**
  e.g. BUILDER_20 was absent with `wc -c` = 0 and the crash guard skips it.
  Not counted in the ledger total (49 entries, not 50).
- `verified=`/`blocker=`/`next=` are optional; absent key shows as
  `verified=unknown blocker=unknown next=unknown`.

## Report-reading notes for the pulse
- On a parked/dormant fleet, residual `[IN-PROGRESS]` markers persist in
  files that are weeks old — do NOT report them as live work. Lead with file
  mtime freshness (min since last write) for the LIVE/DORMANT verdict, and
  call out the freshest file's IDLE/blocker/next as "what would wake the floor".
- **Corroborate DORMANT with process liveness, not just mtime.** Old STATUS
  files prove the files weren't touched, but they can't distinguish "parked"
  from "actively building without re-writing its status file." Before calling
  the floor parked, run `pgrep -af` for builder/controller procs
  (`eni_swarm|BUILDER|master_driver|orchestrat`) AND confirm no
  `STATUS_BUILDER_*.md` was modified in the last 24h (`find ... -mmin -1440`).
  If both come back empty, the verdict is solid DORMANT ("fleet is parked, not
  failing") rather than "unknown/possibly live." (Confirmed 2026-08-16: zero
  matching procs + zero fresh files → clean DORMANT on a weeks-stale fleet.)
- `[BLOCKED]` builders are frequently just *unassigned* (no task dispatched),
  not a fault — read the file body before raising it.
- **To READ a builder status file body, use the ZERO-PADDED on-disk name** —
  files exist as `STATUS_BUILDER_04.md`, NOT `STATUS_BUILDER_4.md`. Opening an
  unpadded name raises `FileNotFoundError`. This trips easily when the number
  came from the LEDGER (which emits `BUILDER_4`, no pad) or from memory. Always
  build the path with the number zero-padded to 2 digits
  (`STATUS_BUILDER_{num:02d}.md`) when reading a body to inspect a
  `[BLOCKED]`/`[IDLE]` reason or `blocker=` before raising an alert.