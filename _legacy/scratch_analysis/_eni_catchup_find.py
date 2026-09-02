#!/usr/bin/env python3
"""Find on-disk transcript .md files whose video_id is NOT resolved in ledger."""
import json, os, csv

REPO = "/home/hunter/Desktop/Enterprise Builder/enterprise"
MANIFEST = os.path.join(REPO, "data/build/manifest.json")
TRANS = os.path.join(REPO, "data/transcripts")

with open(MANIFEST) as f:
    led = json.load(f)
tr = led.get("transcripts", {})

unres = []
for ch_dir in sorted(os.listdir(TRANS)):
    cd = os.path.join(TRANS, ch_dir)
    if not os.path.isdir(cd):
        continue
    csvp = os.path.join(cd, "_index.csv")
    ledger_ch = tr.get(ch_dir, {})
    seen = {}
    for vid, info in ledger_ch.items():
        st = info.get("status") if isinstance(info, dict) else "?"
        seen[vid] = st
    if not os.path.exists(csvp):
        continue
    with open(csvp) as f:
        for row in csv.DictReader(f):
            st = row.get("status", "")
            vid = row.get("video_id", "")
            if st != "ok" or not vid:
                continue
            md = os.path.join(cd, vid + ".md")
            if not os.path.exists(md):
                continue
            if vid not in seen:
                unres.append((ch_dir, vid, row.get("title", ""), "NOT IN LEDGER"))
            else:
                lst = seen[vid]
                if lst in ("built", "evaluated-skip"):
                    continue
                unres.append((ch_dir, vid, row.get("title", ""), "ledger status=" + repr(lst)))

print("Total unresolved on-disk ok transcripts:", len(unres))
for u in unres:
    print("   ", u)

# Orphan .md: a .md that exists but has no _index.csv row
print("\n== .md files with no index row / channel missing from ledger ==")
for ch_dir in sorted(os.listdir(TRANS)):
    cd = os.path.join(TRANS, ch_dir)
    if not os.path.isdir(cd):
        continue
    csvp = os.path.join(cd, "_index.csv")
    idx_vids = set()
    if os.path.exists(csvp):
        with open(csvp) as f:
            for row in csv.DictReader(f):
                idx_vids.add(row.get("video_id", ""))
    for fname in sorted(os.listdir(cd)):
        if fname.endswith(".md"):
            vid = fname[:-3]
            if vid not in idx_vids:
                print("   ORPHAN-MD", ch_dir + "/" + fname)
            elif ch_dir not in tr:
                print("   CHANNEL-NOT-IN-LEDGER", ch_dir + "/" + fname)