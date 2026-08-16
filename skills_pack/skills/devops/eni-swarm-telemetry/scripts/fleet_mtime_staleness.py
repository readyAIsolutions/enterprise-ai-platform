#!/usr/bin/env python3
"""One-shot mtime-staleness probe for the ENI swarm fleet.

When a fleet-status cron fires and the regenerated ledger is dominated by rows,
the ledger alone does NOT prove activity. This probe classifies every builder
status file by its last-modified age (in hours) so you can instantly tell which
builders are actually live vs. stale/dormant.

Usage:  python3 fleet_mtime_staleness.py [BUILDS_DIR]
Default build dir: <this file's parent>/../builds

Output: lists the freshest and stalest builders with ages in hours, plus the
total count. The key pattern it makes legible:
  - ~388h (~16 days) across nearly all files  -> fleet DORMANT
  - exactly 1 fresh file (<24h)               -> only that builder is live
  - a regenerated ledger is NOT a sign of activity
"""
import glob, os, re, sys, datetime

base = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "builds")
base = os.path.abspath(base)

now = datetime.datetime.now().astimezone()
files = glob.glob(os.path.join(base, "STATUS_BUILDER_*.md"))
if not files:
    print("no STATUS_BUILDER_*.md found in", base)
    sys.exit(0)

rows = []  # (builder_num, age_hours)
for f in files:
    m = re.search(r"BUILDER_(\d+)\.md", f)
    if not m:
        continue
    n = int(m.group(1))
    mt = datetime.datetime.fromtimestamp(os.path.getmtime(f)).astimezone()
    age_h = (now - mt).total_seconds() / 3600.0
    rows.append((n, age_h))
rows.sort(key=lambda r: r[1])

print("now:", now.isoformat())
print("total builder status files:", len(rows))
fresh = [r for r in rows if r[1] < 24]
stale = [r for r in rows if r[1] >= 24]
print(f"fresh (<24h): {len(fresh)}  |  stale (>=24h): {len(stale)}")

print("\n=== FRESHEST 6 ===")
for n, age in rows[:6]:
    print(f"  BUILDER_{n:02d}  age={age:7.1f}h")
print("\n=== STALEST 6 ===")
for n, age in rows[-6:]:
    print(f"  BUILDER_{n:02d}  age={age:7.1f}h")

if fresh and not stale:
    print("\nVERDICT: all builders fresh")
elif len(fresh) == 1 and len(stale) > 0:
    print(f"\nVERDICT: singleton live builder (BUILDER_{fresh[0][0]:02d}), "
          f"rest dormant ({stale[-1][1]:.0f}h old)")
elif not fresh and stale:
    print("\nVERDICT: fleet fully dormant")
else:
    print("\nVERDICT: mixed — several live, several dormant")
