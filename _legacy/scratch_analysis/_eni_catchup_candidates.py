#!/usr/bin/env python3
"""Compute unbuit candidates: eligible (status==ok + md exists) minus built/evaluated-skip."""
import json, os, csv

REPO = "/home/hunter/Desktop/Enterprise Builder/enterprise"
DATA = os.path.join(REPO, "data")
manifest_path = os.path.join(DATA, "build", "manifest.json")
with open(manifest_path) as f:
    manifest = json.load(f)

built = set(manifest.get("built_modules", []))
transcripts = manifest.get("transcripts", {})
# build a lookup of archived status per (channel, video_id)
def man_status(ch, vid):
    return transcripts.get(ch, {}).get(vid, {}).get("status")

tdir = os.path.join(DATA, "transcripts")

candidates = []
by_channel = {}
for ch in sorted(os.listdir(tdir)):
    full = os.path.join(tdir, ch)
    if not os.path.isdir(full):
        continue
    idx = os.path.join(full, "_index.csv")
    if not os.path.exists(idx):
        continue
    with open(idx) as f:
        rows = list(csv.DictReader(f))
    eligible = []
    for r in rows:
        vid = r["video_id"]
        if r.get("status") != "ok":
            continue
        md = os.path.join(full, vid + ".md")
        if not os.path.exists(md):
            continue
        eligible.append((vid, r.get("title", ""), r.get("duration", ""), r.get("date", "")))
    unresolved = []
    for vid, title, dur, date in eligible:
        st = man_status(ch, vid)
        if st in ("built", "evaluated-skip"):
            continue
        if st is None:
            # not in manifest at all
            unresolved.append((vid, title, dur, date, "not-in-manifest"))
        else:
            unresolved.append((vid, title, dur, date, st))
    by_channel[ch] = (len(eligible), len(unresolved))
    for u in unresolved:
        candidates.append((ch, u[0], u[1], u[2], u[3], u[4]))

print("=== Eligible (status ok + md) vs Unresolved per channel ===")
for ch, (el, un) in by_channel.items():
    print(f"  {ch}: eligible={el} unresolved={un}")

print(f"\n=== TOTAL CANDIDATES (unresolved) = {len(candidates)} ===")
for ch, vid, title, dur, date, st in candidates:
    print(f"  [{ch}] {vid} | {st} | {title[:70]} ({dur}) {date}")
