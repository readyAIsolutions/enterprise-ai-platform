# OpenRouter model cache refresh recipe

Symptom: model picker shows only 1 free OpenRouter model, user knows there should be ~16.

## Root cause: three-layer cache, any stale layer gates the picker

1. `~/.hermes/config.yaml` — `providers.openrouter` must exist with `discover_models: true`
2. `~/.hermes/provider_models_cache.json` — live `/v1/models` snapshot per provider
3. `~/.hermes/cache/model_catalog.json` — curated catalog with descriptions

## Full fix

### Step 1 — Register OpenRouter as a provider (if missing)
```bash
hermes config set providers.openrouter.name openrouter
hermes config set providers.openrouter.base_url https://openrouter.ai/api/v1
hermes config set providers.openrouter.api_key ""
hermes config set providers.openrouter.discover_models true
hermes config set providers.openrouter.context_length 200000
hermes config set providers.openrouter.default_model openrouter/auto
```

### Step 2 — Refresh provider cache with live free models
```bash
curl -s 'https://openrouter.ai/api/v3/models?limit=200' | python3 -c "
import sys, json, time
data = json.load(sys.stdin)
free_ids = [m['id'] for m in data['data']
    if float(m.get('pricing',{}).get('prompt','1') or '1') == 0
    and float(m.get('pricing',{}).get('completion','1') or '1') == 0]

with open('/home/hunter/.hermes/provider_models_cache.json') as f:
    cache = json.load(f)

old = cache['openrouter']['models']
paid = [m for m in old if ':free' not in m]
new = list(dict.fromkeys(free_ids + paid))
cache['openrouter']['models'] = new
cache['openrouter']['at'] = time.time()

with open('/home/hunter/.hermes/provider_models_cache.json', 'w') as f:
    json.dump(cache, f, indent=2)
print(f'Cache: {len(old)} -> {len(new)} models ({len(free_ids)} free)')
"
```

### Step 3 — Add missing free models to model catalog
```bash
python3 -c "
import json
live_free = [...]  # from step 2 output
with open('/home/hunter/.hermes/cache/model_catalog.json') as f:
    cat = json.load(f)
existing = {m['id'] for m in cat['providers']['openrouter']['models']}
for mid in live_free:
    if mid not in existing:
        cat['providers']['openrouter']['models'].append({'id': mid, 'description': 'free', 'free': True})
with open('/home/hunter/.hermes/cache/model_catalog.json', 'w') as f:
    json.dump(cat, f, indent=2)
"
```

### Step 4 — User refreshes picker
```bash
hermes model --refresh
```

## Verification
- Provider cache: 40+ OpenRouter models, 13+ with `:free` suffix
- Model catalog: 50+ OpenRouter entries, 16+ free
- Config: `grep -A7 '  openrouter:' ~/.hermes/config.yaml` shows discover_models: true
