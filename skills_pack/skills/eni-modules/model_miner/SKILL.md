---
name: eni-module-model_miner
description: Operate the ENI Enterprise `model_miner` module (Legacy Core) — Enterprise Model Miner OS Module — scan/rip local model training into the KB. Use when working with model_miner in the Enterprise Platform.
---

# Module skill: model_miner

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: Enterprise Model Miner OS Module — scan/rip local model training into the KB.

## What it does
Enterprise Model Miner OS Module — scan/rip local model training into the KB.

Turns LO's idea into a first-class enterprise module: scan local models that
have training worth using, connect to each, "rip" their trained knowledge into
the local knowledge base, and expose each model to Hermes via a local MCP-style
tool + LSP note. Runs as part of the enterprise platform lifecycle (initialize /
health_check / shutdown) and can be booted as an infinite ever-expanding loop.

Data flow (all local-first, no cloud egress unless the chosen model is a local
endpoint):
  scan  -> discover local models (ollama, local OpenAI-compat, HF cache)
  rip   -> probe each chat-capable model with a curated topic battery
  store -> save each answer to the KB (deduplicated, tagged, provenance)
  serve -> registe

## Key API (facade methods on the @module class)
- facade\n- health_check\n- initialize\n- shutdown

## Use
Import via:
```python
from enterprise.modules.model_miner import create_model_miner_module
m = create_model_miner_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/model_miner/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
