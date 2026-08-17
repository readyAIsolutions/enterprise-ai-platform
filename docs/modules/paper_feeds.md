# Module: `paper_feeds`

- Category: Knowledge Intake · priority 1
- Version: 2.0.0
- Purpose: Daily research feeds (arXiv/HF/PwC/AlphaXiv), dedup, tagging, JSON/CSV export.
- Skill: `eni-module-paper_feeds` (ICM stages) in skills_pack/skills/eni-modules/paper_feeds/

## What it does
Paper-feeds module — daily AI research digests (arXiv/HF/PwC/AlphaXiv).

Rebuilt v2.0: structured ``Paper`` model, primary arXiv Atom API ingestion with
HTML fallback, change detection (only *new* papers surface in daily digests),
relevance tagging for the enterprise, and machine-readable JSON/CSV exports —
WiFi-safe, retry/backoff, gentle pacing.

Writes markdown + JSON + CSV under ``data/papers/<date>/<feed>.*`` plus a
persistent ``data/papers/index.json`` for change detection.

## Key API (facade methods)
health_check, initialize, pull_one, pull_today, seen_count, shutdown

## Tests
```bash
python3 -m pytest modules/paper_feeds/tests -q
```

## Import
```python
from enterprise.modules.paper_feeds import create_paper_feeds_module
m = create_paper_feeds_module()
```
