#!/usr/bin/env python3
"""Comprehensive: any on-disk .md not resolved in ledger, across all channels."""
import json, os, csv

REPO = "/home/hunter/Desktop/Enterprise Builder/enterprise"
MANIFEST = os.path.join(REPO, "data/build/manifest.json")
TRANS = os.path.join(REPO, "data/transcripts")

with open(MANIFEST) as f:
    led = json.load(f)
tr = led.get("transcripts", {})

total_md = 0
unresolved = []
for ch_dir in sorted(os.listdir(TRANS)):
    cd = os.path.join(TRANS, ch_dir)
    if not os.path.isdir(cd):
        continue
    ledger_ch = tr.get(ch_dir, {})
    for fname in os.listdir(cd):
        if not fname.endswith(".md"):
            continue
        vid = fname[:-3]
        total_md += 1
        if vid not in ledger_ch:
            unresolved.append((ch_dir, vid, "NOT-IN-LEDGER"))
        else:
            info = ledger_ch[vid]
            s = info.get("status") if isinstance(info, dict) else "?"
            if s not in ("built", "evaluated-skip"):
                unresolved.append((ch_dir, vid, "status=" + repr(s)))

print("total on-disk .md files:", total_md)
print("total unresolved .md:", len(unresolved))
by_ch = {}
for ch, v, why in unresolved:
    by_ch.setdefault(ch, []).append((v, why))
for ch, items in sorted(by_ch.items()):
    print("\n== ", ch, len(items))
    for v, why in items[:5]:
        print("    ", v, why)