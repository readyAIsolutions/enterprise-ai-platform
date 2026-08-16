# OpenRouter free-model pool — probed 2026-07-11

Probe method: for each slug,
  curl -sS https://openrouter.ai/api/v1/chat/completions \
    -H "Authorization: Bearer *** " -H "Content-Type: application/json" \
    -d '{"model":"<slug>","messages":[{"role":"user","content":"hi"}]}'
then read the HTTP status. The OpenRouter key is loaded by hermes from
/home/hunter/.hermes/.env (minis inherit it).

## LIVE (use these — rotate across minis)
| slug                                  | status | notes                                    |
|---------------------------------------|--------|------------------------------------------|
| tencent/hy3:free                      | 200    | reliable at scale; LO's own chat runs it |
| qwen/qwen3-coder:free                 | 429    | transient rate-limit; rotates OK         |
| meta-llama/llama-3.3-70b-instruct:free| 429    | transient rate-limit; rotates OK         |

## DEAD — HTTP 400 (bad model id / not a free slug)
- qwen/qwen2.5-72b-instruct:free
- qwen/qwen2.5-7b-instruct:free
- deepseek/deepseek-v3-0324:free
- sao10k/l3.1-70b-hanami-x:free
- thedrummer/anubis-pro-105b-v1:free

## DEAD — HTTP 404 (not found on OpenRouter free tier)
- meta-llama/llama-3.1-8b-instruct
- mistralai/mistral-7b-instruct
- nous-hermes (all)
- qwen/qwen3-30b / qwen3-8b
- meta-llama/llama-3.2-11b / llama-3.2-11b-vision
- google/gemini-2.5-flash
- microsoft/phi-4
- deepseek/deepseek-r1 / deepseek-chat
- google/gemma-2-9b
- meta-llama/llama-3.1-70b
- openchat / openhermes / dolphin-mixtral
(and others — if a slug 400s/404s, treat it as dead; do not add it to the pool)

## Rotation rule (16 minis)
slug = LIVE_POOL[i % 3]; stagger launches with `sleep 2.5` between windows to avoid
the 429 storm when 16 chats fire at once. NEVER pin a dead slug (it 400/404s every time
and the mini spins on errors). Seed the pool at ~/.cache/eni_parallel/live_models.txt.
