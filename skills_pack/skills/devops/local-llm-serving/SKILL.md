---
name: local-llm-serving
description: Set up, debug, and optimize local LLM backends (transformers, llama.cpp, AirLLM, vLLM) for Hermes. Covers model format pitfalls, GPU memory budgeting, quantization, and speed optimization.
triggers:
  - User says "fix local model", "speed up local LLM", "airllm slow", "local provider not working"
  - User is setting up or debugging a local OpenAI-compatible LLM server for Hermes
  - Symptoms: <1 tok/s inference on GPU-capable hardware, garbled output, OOM errors
  - A local backend returns HTTP 500 on every model call (e.g. Ollama "llama-server binary not found")
  - A local model answers chat/math with orchestration-flavored text (it is a tool-calling fine-tune, not a general chatbot)
---
> Ollama-500 / model-role-mismatch diagnostics: see `references/local-llm-diagnostics.md`.

# Local LLM Serving & Optimization

## Quick decision tree

1. **Model fits in VRAM?** → Use `transformers` directly with `device_map="auto"`. Do NOT use disk-offloading libraries (AirLLM, DeepSpeed ZeRO-Infinity) for small models.
2. **Model too big for VRAM?** → Use 4-bit quantization (bitsandbytes NF4) if safetensors available, else GGUF + llama.cpp.
3. **Still slow?** → Check if layers are on CPU. Use `max_memory` to push more to GPU. Flash attention (SDPA is built-in and fast enough for most cases).

## Model format pitfalls

- **`.bin` vs `.safetensors`**: bitsandbytes quantization REQUIRES safetensors. If HF cache only has `.bin` files, loading with `quantization_config` fails with `IncompleteSnapshotError`.
- **Workaround for .bin**: Load in fp16 without quantization, use `use_safetensors=False`, and add `offload_folder` for CPU-offloaded layers.
- **Force offline**: Set `HF_HUB_OFFLINE=1` to prevent HF from trying to download missing safetensors at each load.
- **Download safetensors directly**: Use `hf_hub_download()` for individual files instead of `snapshot_download()` which can get stuck downloading duplicate blob versions.

```python
from huggingface_hub import hf_hub_download
files = [
    'model-00001-of-00003.safetensors',
    'model-00002-of-00003.safetensors',
    'model-00003-of-00003.safetensors',
    'model.safetensors.index.json',
]
for f in files:
    hf_hub_download('org/model-name', f)
```

## GPU memory budgeting

- RTX 3060 Ti (8GB): usable VRAM ~7.66 GiB. Leave ~1.5 GiB for KV cache + CUDA overhead → budget ~6 GiB for model weights.
- fp16 Mistral-7B ~14GB → won't fit, needs 4-bit (~4-5GB) or GPU/CPU split.
- When using `device_map="auto"` with fp16: expect ~5-6GB on GPU, rest on CPU. Speed ~0.7-1.0 tok/s on 3060 Ti.
- When using 4-bit: full model on GPU, speed ~20-50 tok/s.

## Server boilerplate

Minimal fast OpenAI-compatible server using transformers:

```python
# Key: use_safetensors=False for .bin models, offload_folder for disk offload
model = AutoModelForCausalLM.from_pretrained(
    model_id,
    device_map="auto",
    trust_remote_code=False,
    attn_implementation="sdpa",
    torch_dtype=torch.float16,
    use_safetensors=False,
    offload_folder="/path/to/offload",
)
```

## Verification (ALWAYS RUN BEFORE REPORTING TO USER)

**Critical workflow**: When debugging Hermes + local server issues, always verify the server responds correctly via `curl` BEFORE asking the user to test or restart. The user should never be the first tester.

```bash
# 1. Health check
curl -s http://127.0.0.1:8913/health

# 2. Full inference test (ALL THREE model name variants — HF path, short name, alias)
#    The alias name (e.g. "airllm") is what Hermes actually sends in the request body.
curl -s http://127.0.0.1:8913/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"mistralai/Mistral-7B-Instruct-v0.2","messages":[{"role":"user","content":"hi"}],"max_tokens":10}'

curl -s http://127.0.0.1:8913/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"Mistral-7B-Instruct-v0.2","messages":[{"role":"user","content":"hi"}],"max_tokens":10}'

curl -s http://127.0.0.1:8913/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"airllm","messages":[{"role":"user","content":"hi"}],"max_tokens":10}'

# 3. Check connections
ss -tp | grep 8913
```

Only after all three pass should you tell the user the fix is ready. Target: <5s for 20 tokens = acceptable. <2s = good. >30s = broken.

## Hermes integration

Once the server is running, wire it into Hermes:

```bash
# Point auxiliary models (title gen, compression) to local to avoid rate limits
hermes config set auxiliary.title_generation.provider airllm
hermes config set auxiliary.title_generation.model mistralai/Mistral-7B-Instruct-v0.2
hermes config set auxiliary.compression.provider airllm
hermes config set auxiliary.compression.model mistralai/Mistral-7B-Instruct-v0.2

# Optionally make it the default model
hermes config set model.default mistralai/Mistral-7B-Instruct-v0.2
hermes config set model.provider airllm
```

**Do NOT edit `~/.hermes/config.yaml` directly** — Hermes blocks writes to config files. Use `hermes config set` instead.

The user switches with `/model airllm` (or `/model mistral-local` if that alias exists).

If the TUI shows wrong context length (e.g. 256K for a model that should be 8K), Hermes is using a different provider — verify the model alias is correct.

## 4-bit full-GPU server (fast path)

Once safetensors are downloaded, this is the production config (~20-50 tok/s, all layers on GPU):

```python
from transformers import AutoModelForCausalLM, BitsAndBytesConfig

quant_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",
)
model = AutoModelForCausalLM.from_pretrained(
    model_id,
    quantization_config=quant_config,
    device_map="auto",
    attn_implementation="sdpa",
)
# Verify all layers on GPU:
devices = set(str(p.device) for p in model.parameters())
print("ALL GPU" if all('cuda' in d for d in devices) else f"SPLIT: {devices}")
# Expect: ~4.1 GB VRAM used for Mistral-7B
```

Full reference server script: see `airllm-fast-server` skill for the complete deployable at `/home/hunter/Dev/workers/airllm_server.py`.

## Speed benchmarks (Mistral-7B on RTX 3060 Ti 8GB)

| Config | Speed | VRAM | Output |
|--------|-------|------|--------|
| AirLLM disk offloading (original) | 0.05 tok/s, garbled | 1.3 GB | Broken — hallucinates `<|user|>` |
| fp16 GPU/CPU split | 0.7-1.0 tok/s | 5-6 GB | Clean, slow |
| 4-bit NF4 full GPU | 20-50 tok/s | 4.1 GB | Clean, fast |

First request after server start is slower (CUDA warmup). Test speed with the second request.

## Common failures

| Symptom | Cause | Fix |
|---------|-------|-----|
| 100+ seconds per reply | Disk offloading (AirLLM) | Switch to direct transformers |
| `IncompleteSnapshotError` with `local_files_only` | Missing safetensors | Use `use_safetensors=False` or download |
| `OutOfMemoryError` at load | `max_memory` too high | Lower GPU budget to 6 GiB for 8GB card |
| Garbled output (`<|user|>` in response) | Wrong chat template or old AirLLM | Use tokenizer's `apply_chat_template` |
| 0% GPU utilization during inference | Model on CPU | Check device_map, VRAM allocation |
| "Model returned no content" in Hermes (curl works) | Hermes sends alias name (e.g. "airllm") as model field; server MODEL_ALIASES missing it | Add alias name to MODEL_ALIASES dict |
| HTTP 429 / rate limiting in Hermes | Auxiliary models hitting external APIs | Point aux models to local provider via `hermes config set` |
| TUI shows wrong context length (e.g. 256K for local 8K model) | **Model catalog overriding local provider** | `hermes config set model_catalog.enabled false` + restart Hermes |
| Hermes connects but gets empty response (CLOSE-WAIT on server port) | Model catalog routing to wrong provider | Disable model catalog, full Hermes restart |

### Hermes auxiliary model rate limiting

When Hermes shows `HTTP 429: Rate limit exceeded: free-models-per-day-high-balance`, it means auxiliary services (title generation, compression, etc.) are hitting external providers like OpenRouter. Fix by pointing them to the local provider:

```bash
hermes config set auxiliary.title_generation.provider airllm
hermes config set auxiliary.title_generation.model <local-model-id>
hermes config set auxiliary.compression.provider airllm
hermes config set auxiliary.compression.model <local-model-id>
```

Vision can't use local (no vision model on Mistral-7B) — leave it on an external provider.

### Model name mismatch between Hermes and server

Hermes may send model names without the HuggingFace prefix (e.g. `Mistral-7B-Instruct-v0.2` instead of `mistralai/Mistral-7B-Instruct-v0.2`). **Critically, Hermes also sends the ALIAS NAME directly** (e.g. `"airllm"`) as the `model` field in API requests, not the resolved model ID. Your server's MODEL_ALIASES dict MUST include every configured alias name. Test all three variants from the CLI before declaring the server working.

Recipe and full troubleshooting flow: see `airllm-fast-server` skill and its `references/hermes-routing-troubleshooting.md`.

## Pitfalls

- AirLLM splits layers to disk and reads them one-by-one per forward pass. For a 7B model on 8GB GPU this is absurd — use transformers directly.
- `snapshot_download()` can download duplicate blob versions and stall. Use `hf_hub_download()` for specific files.
- Don't set `max_memory` higher than 7.0 GiB on 8GB cards — CUDA context + KV cache need headroom.
- Python output buffering hides progress. Always run servers with `PYTHONUNBUFFERED=1 python3 -u`.
- `device_map="auto"` with fp16 splits layers GPU/CPU — some end up on `meta` device if no `offload_folder`. The "Some parameters are on the meta device" warning means incomplete load.
- Converting a `.bin`-cached model to 4-bit requires first downloading `.safetensors` — budget 10-20 min for the download on first setup.
- **Model catalog hijack**: When `model_catalog.enabled: true` (default), Hermes may match a local model name against the Nous model catalog and route it to an external provider with wrong context length (e.g. local Mistral-7B showing 256K context). Symptom: `ss -tp` shows CLOSE-WAIT connections to the local server port but Hermes reports empty responses. Fix: `hermes config set model_catalog.enabled false` then fully restart Hermes (exit + relaunch — `/new` is NOT sufficient). If stale, delete the cached catalog at `~/.hermes/cache/model_catalog.json`.
- **`/new` does NOT reload config**: After `hermes config set`, you must fully exit and restart Hermes. `/new` only starts a new chat session; it does not reload provider/auxiliary config.
