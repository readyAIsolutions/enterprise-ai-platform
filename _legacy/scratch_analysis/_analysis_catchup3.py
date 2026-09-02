import os, csv, glob

REPO = "/home/hunter/Desktop/Enterprise Builder/enterprise"
for csv_path in sorted(glob.glob(os.path.join(REPO, "data/transcripts", "*", "_index.csv"))):
    ch = os.path.basename(os.path.dirname(csv_path))
    counts = {}
    eligible = 0
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            st = (row.get("status") or "").strip()
            vid = (row.get("video_id") or "").strip()
            counts[st] = counts.get(st, 0) + 1
            if st == "ok" and vid and os.path.exists(os.path.join(REPO, "data/transcripts", ch, vid + ".md")):
                eligible += 1
    print(f"{ch}: rows={sum(counts.values())} {counts} eligible_ok_with_md={eligible}")