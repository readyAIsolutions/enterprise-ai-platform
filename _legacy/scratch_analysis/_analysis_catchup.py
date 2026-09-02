import json, os, csv, glob

REPO = "/home/hunter/Desktop/Enterprise Builder/enterprise"
MB = os.path.join(REPO, "data/build/manifest.json")
with open(MB) as f:
    manifest = json.load(f)

built = set(manifest.get("built_modules", []))
tx = manifest.get("transcripts", {})
print("BUILT_MODULES count:", len(built))

# Gather eligible from _index.csv (status==ok AND .md exists)
eligible = []  # (channel, video_id, title)
all_pulled = []
total_ok = 0
for csv_path in glob.glob(os.path.join(REPO, "data/transcripts", "*", "_index.csv")):
    ch = os.path.basename(os.path.dirname(csv_path))
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            vid = (row.get("video_id") or "").strip()
            status = (row.get("status") or "").strip()
            title = (row.get("title") or "").strip()
            all_pulled.append((ch, vid, title, status))
            if status == "ok" and vid:
                md = os.path.join(REPO, "data/transcripts", ch, vid + ".md")
                if os.path.exists(md):
                    eligible.append((ch, vid, title))

print("eligible (ok+md):", len(eligible))
print("index rows total:", len(all_pulled))

# Ledger statuses for each video_id
ledger_status = {}
for ch, videos in tx.items():
    for vid, rec in videos.items():
        ledger_status[(ch, vid)] = rec.get("status")

# compute unbuilt
unbuilt = []
resolved = 0
for ch, vid, title in eligible:
    st = ledger_status.get((ch, vid))
    if st in ("built", "evaluated-skip"):
        resolved += 1
        continue
    unbuilt.append((ch, vid, title, st))

print("\nRESOLVED (built or eval-skip) among eligible:", resolved)
print("UNBUILT candidates:", len(unbuilt))
for ch, vid, title, st in unbuilt:
    print(f"  [{ch}] {vid} | st={st} | {title[:80]}")