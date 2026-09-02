#!/usr/bin/env python3
"""Cross-check: every .md on disk must have a manifest entry; list orphans."""
import json, os

REPO = "/home/hunter/Desktop/Enterprise Builder/enterprise"
DATA = os.path.join(REPO, "data")
with open(os.path.join(DATA, "build", "manifest.json")) as f:
    manifest = json.load(f)
transcripts = manifest.get("transcripts", {})

tdir = os.path.join(DATA, "transcripts")
orphans = []
total_md = 0
for ch in sorted(os.listdir(tdir)):
    full = os.path.join(tdir, ch)
    if not os.path.isdir(full):
        continue
    for fn in sorted(os.listdir(full)):
        if not fn.endswith(".md"):
            continue
        total_md += 1
        vid = fn[:-3]
        rec = transcripts.get(ch, {}).get(vid)
        if rec is None:
            orphans.append((ch, vid, "NO MANIFEST ENTRY"))
        elif "status" not in rec:
            orphans.append((ch, vid, "MANIFEST ENTRY WITHOUT status"))

print(f"Total .md files on disk: {total_md}")
print(f"Orphan .md files (no manifest status): {len(orphans)}")
for ch, vid, why in orphans[:50]:
    print(f"  [{ch}] {vid} | {why}")

# print manifest note / scan summary
print("\n=== SCAN.JSON SUMMARY ===")
spath = os.path.join(DATA, "build", "scan.json")
if os.path.exists(spath):
    with open(spath) as f:
        scan = json.load(f)
    if isinstance(scan, dict):
        print("scan keys:", list(scan.keys()))
        for k, v in scan.items():
            if isinstance(v, (int, str)):
                print(f"  {k}: {v}")
            elif isinstance(v, list):
                print(f"  {k}: list[{len(v)}]")
print("\n=== PULL.LOG ===")
pulllog = os.path.join(DATA, "transcripts", "pull.log")
if os.path.exists(pulllog):
    with open(pulllog) as f:
        print(f.read())