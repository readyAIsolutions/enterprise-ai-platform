# Module: `model_miner`

- Category: Legacy Core · priority 36
- Version: 1.0.0
- Purpose: Enterprise Model Miner OS Module — scan/rip local model training into the KB.
- Skill: `eni-module-model_miner` (ICM stages) in skills_pack/skills/eni-modules/model_miner/

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
  serve -> register model as a local MCP tool + LSP note for Hermes

All components are stdlib-only with zero external dependencies.

## Key API (facade methods)
facade, health_check, initialize, shutdown

## Tests
```bash
python3 -m pytest modules/model_miner/tests -q
```

## Import
```python
from enterprise.modules.model_miner import create_model_miner_module
m = create_model_miner_module()
```
