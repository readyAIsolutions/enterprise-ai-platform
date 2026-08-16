# OpenRouter Rate Limit Signatures

## Free Tier — 1,000 requests/day

Error body when free tier is exhausted:
```json
{
  "error": {
    "message": "Rate limit exceeded: free-models-per-day-high-balance. ",
    "code": 429,
    "metadata": {
      "headers": {
        "X-RateLimit-Limit": "1000",
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": "1785024000000"
      },
      "provider_name": null
    }
  }
}
```

- `X-RateLimit-Limit`: 1000 (requests per day for free tier)
- `X-RateLimit-Remaining`: 0 when exhausted
- `X-RateLimit-Reset`: epoch ms when the daily window resets

The `X-RateLimit-Reset` value is an epoch in milliseconds. Convert to datetime:
```python
import datetime
reset = datetime.datetime.fromtimestamp(1785024000000 / 1000, tz=datetime.timezone.utc)
```

## Pool Entry Structure (auth.json)

OpenRouter keys appear in two pool entries within `credential_pool`:
1. Direct: `openrouter` — sourced from `env:OPENROUTER_API_KEY`
2. Custom: `custom:openrouter` — sourced from `config:openrouter` (the provider block in config.yaml)

Both share the same API key (`secret_fingerprint` is identical), so exhausting one doesn't unlock the other. Clear both.

Exhausted entry example:
```json
{
  "id": "64854a",
  "label": "OPENROUTER_API_KEY",
  "auth_type": "api_key",
  "last_status": "exhausted",
  "last_status_at": 1784950251.0613573,
  "last_error_code": 429,
  "last_error_message": "Error code: 429 - {...}",
  "base_url": "https://openrouter.ai/api/v1",
  "request_count": 0
}
```

## Hermes Cooldown Constants

| Constant | File | Default | Patched |
|---|---|---|---|
| `EXHAUSTED_TTL_429_SECONDS` | `agent/credential_pool.py` | 3600 (1h) | 1 |
| `_rate_limited_until` | `agent/chat_completion_helpers.py` | +60s | +0s |
| `EXHAUSTED_TTL_401_SECONDS` | `agent/credential_pool.py` | 300 (5m) | unchanged |
| `EXHAUSTED_TTL_DEFAULT_SECONDS` | `agent/credential_pool.py` | 3600 (1h) | unchanged |