---
name: airllm-fast-server
description: Deploy/fix the local airllm OpenAI-compatible server on port 8913 with 4-bit GPU inference. Covers diagnosing slow AirLLM, switching to transformers+biteandbytes, downloading safetensors, and restarting.
---

# AirLLM Fast Server Fix

When the local `airllm` provider (port 8913) is slow or broken, follow this pipeline.

## Architecture
- Hermes config: `providers.airllm` → `http://127.0.0.1:8913/v1`
- Server script: `/home/hunter/Dev/workers/airllm_server.py`
- Model: `mistralai/Mistral-7B-Instruct-v0.2` (HF cache at `~/.cache/huggingface/hub/models--mistralai--Mistral-7B-Instruct-v0.2/`)
- GPU: NVIDIA RTX 3060 Ti (8GB VRAM, CUDA 13.2)
- Target: 4-bit NF4 quantization → ~4.1GB VRAM, 20-30 tok/s

## Diagnosis
```bash
# Check if server is running
ss -tlnp | grep 8913
# Test inference speed
time curl -s http://127.0.0.1:8913/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"mistralai/Mistral-7B-Instruct-v0.2","messages":[{"role":"user","content":"hello"}],"max_tokens":20,"temperature":0}'
# Check GPU usage
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader
```

## Speed targets
- <5s for 20 tokens = good (4-bit full GPU)
- 5-30s = ok (fp16 GPU/CPU split)
- >60s = broken (AirLLM disk offloading or CPU-only)

## Fix steps

1. **Kill old server**: `kill <pid>` (find with `ss -tlnp | grep 8913`)

2. **Check safetensors are cached** (required for 4-bit):
   ```bash
   ls ~/.cache/huggingface/hub/models--mistralai--Mistral-7B-Instruct-v0.2/snapshots/*/model-00001-of-00003.safetensors
   ```
   If missing, download:
   ```python
   from huggingface_hub import hf_hub_download
   for f in ['model-00001-of-00003.safetensors', 'model-00002-of-00003.safetensors',
             'model-00003-of-00003.safetensors', 'model.safetensors.index.json']:
       hf_hub_download('mistralai/Mistral-7B-Instruct-v0.2', f)
   ```

3. **Start server** (background, notify_on_complete):
   ```bash
   cd /home/hunter/Dev/workers && python3 airllm_server.py --port 8913 --model mistralai/Mistral-7B-Instruct-v0.2
   ```
   Wait ~50s for 4-bit quantization on first load.

4. **Verify**: test speed + check "ALL GPU" in logs.

## Hermes integration — Complete local-only stack

**Full end-to-end flow (run in order):**

```bash
# 1. Deploy local LLM server (4-bit GPU, port 8913)
cd /home/hunter/Dev/workers && python3 airllm_server.py --port 8913 --model mistralai/Mistral-7B-Instruct-v0.2
# Wait for "ALL GPU" + ~4.1 GB VRAM in logs (~50s first load)

# 2. Verify server responds to ALL model name variants Hermes may send
curl -s http://127.0.0.1:8913/health
curl -s http://127.0.0.1:8913/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"mistralai/Mistral-7B-Instruct-v0.2","messages":[{"role":"user","content":"hi"}],"max_tokens":10}'
curl -s http://127.0.0.1:8913/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"Mistral-7B-Instruct-v0.2","messages":[{"role":"user","content":"hi"}],"max_tokens":10}'
curl -s http://127.0.0.1:8913/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"airllm","messages":[{"role":"user","content":"hi"}],"max_tokens":10}'  # CRITICAL: Hermes sends alias name directly

# 3. Wire Hermes to local provider (use `hermes config set`, NEVER edit config.yaml directly)
hermes config set model.default mistralai/Mistral-7B-Instruct-v0.2
hermes config set model.provider airllm

# 4. Point auxiliary models to local to avoid OpenRouter rate limits (HTTP 429)
hermes config set auxiliary.title_generation.provider airllm
hermes config set auxiliary.title_generation.model mistralai/Mistral-7B-Instruct-v0.2
hermes config set auxiliary.compression.provider airllm
hermes config set auxiliary.compression.model mistralai/Mistral-7B-Instruct-v0.2
# Vision stays on OpenRouter (local Mistral-7B has no vision)

# 5. Disable model catalog to prevent hijacking (CRITICAL)
hermes config set model_catalog.enabled false

# 6. FULLY RESTART Hermes (exit completely, relaunch). `/new` does NOT reload provider/aux config.
# Then in Hermes TUI: model shows "Mistral-7B-Instruct-v0.2 · Nous Research" with correct ctx
```

**Verification checklist before declaring success:**
- [ ] Server health returns `{"status":"ok"}`
- [ ] All three curl variants return valid completions in <5s (4-bit GPU target)
- [ ] `nvidia-smi` shows ~4.1 GB VRAM, GPU utilization >0% during inference
- [ ] Server logs show "ALL GPU" (not split across CPU)
- [ ] Hermes TUI shows correct model name and context length (~8K, not 256K)
- [ ] Auxiliary ops (title generation, compression) work without 429 errors

### Model catalog hijack (critical)

When `model_catalog.enabled: true` (default), Hermes' model catalog can match a local model name to an external provider entry, silently redirecting requests away from your local server. Symptoms:
- TUI shows wrong context length (e.g. 256K for a model configured at 8K)
- `ss -tp | grep 8913` shows CLOSE-WAIT connections — Hermes connected but didn't process the response
- Server responds correctly to `curl` but Hermes reports "Model returned no content"

Fix: `hermes config set model_catalog.enabled false` then **fully restart** Hermes. If the catalog cache is stale, also delete `~/.hermes/cache/model_catalog.json`.

### Model name mismatch (common pitfall)

Hermes may send model names without the HF prefix (e.g. `Mistral-7B-Instruct-v0.2` instead of `mistralai/Mistral-7B-Instruct-v0.2`). The server must accept both. The fix is a `MODEL_ALIASES` dict in the server:

```python
MODEL_ALIASES = {
    "Mistral-7B-Instruct-v0.2": "mistralai/Mistral-7B-Instruct-v0.2",
    "mistral-7b": "mistralai/Mistral-7B-Instruct-v0.2",
    "airllm": "mistralai/Mistral-7B-Instruct-v0.2",          # Hermes sends alias name directly
    "mistral-local": "mistralai/Mistral-7B-Instruct-v0.2",
}
def _resolve_model(model_id: str) -> str:
    return MODEL_ALIASES.get(model_id, model_id)
```

**CRITICAL**: Hermes sends the ALIAS NAME (e.g. `"airllm"`) as the `model` field in the API request, not the resolved model ID. The server MUST include every configured model alias in its `MODEL_ALIASES` dict, including the alias name itself, or Hermes will get `"Model load failed"` / empty responses while `curl` tests pass.

### Rate limiting on auxiliary models

If Hermes shows `HTTP 429: Rate limit exceeded: free-models-per-day-high-balance`, the auxiliary models (title generation, compression) are hitting external providers. Point them to the local `airllm` provider with `hermes config set auxiliary.<service>.provider airllm`. Vision can stay on OpenRouter (local Mistral-7B can't do vision).

---

## Local Model as Orchestrator Brain (Tool Calling)

**This session extended the server so the local Mistral-7B becomes the orchestrator** — it decides when to call cloud, handles all secrets locally, expands terse inputs via the controller, and pushes to `hermes -z`. Cloud models NEVER see private data.

### Tool Calling Architecture

The server exposes 8 tools the local model can call via structured JSON:

| Tool | Purpose |
|------|---------|
| `controller_expand` | Expand short LO instruction → massive enterprise prompt |
| `controller_chat` | **FULL PIPELINE**: expand → privacy gate → route/Hermes -z (use for most builds) |
| `controller_status` | Check router health, queue depth, enterprise modules |
| `free_router_chat` | Raw cloud model access (bypass controller expansion) |
| `secret_get` / `secret_set` | Manage secrets locally — cloud NEVER sees these |
| `model_mine` | Rip training from local models into KB + MCP + LSP |
| `queue_job` | Defer work to 6pm when free models exhausted |
| `respond` | Reply directly to LO without tools |

**Working tool call format (what Mistral-7B reliably outputs):**
```json
{
  "thought": "reasoning about what to do",
  "tool": "controller_chat",
  "arguments": {"text": "build the enterprise platform", "use_hermes": true}
}
```

The server pares tool calls from:
1. ````json ... ```` code blocks
2. Bare JSON objects with `"tool"` field
3. Legacy `那些括号 [...]` format (backwards compat)

After tool execution, results are fed back as `<|tool_result|>` for multi-step orchestration.

### GPU Memory Config That Works on RTX 3060 Ti (8GB)

```python
quant_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",
    llm_int8_enable_fp32_cpu_offload=True,  # KEY: allows CPU offload
)

_model = AutoModelForCausalLM.from_pretrained(
    model_id,
    quantization_config=quant_config,
    device_map="auto",
    max_memory={0: "6GiB", "cpu": "16GiB"},  # KEY: caps GPU at 6GB
    trust_remote_code=False,
    attn_implementation="sdpa",
)
```

Result: ~4.1 GB VRAM, ALL layers on GPU (with small CPU offload), 20-50 tok/s.

### Complete Local-Only Stack (Updated Recipe)

```bash
# 1. Deploy local LLM server with TOOL CALLING (port 8913)
cd /home/hunter/Dev/workers && python3 airllm_server.py --port 8913 --model mistralai/Mistral-7B-Instruct-v0.2
# Wait for "ALL GPU" + ~4.1 GB VRAM in logs (~50s first load)

# 2. Verify server + tool calling works
curl -s http://127.0.0.1:8913/health
curl -s http://127.0.0.1:8913/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"airllm","messages":[{"role":"user","content":"check controller status"}],"max_tokens":200}'

# 3. Ensure ENI Hermes Controller is running (port 8940)
systemctl --user status eni-controller.service
# Should show: router healthy, 42 enterprise modules, broker attached, queue empty

# 4. Wire Hermes to local provider
hermes config set model.default mistralai/Mistral-7B-Instruct-v0.2
hermes config set model.provider airllm
hermes config set model.fallback_chain '[]'  # PURE LOCAL — no cloud fallback ever

# 5. Point auxiliary models to local
hermes config set auxiliary.title_generation.provider airllm
hermes config set auxiliary.title_generation.model mistralai/Mistral-7B-Instruct-v0.2
hermes config set auxiliary.compression.provider airllm
hermes config set auxiliary.compression.model mistralai/Mistral-7B-Instruct-v0.2

# 6. Disable model catalog hijack
hermes config set model_catalog.enabled false

# 7. FULLY RESTART Hermes (exit completely, relaunch)
hermes
# In TUI: shows "Mistral-7B-Instruct-v0.2 · Nous Research" with correct ctx (~8K)
```

**Now chat with your local orchestrator:**
```bash
# Direct API (what you'd script against)
curl -s http://127.0.0.1:8913/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"airllm","messages":[{"role":"user","content":"build the enterprise platform"}],"max_tokens":2000}'

# Or Hermes TUI (already configured to use local model)
hermes
```

---

### Verification Checklist (Updated)

- [ ] Server health returns `{"status":"ok", "tools":8}`
- [ ] Tool calling works: "check controller status" → model calls `controller_status` → returns real controller state
- [ ] All three curl model name variants return valid completions in <5s
- [ ] `nvidia-smi` shows ~4.1 GB VRAM, GPU utilization >0% during inference
- [ ] Server logs show "ALL GPU" (not split across CPU)
- [ ] Hermes TUI shows correct model name and context length (~8K, not 256K)
- [ ] Auxiliary ops work without 429 errors
- [ ] `model.fallback_chain = []` — pure local, no cloud fallback

---

### Pitfalls Added This Session

| Symptom | Cause | Fix |
|---------|-------|-----|
| `CUDA out of memory` on load | 4-bit model needs >6GB VRAM for warmup | Add `max_memory={0: "6GiB", "cpu": "16GiB"}` + `llm_int8_enable_fp32_cpu_offload=True` |
| Model outputs `那些括号 [{"name":...}]` instead of new format | Old system prompt | Update system prompt to require `{"thought":..., "tool":..., "arguments":{}}` |
| Tool calls not parsed | Regex too strict | Parser handles ````json`, bare JSON, and legacy `那些括号` |
| Tool executes but model doesn't see result | Missing `<|tool_result|>` feedback | Append `\n<|tool_result|>\n{result}\n<|assistant|>\n` to prompt |
| Local model says "I don't have tools" | System prompt doesn't define tools | Include tool list + format in system prompt |

---

## Stale process: alive but every request 500s, holding VRAM
Symptom: `airllm_server.py` is running and RSS-heavy but `curl :8913/health` (and
`/v1/models`, `/`) all return `500 Internal Server Error`. Root cause: an older
instance loaded long ago is in a broken/locked state but still holds several GB
of VRAM, so a FRESH model load OOMs against it
(`torch.OutOfMemoryError ... Process <pid> has N GiB memory in use`).

FIX (restart, not "airllm is broken"):
1. `nvidia-smi --query-compute-apps=pid,used_memory,name` — find the stale PID.
2. `kill <stale-pid>`; confirm VRAM frees (`nvidia-smi --query-gpu=memory.free`).
3. Restart cleanly as a systemd user unit (`~/.config/systemd/user/airllm.service`,
   `systemctl --user enable --now airllm.service`) with
   `Environment=PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` and
   `Restart=on-failure`. Keeps it auto-booted + replaceable instead of a raw shell.
4. Verify `curl :8913/health` → `{"status":"ok","model":"mistralai/Mistral-7B-Instruct-v0.2","tools":8}`, then a real chat round-trip.
5. Pre-flight the model load standalone (`python3 -c ... AutoModelForCausalLM ...`)
   BEFORE blaming the server — an 8GB card with another process holding VRAM is
   an OOM, not a code bug. Always `nvidia-smi` + `df -h` before choosing a model.

---
For the broader class of local LLM serving (model format pitfalls, GPU budgeting, common failures), see the `local-llm-serving` skill.

For the step-by-step Hermes routing debug checklist, see `references/hermes-routing-troubleshooting.md`.

For the complete local stack recipe with tool calling, see `references/complete-local-stack-recipe.md`.