---
name: eni-module-paper_feeds
description: Operate the ENI Enterprise `paper_feeds` module (Knowledge Intake) — Daily research feeds (arXiv/HF/PwC/AlphaXiv), dedup, tagging, JSON/CSV export. Use when working with paper_feeds in the Enterprise Platform.
---

# Module skill: paper_feeds

- Category: Knowledge Intake (priority 1)
- Version: 2.0.0
- Purpose: Daily research feeds (arXiv/HF/PwC/AlphaXiv), dedup, tagging, JSON/CSV export.

## What it does
Paper-feeds module — daily AI research digests (arXiv/HF/PwC/AlphaXiv).

Rebuilt v2.0: structured ``Paper`` model, primary arXiv Atom API ingestion with
HTML fallback, change detection (only *new* papers surface in daily digests),
relevance tagging for the enterprise, and machine-readable JSON/CSV exports —
WiFi-safe, retry/backoff, gentle pacing.

Writes markdown + JSON + CSV under ``data/papers/<date>/<feed>.*`` plus a
persistent ``data/papers/index.json`` for change detection.

## Key API (facade methods on the @module class)
- health_check\n- initialize\n- pull_one\n- pull_today\n- seen_count\n- shutdown

## Use
Import via:
```python
from enterprise.modules.paper_feeds import create_paper_feeds_module
m = create_paper_feeds_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/paper_feeds/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
