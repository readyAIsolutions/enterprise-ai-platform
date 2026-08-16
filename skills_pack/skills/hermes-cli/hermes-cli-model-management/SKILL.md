---
name: hermes-cli-model-management
description: Manage model configuration and the /model slash command picker in Hermes CLI. Covers adding models to curated fallback lists, understanding remote catalog vs local fallback, and switching models via config or TUI.
category: hermes-cli
---

# Hermes CLI Model Management

## Overview
Hermes CLI uses a two-tier model catalog system for the `/model` slash command picker:
1. **Remote catalog** — `https://hermes-agent.nousresearch.com/docs/api/model-catalog.json` (TTL 24h, cached to disk)
2. **Local fallback** — `OPENROUTER_MODELS` list in `hermes_cli/models.py` (used when remote unavailable)

The picker filters live OpenRouter `/v1/models` against the curated list. A model must be in the curated list (remote or local) AND advertise `tools` in `supported_parameters` to appear.

## Adding a Model to the /model Picker (OpenRouter)

### When the model exists in OpenRouter but not in the catalog
Patch the local fallback list in `hermes_cli/models.py`:

```python
# File: ~/.local/lib/python3.14/site-packages/hermes_cli/models.py
# Find OPENROUTER_MODELS list and add entry:
("vendor/model-id", "description — $price, context"),
```

### Verification
```bash
# Force refresh and check
python3 -c "
import hermes_cli.models as m
m._openrouter_catalog_cache = None
from hermes_cli.models import fetch_openrouter_models
models = fetch_openrouter_models(force_refresh=True)
for mid, desc in models:
    if 'model-id' in mid:
        print(f'{mid} -> {desc}')
"
```

### Remote Catalog (Preferred)
The remote catalog at `hermes-agent.nousresearch.com/docs/api/model-catalog.json` is the source of truth. If you maintain that repo, add the model there instead of patching local fallback.

## Switching Default Model

### Via Config (Persistent)
```bash
hermes config set model.model deepseek/deepseek-v4-flash-0731
hermes config set model.provider openrouter
```

### Via Alias (Session)
```bash
hermes -m ds-flash "prompt"
```

### Via TUI
Type `/model` → **Step 1: select provider (e.g., OpenRouter)** → **Step 2: select model from that provider's list** → saves to config.yaml

**Critical:** The picker is TWO STEPS. You must pick the provider FIRST, then the model list for that provider appears. Many users miss Step 1 and think the model is missing.

## Pitfalls

| Issue | Cause | Fix |
|-------|-------|-----|
| Model not in `/model` picker | Missing from curated list (remote + local) | Add to `OPENROUTER_MODELS` fallback or update remote catalog |
| Model in picker but fails at runtime | Doesn't advertise `tools` in `supported_parameters` | Only tool-capable models work with Hermes agent loop |
| Changes don't appear | In-process cache (`_openrouter_catalog_cache`) | Set `m._openrouter_catalog_cache = None` before refetch |
| Free model not showing for free tier | Pricing filter | Ensure pricing has `prompt: 0` and `completion: 0` |
| **Model seems missing but IS in catalog** | **Two-step picker: must select provider FIRST** | **Run `/model` → pick OpenRouter → then scroll model list** |
| **Can't diagnose why model hidden** | No visibility into filtering logic | Run `references/verify_model_in_picker.py <model-id>` |
| **Model exists in OpenRouter API but NOT in `/model` picker** | **Stale `provider_models_cache.json` — Hermes caches discovered models per-provider** | **Run `hermes model --refresh` in an INTERACTIVE terminal (NOT via script/pipe) to wipe cache and re-fetch all 340+ models from OpenRouter** |
| **Provider discovery returns subset of models** | `provider_models_cache.json` only updated by explicit refresh or auto-discovery on first run | Delete `~/.hermes/provider_models_cache.json` then run `hermes model --refresh` |

## Key Files

| Path | Purpose |
|------|---------|
| `hermes_cli/models.py` | `OPENROUTER_MODELS` fallback list, `fetch_openrouter_models()` |
| `hermes_cli/model_catalog.py` | Remote catalog fetch/cache logic |
| `~/.hermes/config.yaml` | `model.model`, `model.provider`, `model.model_aliases` |
| `~/.hermes/cache/model_catalog.json` | Disk cache of remote catalog (24h TTL) |
| `~/.hermes/provider_models_cache.json` | **Per-provider live /v1/models cache — ONLY updated by `hermes model --refresh`** |
| `references/verify_model_in_picker.py` | Diagnose curated catalog + tool-support filtering |
| `references/diagnose_provider_cache.py` | **Diagnose stale provider_models_cache.json (this session's issue)** |

## Verification Scripts

**For curated catalog + tool-support issues:**
```bash
python3 ~/.hermes/skills/hermes-cli/hermes-cli-model-management/references/verify_model_in_picker.py deepseek/deepseek-v4-flash-0731
```
Clears in-process cache, fetches fresh from OpenRouter, verifies catalog presence AND `tools` support.

**For stale provider discovery cache (provider_models_cache.json):**
```bash
python3 ~/.hermes/skills/hermes-cli/hermes-cli-model-management/references/diagnose_provider_cache.py deepseek/deepseek-v4-flash-0731
```
Checks if model exists in provider_models_cache.json, compares against live OpenRouter API, tells you exactly what to run.

## Related Skills
- `hermes-intelligent-router` — Auto-loaded router config
- `hermes-local-llm-provider` — Local model serving (different path)