#!/usr/bin/env python3
"""Compare TwoMinutePapers: ledger vs index vs on-disk .md files."""
import json, os, csv

REPO = "/home/hunter/Desktop/Enterprise Builder/enterprise"
MANIFEST = os.path.join(REPO, "data/build/manifest.json")
ch = "TwoMinutePapers"
cd = os.path.join(REPO, "data/transcripts", ch)

with open(MANIFEST) as f:
    led = json.load(f)
tr = led["transcripts"].get(ch, {})

# on-disk .md files
md_files = set()
for fname in os.listdir(cd):
    if fname.endswith(".md"):
        md_files.add(fname[:-3])

# index rows
csvp = os.path.join(cd, "_index.csv")
idx = {}
if os.path.exists(csvp):
    with open(csvp) as f:
        for row in csv.DictReader(f):
            idx[row.get("video_id", "")] = row.get("status", "")

print("ledger entries:", len(tr))
print("index rows:", len(idx), "index ok:", sum(1 for s in idx.values() if s == "ok"))
print("on-disk .md files:", len(md_files))

# For each orphan md (not in index), is it in ledger?
orphans = sorted(md_files - set(idx.keys()))
print("\norphan .md count (in .md but not index):", len(orphans))
in_ledger_resolved = 0
in_ledger_unresolved = 0
not_in_ledger = []
for v in orphans:
    if v in tr:
        s = tr[v].get("status") if isinstance(tr[v], dict) else "?"
        if s in ("built", "evaluated-skip"):
            in_ledger_resolved += 1
        else:
            in_ledger_unresolved += 1
            not_in_ledger.append((v, s, tr[v].get("title", "") if isinstance(tr[v], dict) else ""))
    else:
        not_in_ledger.append((v, "NOT-IN-LEDGER", ""))

print("orphan mds resolved in ledger:", in_ledger_resolved)
print("orphan mds in ledger but unresolved:", in_ledger_unresolved)
print("\nSample NOT-in-ledger / unresolved orphans:")
for v, s, title in not_in_ledger[:20]:
    print("   ", v, s, title)

# Also: md files in index NOT present on disk (index says ok but file missing)
idx_ok_missing = [v for v, s in idx.items() if s == "ok" and v not in md_files]
print("\nindex-ok rows missing .md on disk:", len(idx_ok_missing))