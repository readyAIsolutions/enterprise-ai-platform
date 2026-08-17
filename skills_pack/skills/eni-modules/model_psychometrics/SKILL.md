---
name: eni-module-model_psychometrics
description: Operate the ENI Enterprise `model_psychometrics` module (Domain) — Probe/evaluate model reasoning attributes (psychometric-style evals). Use when working with model_psychometrics in the Enterprise Platform.
---

# Module skill: model_psychometrics

- Category: Domain (priority 4)
- Version: 1.0.0
- Purpose: Probe/evaluate model reasoning attributes (psychometric-style evals).

## What it does
Enterprise Model Psychometrics OS Module — audit the trait profile of AI
models with validated psychometric scales.

Grounded in JEVanClief's "ethics engine" / "becoming an AI psychologist"
pipeline (data/transcripts/JEVanClief/UGyTimVObus.md and Wtf6E-fwuwI.md): a
data pipeline that administers validated personality / psychometric scales
(right-wing authoritarianism, moral foundations, social dominance, Rosenberg
self-esteem) across AI models, personas, model variations and providers to tell
you where a model "lands" on moral foundations / authoritarianism / personality
dimensions.

Module design (mirroring the transcript's own engineering notes):
  * Scales are data — name, description, citation, Likert response range,
    item text, reverse-score flags — and users can select built-ins o

## Key API (facade methods on the @module class)
- health_check\n- initialize\n- registry\n- runner\n- set_event_bus\n- shutdown

## Use
Import via:
```python
from enterprise.modules.model_psychometrics import create_model_psychometrics_module
m = create_model_psychometrics_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/model_psychometrics/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
