# Provider Mesh — Final State (July 24, 2026)

## All 16 Configured Providers

LO has 30+ API keys in `~/.hermes/.env`. 16 are configured as Hermes providers with
round-robin credential pooling. The mesh auto-routes through the fallback chain when
the primary provider exhausts.

### Working (confirmed via curl test)
| Provider | Base URL | Model | Daily Capacity | Key |
|----------|----------|-------|---------------|-----|
| OpenRouter | https://openrouter.ai/api/v1 | 15 :free models | 1,000 req/key (3 keys) | OPENROUTER_API_KEY |
| Groq | https://api.groq.com/openai/v1 | llama-3.3-70b-versatile | ~14,400 req | GROQ_API_KEY |
| Cerebras | https://api.cerebras.ai/v1 | gemma-4-31b | ~1,000+ req | CEREBRAS_API_KEY |
| SambaNova | https://api.sambanova.ai/v1 | DeepSeek-V3.2 | ~1,000+ req | SAMBANOVA_API_KEY |
| AirLLM | http://127.0.0.1:8913/v1 | Mistral-7B-Instruct-v0.2 | UNLIMITED | local |

### Configured but not yet tested
| Provider | Base URL | Default Model | Key |
|----------|----------|--------------|-----|
| NVIDIA | https://integrate.api.nvidia.com/v1 | nemotron-3-nano-30b-a3b | NVIDIA_API_KEY |
| Fireworks | https://api.fireworks.ai/inference/v1 | llama-v3p1-70b-instruct | FIREWORKS_API_KEY |
| Mistral | https://api.mistral.ai/v1 | mistral-large-latest | MISTRAL_API_KEY |
| DeepSeek | https://api.deepseek.com/v1 | deepseek-chat | DEEPSEEK_API_KEY |
| Cohere | https://api.cohere.ai/v1 | command-r-plus | COHERE_API_KEY |
| xAI | https://api.x.ai/v1 | grok-2-1212 | XAI_API_KEY |
| Novita | https://api.novita.ai/v3/openai | llama-3.1-8b-instruct | NOVITA_API_KEY |
| Upstage | https://api.upstage.ai/v1/solar | solar-pro | UPSTAGE_API_KEY |
| Voyage | https://api.voyageai.com/v1 | voyage-3 | VOYAGE_API_KEY |

### Known non-working (402/needs credits)
| Provider | Error |
|----------|-------|
| DeepInfra | 402 — needs positive balance |
| Hyperbolic | 402 — insufficient funds |

## Fallback Chain (Priority Order)

```
1. OpenRouter (nvidia/nemotron-3-ultra-550b-a55b:free, 1M context)
2. Groq (llama-3.3-70b-versatile)
3. Cerebras (gemma-4-31b)
4. SambaNova (DeepSeek-V3.2)
5. NVIDIA (nemotron-3-nano-30b-a3b)
6. DeepSeek (deepseek-chat)
7. xAI (grok-2-1212)
8. Novita (llama-3.1-8b-instruct)
9. Upstage (solar-pro)
10. AirLLM (Mistral-7B-Instruct-v0.2, local, UNLIMITED)
```

## OpenRouter Models (July 2026)

15 free models. Notable for token-maxing:
- `nvidia/nemotron-3-ultra-550b-a55b:free` — **1,000,000 context** (primary for swarms)
- `nvidia/nemotron-3-super-120b-a12b:free`
- `google/gemma-4-31b-it:free` — 262,144 context
- `google/gemma-4-26b-a4b-it:free` — 262,144 context
- `poolside/laguna-s-2.1:free` — 262,144 context
- `poolside/laguna-xs-2.1:free` — 262,144 context
- `poolside/laguna-m.1:free` — 262,144 context
- `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` — 256,000 context
- `nvidia/nemotron-3-nano-30b-a3b:free`
- `cohere/north-mini-code:free` — 256,000 context
- `inclusionai/ling-3.0-flash:free` — 262,144 context

## Credential Pool Structure

Pool entries in `~/.hermes/auth.json` → `credential_pool` → `{provider}`:

### OpenRouter (3 keys)
```
[0] source=manual, access_token=sk-or-... (env-resolved key)
[1] source=manual, access_token=sk-or-... (LO's second key)
[2] source=env:OPENROUTER_API_KEY (syncs from .env at runtime)
```

### Credential resolution priority
1. `access_token` directly on the entry
2. `extra.secret_fingerprint` → system keyring lookup
3. `.env` file → synced by `_upsert_entry` on startup (matches by `source` field)

### Adding a new key
Add to `~/.hermes/auth.json`:
```json
{
  "id": "<6-char hex>",
  "label": "PROVIDER_API_KEY_N",
  "auth_type": "api_key",
  "priority": <next available>,
  "source": "manual",
  "access_token": "<actual key>",
  "base_url": "<provider base url>",
  "request_count": 0
}
```

## Token-Maxing Strategy

OpenRouter limit is **request-based** (1,000 req/day/key), NOT token-based.

To maximize throughput:
1. Use `nvidia/nemotron-3-ultra-550b-a55b:free` (1,000,000 context)
2. Pack every request's context window to near-limit
3. Set `max_tokens` to model maximum
4. For swarm workers: batch multiple tasks into large context windows
5. Never waste a request on a short/small prompt

### July 12, 2026 — 1.7 Billion Token Day

LO hit 1.7B tokens on OpenRouter free models in one day. The exact mechanism remains
unconfirmed — possibilities include:
- OpenRouter's free tier did not have the 1,000 req/day cap at that time
- Account had a different rate-limit tier ("high-balance" tier observed on key)
- Multiple keys/accounts were active simultaneously
- The limit is per-model rather than per-account (15 models × 1,000 = 15K req)

With the current mesh: 3 OpenRouter keys (3,000 req) + Groq (14,400 req) + Cerebras
+ SambaNova + 6 more providers + unlimited local = **~20,000+ req/day combined**.
At max context packing, this exceeds 1.7B tokens.

## Source File Locations

All under `/home/hunter/.local/lib/python3.14/site-packages/agent/`:
- `credential_pool.py` — TTLs, `_exhausted_until`, `_available_entries`, `mark_exhausted_and_rotate`
- `chat_completion_helpers.py` — `_rate_limited_until`, `interruptible_api_call`
- `transports/chat_completions.py` — `:free` handling in `build_kwargs()`
- `agent_runtime_helpers.py` — `recover_with_credential_pool()`, `extract_api_error_context()`
- `retry_utils.py` — `jittered_backoff()`