# Provider Test Results — July 25, 2026

37 providers tested from LO's API key backup file. Results below.

## CONFIRMED WORKING (hermes chat-tested)

| Provider | Model | Context | Notes |
|----------|-------|---------|-------|
| OpenRouter | nemotron-3-ultra-550b-a55b:free | 1,000,000 | 2 keys round-robin, 18 free models available |
| Zhipu GLM | glm-5.2 | 1,048,576 | Free tier, China-based |
| SambaNova | DeepSeek-V3.1 | 131,072 | Works, use V3.1 not V3.2 (32K ctx too small) |
| Cerebras | gemma-4-31b | 131,072 | Free tier |
| NVIDIA NIM | nemotron-3-nano-30b-a3b | 262,144 | 118 models available |
| Upstage | solar-pro | 131,072 | Korea-based |
| DeepInfra | llama-3.3-70B | 131,072 | KEY VALID — needs balance top-up (402) |
| Cohere | command-r-plus-08-2024 | 128,000 | Via local proxy (no OpenAI-compatible endpoint) |

## KEY EXPIRED (401)

DeepSeek, Moonshot, Mistral, Replicate, HuggingFace, Anthropic — regenerate keys at respective dashboards.

## ACCOUNT BLOCKED (403)

Fireworks (suspended), AI21, Writer, Hyperbolic, Novita, GooseAI, NLP Cloud, Groq.

## WRONG ENDPOINTS (404)

Cloudflare Workers AI, RunPod, VastAI, Anyscale — need correct base URLs.

## PAY-ONLY

OpenAI (117 models available, key valid), Together, Perplexity, Lambda, Lepton, Baseten.

## UNREACHABLE

Google Gemini (no key in backup), Alibaba Qwen (no key), HuggingFace (DNS issues on this box, router.huggingface.co works).

## MODEL PICKER BUG

`hermes model` shows only 28 OpenRouter models because `hermes_cli/models.py` has a hardcoded `OPENROUTER_MODELS` list. The live API returns 345 models (18 free) but the picker only shows models in the hardcoded list. Fix: patch the list to include all current free models, clear bytecode cache, restart hermes, run `hermes model --refresh`.