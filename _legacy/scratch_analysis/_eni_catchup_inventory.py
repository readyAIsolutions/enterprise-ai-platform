"""ENI catch-up inventory: compute eligible / unbuilt / resolved state."""
import json, os, csv, sys

REPO = "/home/hunter/Desktop/Enterprise Builder/enterprise"
TRANS = os.path.join(REPO, "data", "transcripts")
MANIFEST = os.path.join(REPO, "data", "build", "manifest.json")

with open(MANIFEST) as f:
    manifest = json.load(f)

ledger = manifest.get("transcripts", {})
built_modules = manifest.get("built_modules", [])

def load_index(csv_path):
    rows = []
    with open(csv_path, newline='', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows

channels = sorted([d for d in os.listdir(TRANS)
                   if os.path.isdir(os.path.join(TRANS, d)) and not d.endswith('.7z')])

print("CHANNELS:", channels)
print()

all_eligible = 0
all_unbuilt = []
all_channel_counts = {}

for ch in channels:
    idx_path = os.path.join(TRANS, ch, "_index.csv")
    if not os.path.exists(idx_path):
        print(f"[{ch}] NO _index.csv -- skipping")
        continue
    rows = index = idx = load_index(idx_path)
    eligible = []
    for r in rows:
        vid = (r.get("video_id") or "").strip()
        status = (r.get("status") or "").strip()
        if status != "ok":
            continue
        md = os.path.join(TRANS, ch, vid + ".md")
        if not os.path.exists(md):
            continue
        eligible.append((vid, r.get("title", "")))
    # manifest-ledger status for this channel
    ch_ledger = ledger.get(ch, {})
    unbuilt = []
    built = []
    skipped = []
    for vid, title in eligible:
        rec = ch_ledger.get(vid, {})
        st = rec.get("status") if isinstance(rec, dict) else None
        if st == "built":
            built.append(vid)
        elif st == "evaluated-skip":
            skipped.append(vid)
        else:
            unbuilt.append((vid, title))
    all_channel_counts[ch] = (len(eligible), len(built), len(skipped), len(unbuilt))
    all_eligible += len(eligible)
    all_unbuilt.extend(unbuilt)
    print(f"[{ch}] eligible={len(eligible)} built={len(built)} skipped={len(skipped)} UNBUILT={len(unbuilt)}")
    for vid, title in unbuilt:
        print(f"    UNBUILT {vid}: {title[:90]}")

print()
print(f"TOTAL eligible pulled: {all_eligible}")
print(f"TOTAL unresolved/unbuilt: {all_unbuilt}")
print(f"built_modules count in ledger: {len(built_modules)}")