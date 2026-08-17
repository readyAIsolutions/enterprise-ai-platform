---
name: eni-module-ai_systems_thinking
description: Operate the ENI Enterprise `ai_systems_thinking` module (Knowledge Intake) — Feedback loops, coupling and systems lens for AI feature design. Use when working with ai_systems_thinking in the Enterprise Platform.
---

# Module skill: ai_systems_thinking

- Category: Knowledge Intake (priority 1)
- Version: 1.0.0
- Purpose: Feedback loops, coupling and systems lens for AI feature design.

## What it does
ai_systems_thinking module — systems-thinking evaluation for AI system designs.

Grounded in the pulled JE Van Clief transcripts:

* ``NWyTsKTKka8`` — *Systems Thinking for People Who Build With AI*
* ``jjV1ckgPzI0`` — *I Charged $2000 For This AI Lecture (And I Underpriced It)*
* ``g3eWjeZPFiM`` — *Life, Liberty and the pursuit of Artificial Intelligence*

The module exposes a deterministic, network-free evaluation engine
(:class:`~enterprise.modules.ai_systems_thinking.assessor.SystemsThinker`)
that scores an AI system design across systems-thinking dimensions and emits:
per-dimension scores, identified feedback loops (including implicit ones found
by walking the coupling graph), leverage points, coupling analysis, risks of
unintended consequences, and an overall systems-health read.

## Key API (facade methods on the @module class)
- engine\n- evaluate\n- health_check\n- initialize\n- shutdown

## Use
Import via:
```python
from enterprise.modules.ai_systems_thinking import create_ai_systems_thinking_module
m = create_ai_systems_thinking_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/ai_systems_thinking/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
