import json, os
from collections import Counter
REPO = "/home/hunter/Desktop/Enterprise Builder/enterprise"
MANIFEST = os.path.join(REPO, "data/build/manifest.json")
with open(MANIFEST) as f:
    manifest = json.load(f)
ledger = manifest.get("transcripts", {})
print("Channel keys in manifest.transcripts:", list(ledger.keys()))
print("built_modules count:", len(manifest.get("built_modules", [])))
for ch, d in sorted(ledger.items()):
    c = Counter((rec.get("status") or "MISSING") for rec in d.values())
    print(f"{ch}: total_entries={len(d)} {dict(c)}")