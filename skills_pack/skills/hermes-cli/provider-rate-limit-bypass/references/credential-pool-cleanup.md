# Credential Pool Cleanup & Restore Recipe

When the credential pool gets corrupted, keys are overwritten, or exhaustion
state needs clearing, use these recipes. Run from terminal as `python3 << 'PYEOF'`.

## Quick exhaustion clear (all providers)
```python
import json
with open('/home/hunter/.hermes/auth.json') as f:
    auth = json.load(f)

pool = auth.get('credential_pool', {})
for provider, keys in pool.items():
    if isinstance(keys, list):
        for k in keys:
            k['last_status'] = None
            k['last_error_code'] = None
            k['exhausted'] = False
            k.pop('last_error_reset_at', None)

with open('/home/hunter/.hermes/auth.json', 'w') as f:
    json.dump(auth, f, indent=2)
print('Exhaustion cleared for all providers')
```

## Merge new keys (don't replace)
```python
import json

NEW_KEY_1 = "sk-or-..."  # from LO
NEW_KEY_2 = "sk-or-..."  # from LO

with open('/home/hunter/.hermes/auth.json') as f:
    auth = json.load(f)

pool = auth.setdefault('credential_pool', {})
or_keys = pool.setdefault('openrouter', [])

# Collect existing tokens to avoid duplicates
existing = {k['access_token'] for k in or_keys if len(k.get('access_token','')) > 50}

for i, new_token in enumerate([NEW_KEY_1, NEW_KEY_2], 1):
    if new_token not in existing:
        or_keys.append({
            "id": f"or_key_{i}",
            "label": f"OPENROUTER_ACCOUNT_{i}",
            "source": "manual",
            "auth_type": "api_key",
            "access_token": new_token,
            "priority": len(or_keys),
            "request_count": 0,
            "last_status": None,
            "last_error_code": None,
            "exhausted": False,
        })
        existing.add(new_token)
        print(f"Added: ACCOUNT_{i}")
    else:
        print(f"Skipped duplicate: ACCOUNT_{i}")

with open('/home/hunter/.hermes/auth.json', 'w') as f:
    json.dump(auth, f, indent=2)

print(f"Total openrouter keys: {len(or_keys)}")
```

## Restore from backup
```bash
# Check what's in the backup
python3 -c "
import json
bk = json.load(open('/home/hunter/.hermes/auth.json.backup'))
or_keys = bk['credential_pool']['openrouter']
for k in or_keys:
    print(k['label'], len(k['access_token']))
"

# If backup looks good, restore it
cp ~/.hermes/auth.json.backup ~/.hermes/auth.json
```

## Verify keys work (curl-based health check)
```python
import json, subprocess
from pathlib import Path

auth = json.loads(Path('/home/hunter/.hermes/auth.json').read_text())
for k in auth['credential_pool']['openrouter']:
    tok = k.get('access_token', '')
    if len(tok) < 50:
        continue
    r = subprocess.run([
        'curl', '-s', 'https://openrouter.ai/api/v1/auth/key',
        '-H', f'Authorization: Bearer *** + tok
    ], capture_output=True, text=True, timeout=10)
    d = json.loads(r.stdout)
    dd = d['data']
    print(f"{k['label']}: credits={dd.get('credits')}, monthly={dd.get('usage_monthly')}, "
          f"daily={dd.get('usage_daily')}, limit={dd.get('limit')}")
```

## Check if paid models work (deepseek-v4-pro test)
```bash
hermes chat -q "say test" --yolo --provider openrouter \
  -m deepseek/deepseek-v4-pro --max-turns 1
```
If you get a response (not 402/429), the credits-bearing key is active.