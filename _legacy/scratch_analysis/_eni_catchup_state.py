#!/usr/bin/env python3
"""Inventory the ENI catch-up build state."""
import json, os, csv

REPO = "/home/hunter/Desktop/Enterprise Builder/enterprise"
DATA = os.path.join(REPO, "data")

# 1) Ledger
manifest_path = os.path.join(DATA, "build", "manifest.json")
with open(manifest_path) as f:
    manifest = json.load(f)

print("=== MANIFEST TOP-LEVEL KEYS ===")
print(list(manifest.keys()))
built = manifest.get("built_modules", [])
print(f"built_modules count: {len(built)}")
if isinstance(built, list):
    print("built_modules sample:", built[:20])
else:
    print("built_modules type:", type(built))

transcripts = manifest.get("transcripts", {})
print("\n=== TRANSCRIPTS by channel ===")
for ch, chmap in transcripts.items():
    statuses = {}
    for vid, rec in (chmap.items() if isinstance(chmap, dict) else []):
        st = rec.get("status", "?")
        statuses[st] = statuses.get(st, 0) + 1
    print(f"  {ch}: {dict(statuses)}  total={len(chmap) if isinstance(chmap, dict) else 0}")

print("\n=== TRANSCRIPT DIRS (on disk) ===")
tdir = os.path.join(DATA, "transcripts")
for ch in sorted(os.listdir(tdir)):
    full = os.path.join(tdir, ch)
    if os.path.isdir(full):
        md = [f for f in os.listdir(full) if f.endswith(".md")]
        csvs = [f for f in os.listdir(full) if f.endswith(".csv")]
        print(f"  {ch}: md={len(md)} csvs={csvs}")
        for c in csvs:
            cp = os.path.join(full, c)
            with open(cp) as f:
                rows = list(csv.DictReader(f))
            if rows:
                print(f"      {c}: {len(rows)} rows; cols={list(rows[0].keys())}")
