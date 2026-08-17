---
name: eni-module-ai_memory_hierarchy
description: Operate the ENI Enterprise `ai_memory_hierarchy` module (Knowledge Intake) — Layered memory model for agents (working/short/long) from AI-memory transcripts. Use when working with ai_memory_hierarchy in the Enterprise Platform.
---

# Module skill: ai_memory_hierarchy

- Category: Knowledge Intake (priority 1)
- Version: 1.0.0
- Purpose: Layered memory model for agents (working/short/long) from AI-memory transcripts.

## What it does
AI Memory Hierarchy — an enterprise module modeling the AI memory hierarchy.

Grounded in the JEVanClief transcript *"How a 1953 Word Game Explains AI
Memory"* (https://www.youtube.com/watch?v=S3fXSc5z2n4). The transcript maps the
hardware memory hierarchy (speed-vs-capacity tradeoff, locality-based staging)
onto AI memory:

  - model weights  ~ ROM            (read-only, fixed at training time)
  - context window ~ working memory / RAM (temporary, per-conversation)
  - system prompt  ~ firmware       (operating parameters)
  - retrieved ctx  ~ disk -> RAM on demand (query-driven loading)
  - persistent mem ~ selectively loaded summaries kept between conversations

Key insight implemented here: in AI, code and data are the *same* — everything
is text processed identically, so a single stri

## Key API (facade methods on the @module class)
- demote\n- health\n- health_check\n- hierarchy\n- initialize\n- insert\n- lock_weights\n- promote\n- retrieve\n- set_event_bus\n- set_prompt\n- set_weights\n- shutdown\n- tier_summary

## Use
Import via:
```python
from enterprise.modules.ai_memory_hierarchy import create_ai_memory_hierarchy_module
m = create_ai_memory_hierarchy_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/ai_memory_hierarchy/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
