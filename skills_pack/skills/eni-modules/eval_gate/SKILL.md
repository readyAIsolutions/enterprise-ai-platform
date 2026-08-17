---
name: eni-module-eval_gate
description: Operate the ENI Enterprise `eval_gate` module (Legacy Core) — ENI Eval Gate OS Module — automated LLM evaluation gates (local & offline). Use when working with eval_gate in the Enterprise Platform.
---

# Module skill: eval_gate

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: ENI Eval Gate OS Module — automated LLM evaluation gates (local & offline).

## What it does
ENI Eval Gate OS Module — automated LLM evaluation gates (local & offline).

Local, stdlib-only automated evaluation of model output quality using fully
deterministic lexical/heuristic metrics (no external model or service calls).
Mirrors the ``model_security`` philosophy: every metric is a regex- and
term-overlap-based function that can be unit tested offline.

Metrics implemented (computed from text alone):
  - AnswerRelevancy    — relevance proxy via answer/question token overlap.
  - Faithfulness       — groundedness of the answer relative to a source.
  - ToxicityDetector   — banned-word lexicon scan for profane content.
  - HallucinationProxy — fact-consistency proxy (unsupported-claim fraction).
  - RefusalDetector    — refusal / evasion phrasing detection.
  - JailbreakGuard     — 

## Key API (facade methods on the @module class)
(module-level API)

## Use
Import via:
```python
from enterprise.modules.eval_gate import create_eval_gate_module
m = create_eval_gate_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/eval_gate/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
