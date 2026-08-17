---
name: eni-module-second_brain
description: Operate the ENI Enterprise `second_brain` module (Knowledge Intake) — Knowledge capture/resurfacing engine: nodes+links, spaced repetition, concept query, compounding. Use when working with second_brain in the Enterprise Platform.
---

# Module skill: second_brain

- Category: Knowledge Intake (priority 1)
- Version: 1.0.0
- Purpose: Knowledge capture/resurfacing engine: nodes+links, spaced repetition, concept query, compounding.

## What it does
Second Brain module — a knowledge capture & resurfacing engine.

Grounded in three real pulled JE Van Clief transcripts:

  * "Your Second Brain Is Not a Notes App" (-CUsfao6m7E)  — a second brain
    links ideas and carries metadata; plain storage becomes a "graveyard".
  * "Van Squared: A Free Local AI Model Labeled a 26-Year Archive"
    (mme027WZhgo) — a labeled long-term archive stays searchable/compounds.
  * "AI Since 2011: The Ideas That Outlive Every Model" (lDXCkx3Nla8) — ideas
    and first principles outlive any single model or tool.

Export surface:
  * SecondBrain — the capture/link/resurface/query/compounding engine.
  * Entry       — a single captured node with metadata + review state.
  * SecondBrainModule — the ENI platform Module wrapper.
  * create_second_brain_module(c

## Key API (facade methods on the @module class)
- build_compounding_report\n- capture\n- health_check\n- initialize\n- link_ideas\n- query_concept\n- resurface\n- shutdown

## Use
Import via:
```python
from enterprise.modules.second_brain import create_second_brain_module
m = create_second_brain_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/second_brain/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
