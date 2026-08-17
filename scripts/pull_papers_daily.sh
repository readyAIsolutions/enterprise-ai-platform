#!/usr/bin/env bash
# ENI Paper-feeds daily digest runner.
# Pulls all feeds (arXiv/HF/PwC/AlphaXiv) into enterprise/data/papers/<date>/,
# WiFi-safe paced. Used by the daily cron.
set -euo pipefail

REPO="/home/hunter/Desktop/Enterprise Builder/enterprise"
PARENT="/home/hunter/Desktop/Enterprise Builder"
OUT_DIR="${1:-$REPO/data/papers}"

export PYTHONPATH="$PARENT"
cd "$REPO"

python3 - "$OUT_DIR" <<'PY'
import json, sys
from enterprise.modules.paper_feeds.papers import pull_all_feeds
out = sys.argv[1]
res = pull_all_feeds(out, enable_dedup=True)
print(json.dumps({"total": res["total"], "new": res["new"],
                  "per_feed": [{"feed": r["feed"], "got": r["got"],
                                "new": r["new"], "error": r.get("error")}
                               for r in res["results"]]}, indent=2))
PY
