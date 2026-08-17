---
name: eni-module-prompt_context
description: Operate the ENI Enterprise `prompt_context` module (Legacy Core) — Prompt & Context Management OS Module Use when working with prompt_context in the Enterprise Platform.
---

# Module skill: prompt_context

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: Prompt & Context Management OS Module

## What it does
Prompt & Context Management OS Module
======================================

Enterprise-grade module for prompt lifecycle management, context orchestration,
optimization, token budgeting, evaluation, and quality gating.

Modules:
- prompt_registry: Prompt definition, versioning, lifecycle, rollback
- context_manager: Hierarchical context blocks with priorities and TTLs
- optimizer: Deduplication, compression, conflict detection, summarization
- token_budget: Token allocation, truncation, caching, model routing
- evaluator: Multi-metric evaluation, hallucination detection, grading
- quality_gates: Pre-execution checks to block/warn on quality issues

## Key API (facade methods on the @module class)
- health_check\n- initialize\n- shutdown

## Use
Import via:
```python
from enterprise.modules.prompt_context import create_prompt_context_module
m = create_prompt_context_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/prompt_context/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
