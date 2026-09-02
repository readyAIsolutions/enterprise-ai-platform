import json, os, csv, glob

REPO = "/home/hunter/Desktop/Enterprise Builder/enterprise"
MB = os.path.join(REPO, "data/build/manifest.json")
with open(MB) as f:
    manifest = json.load(f)
tx = manifest.get("transcripts", {})

# Enumerate all statuses present in ledger
statuses = {}
not_in_ledger = []
for ch, videos in tx.items():
    for vid, rec in videos.items():
        st = rec.get("status")
        statuses[ch] = statuses.get(ch, {})
        statuses[ch][st] = statuses[ch].get(st, 0) + 1

print("Per-channel ledger status counts:")
for ch, m in sorted(statuses.items()):
    print(f"  {ch}: {m}")

# Channel-to-video counts in ledger
print("\nLedger channels:", list(tx.keys()))

# Which eligible are NOT in ledger at all?
eligible = []
for csv_path in glob.glob(os.path.join(REPO, "data/transcripts", "*", "_index.csv")):
    ch = os.path.basename(os.path.dirname(csv_path))
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            vid = (row.get("video_id") or "").strip()
            status = (row.get("status") or "").strip()
            title = (row.get("title") or "").strip()
            if status == "ok" and vid:
                md = os.path.join(REPO, "data/transcripts", ch, vid + ".md")
                if os.path.exists(md):
                    eligible.append((ch, vid, title))

missing = []
for ch, vid, title in eligible:
    if tx.get(ch, {}).get(vid) is None:
        missing.append((ch, vid, title))

print("\nEligible NOT in ledger at all:", len(missing))
for ch, vid, title in missing[:50]:
    print(f"  [{ch}] {vid} | {title[:70]}")