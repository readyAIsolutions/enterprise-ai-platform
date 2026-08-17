---
name: eni-module-position_addressed_memory
description: Operate the ENI Enterprise `position_addressed_memory` module (Legacy Core) — Position-addressed memory — *folder-as-memory* for AI context. Use when working with position_addressed_memory in the Enterprise Platform.
---

# Module skill: position_addressed_memory

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: Position-addressed memory — *folder-as-memory* for AI context.

## What it does
Position-addressed memory — *folder-as-memory* for AI context.

Grounded in the JEVanClief transcript *"How I Run Creative, Software, and
Business Work as One System"* (https://www.youtube.com/watch?v=hALln9wrrQo).
The transcript contrasts three bets on what memory means for an LLM —
OpenBrain vector embeddings (**content**-addressed), Karpathy's LLM wiki
(**link**-addressed), and **the folder system** (**position**-addressed). This
module implements the position-addressed cascade — a root ``CLAUDE.md`` whose
rules cascade down, per-project ``Context.md`` layered on top, and per-file
convention docs — so "by the time Claude reads the scene, it has already
inherited the brand voice, the production rules, the specific shot list."

The deterministic core lives in
:mod:`enterprise.modules.posi

## Key API (facade methods on the @module class)
- addressing\n- health_check\n- inherited_context\n- initialize\n- resolve\n- resolve_content\n- resolve_link\n- resolve_position\n- set_event_bus\n- shutdown\n- stats\n- store_content\n- store_link\n- store_position

## Use
Import via:
```python
from enterprise.modules.position_addressed_memory import create_position_addressed_memory_module
m = create_position_addressed_memory_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/position_addressed_memory/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
