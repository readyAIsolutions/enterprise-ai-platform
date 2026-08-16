#!/usr/bin/env python3
"""Self-contained fleet staleness probe for the ENI parallel-build swarm.

Deterministic readiness read of /home/hunter/Commander/eni_swarm/builds/
STATUS_BUILDER_*.md without depending on any bundled telemetry script (which may
be ENI-compressed and not at the expected on-disk path). Run AFTER monitor_fleet.py
has regenerated HEARTBEAT_LEDGER.md.

Emits freshness buckets (LIVE / RECENT / STALE), oldest/avg/max age, and flags
empty-file (crash-guard) cases so a file-count vs ledger-count mismatch is not
misreported as a vanished builder.

Usage:  python3 fleet_staleness_probe.py [builds_dir]
Default builds_dir: /home/hunter/Commander/eni_swarm/builds
"""
import os, re, sys, time, glob
from datetime import datetime

BUILDS_DIR = sys.argv[1] if len(sys.argv) > 1 else \
    "/home/hunter/Commander/eni_swarm/builds"

now = time.time()
rows = []
for f in sorted(glob.glob(os.path.join(BUILDS_DIR, "STATUS_BUILDER_*.md"))):
    m = re.search(r"STATUS_BUILDER_(\d+)\.md", f)
    num = int(m.group(1))
    mt = os.path.getmtime(f)
    age_days = (now - mt) / 86400.0
    state = "?"
    try:
        with open(f) as fp:
            for line in fp:
                ul = line.upper()
                if re.search(r"IN[-_ ]?PROGRESS", ul):
                    state = "IN-PROGRESS"; break
                if "BLOCKED" in ul:
                    state = "BLOCKED"; break
    except OSError:
        state = "ERR"
    rows.append((num, state, age_days,
                 datetime.fromtimestamp(mt).strftime("%m-%d %H:%M"),
                 os.path.getsize(f)))

rows.sort()

fresh   = [r for r in rows if r[2] < 1]      # <1 day  -> LIVE (real activity)
recent  = [r for r in rows if 1 <= r[2] < 7] # 1-7 d   -> possibly active
stale   = [r for r in rows if r[2] >= 7]     # >=7 d   -> dormant/stale
zero    = [r for r in rows if r[4] == 0]     # empty file -> crash-guard skip

print(f"BUILDER status files on disk : {len(rows)}")
print(f"  LIVE  (<1 day)  : {len(fresh)} {[r[0] for r in fresh]}")
print(f"  RECENT (1-7 d)  : {len(recent)} {[r[0] for r in recent]}")
print(f"  STALE (>=7 d)   : {len(stale)}   avg_age={sum(r[2] for r in rows)/max(len(rows),1):.1f}d "
      f"max_age={max((r[2] for r in rows), default=0):.1f}d oldest={min((r[3] for r in rows), default='-')}")
print(f"  EMPTY files     : {[r[0] for r in zero]}  <- crash-guard, EXCLUDED from ledger")
print("\nVerdict hints:")
if fresh:
    print("  - LIVE nodes present; treat other IN-PROGRESS flags as possibly stale.")
elif len(rows) and not fresh and any(r[1] in ("IN-PROGRESS", "BLOCKED") for r in rows):
    print("  - NO live node; IN-PROGRESS/BLOCKED flags are STALE ARTIFACTS, not live work.")
    print("  - Fleet is DORMANT/PARKED, not broken. Report as a finding (never [SILENT]).")
# Ready-slot pattern: a recently-updated IDLE builder whose control FIFO is absent.
for f in glob.glob(os.path.join(BUILDS_DIR, "STATUS_BUILDER_*.md")):
    m = re.search(r"BUILDER_(\d+)\.md", f)
    if not m: continue
    if (now - os.path.getmtime(f)) / 86400.0 >= 7: continue  # skip old
    try:
        txt = open(f).read()
    except OSError:
        continue
    if "IDLE" in txt.upper() and "blocker=none" in txt.lower():
        fifo = f"/tmp/eni_ctl_BUILDER_{m.group(1)}"
        print(f"  - READY SLOT: BUILDER_{m.group(1)} updated recently, IDLE, "
              f"FIFO {fifo} exists={os.path.exists(fifo)} (missing=awaiting LO directive)")
