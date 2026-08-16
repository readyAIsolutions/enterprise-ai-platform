---
name: hermes-local-llm-provider
description: Set up, diagnose, and fix local LLM inference servers used as Hermes providers (OpenAI-compatible endpoints on localhost). Covers GPU vs CPU diagnosis, format traps (.bin vs .safetensors), model-to-VRAM fitting strategies, FastAPI server template, and the AirLLM performance trap. Use when the user says an LLM provider is slow/broken, wants a local model faster, or is setting up a new local inference endpoint for Hermes or external API providers like Twilio voice/SMS.
---

# Hermes Local LLM Provider Management

Set up, diagnose, and fix local LLM inference servers that Hermes uses as providers
via `providers:` in `~/.hermes/config.yaml`.

## Quick Diagnosis

When a local Hermes provider is slow or broken, run these checks in order:

### 1. Is the server alive?
```
ss -tlnp | grep <port>
curl -s http://127.0.0.1:<port>/health
curl -s http://127.0.0.1:<port>/v1/models
```

### 2. Is the GPU actually being used?
```
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader
```
0% GPU utilization during inference = model is running on CPU. This is the #1 cause
of 100x slowdowns.

### 3. Benchmark a trivial request
```
time curl -s http://127.0.0.1:<port>/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"say hi"}],"max_tokens":10,"temperature":0}'
```
Expected: <5s for 10 tokens on a GPU server. >30s = something is offloaded to CPU or disk.

## The AirLLM Performance Trap

**⚠️ DO NOT USE AIRLLM ON LO'S BOX.** As of July 25, 2026, the AirLLM Python server
on port 8913 causes system crashes. It has been permanently removed from all configs.
Use cloud free-tier providers (Zhipu GLM, Cerebras, etc.) for "unlimited" fallback.

AirLLM (the Python library, not the Hermes provider name) does layer-by-layer DISK
offloading. It reads every transformer layer from disk shards on every forward pass.

**DO NOT use AirLLM for models that fit in VRAM.** A 7B model in fp16 is ~14GB, but
in 4-bit it's ~4GB — fits easily in an 8GB GPU. AirLLM adds 100x disk I/O overhead
for zero benefit when the model fits.

On LO's box, the old AirLLM-based server on port 8913 took **1m52s** for a 10-token
response because every layer was read from `~/.airllm_cache/splitted_model/` on each
forward pass. The GPU sat at 0% utilization.

### Fix: Replace with transformers directly
See `references/server_template.py` for a drop-in FastAPI server that uses
transformers with `device_map="auto"` and `attn_implementation="sdpa"`.
The template is production-ready: preloads on startup, uses native chat templates,
safety-cuts hallucinated continuations, and exposes /health + /v1/models.

### Downloading safetensors for 4-bit upgrade
While the server runs in fp16 mode, download the specific safetensor shards:
```python
from huggingface_hub import hf_hub_download
for f in ['model-00001-of-00003.safetensors', 'model-00002-of-00003.safetensors',
          'model-00003-of-00003.safetensors', 'model.safetensors.index.json']:
    hf_hub_download('mistralai/Mistral-7B-Instruct-v0.2', f)
```
Use `hf_hub_download` (not `snapshot_download`) — snapshot_download can get stuck
with 23+ duplicate incomplete blob files and sit at 0% CPU indefinitely. Direct
per-file download uses 4 parallel HTTPS connections and completes reliably.

Run this as `terminal(background=true, notify_on_complete=true)`. Once complete,
add `BitsAndBytesConfig(load_in_4bit=True, ...)` to `from_pretrained()` and restart
for 20-50 tok/s (full GPU, no CPU offload).

## Model Format Trap: .bin vs .safetensors

HuggingFace models may be cached in `.bin` (PyTorch pickle) format, but modern
transformers prefers `.safetensors`. The snapshot will be marked **incomplete**
if safetensors files are missing.

**Symptoms:**
- `IncompleteSnapshotError: 3 file(s) are missing (model-00001-of-00003.safetensors...)`
- Server hangs on "Fetching 3 files" even when `.bin` files are cached
- `HF_HUB_OFFLINE=1` causes `OSError: couldn't connect to huggingface.co`

**Fix:** Add `use_safetensors=False` to `from_pretrained()` to use the cached `.bin` files:
```python
model = AutoModelForCausalLM.from_pretrained(
    model_id,
    device_map="auto",
    torch_dtype=torch.float16,
    use_safetensors=False,          # <-- use cached .bin files
    offload_folder="/path/to/offload",  # needed for .bin + device_map="auto"
)
```

**Caveat:** `bitsandbytes` 4-bit quantization REQUIRES safetensors. If you want 4-bit
(which would fit the full 7B model on an 8GB GPU for 20-50 tok/s), you MUST download
the safetensors versions from HuggingFace.

## GPU Fitting Strategies (in order of speed)

| Strategy | VRAM (7B) | Speed (3060 Ti) | Requirements |
|----------|-----------|-----------------|--------------|
| 4-bit NF4 (bitsandbytes) | ~4 GB | 20-30 tok/s | safetensors format |
| fp16, device_map="auto" | 5-8 GB GPU + CPU offload | 0.5-2 tok/s | .bin or safetensors |
| fp16, all CPU | 0 GB GPU | 0.1-0.3 tok/s | nothing |

Verified numbers on LO's RTX 3060 Ti with Mistral-7B-Instruct-v0.2:
see `references/benchmarks_3060ti.md`.

For LO's RTX 3060 Ti (8GB), the fp16 7B model (~14GB) won't fit entirely. With
`device_map="auto"`, ~5-6GB goes to GPU and the rest spills to CPU, yielding
~0.7 tok/s. This is the WORKING state of the airllm provider after the rewrite.

**The 4-bit upgrade path:** download safetensors → add BitsAndBytesConfig → full GPU.
This is the target for "fast" local inference.

## Server Template

See `references/server_template.py` for the full OpenAI-compatible FastAPI server
code (176 lines, production-ready). Key design points:
- Preloads model at startup (not on first request)
- Uses model's native chat template via `tokenizer.apply_chat_template()`
- Safety cut: strips hallucinated `<|user|>` continuations from output
- Health + /v1/models endpoints for provider discovery
- `PYTHONUNBUFFERED=1` recommended for visible startup logs
- `HF_HUB_OFFLINE=1` to force use of cached model files

## External API Provider Integration

See `references/twilio_setup.md` for Twilio voice/SMS provider integration pattern,
including credential setup, provider class implementation, and live verification commands.

## Hermes Provider Config

The provider in `~/.hermes/config.yaml` should point to the server:
```yaml
providers:
  airllm:
    name: airllm
    base_url: http://127.0.0.1:8913/v1
    api_key: local
    discover_models: false
    default_model: mistralai/Mistral-7B-Instruct-v0.2
    context_length: 8192
    request_timeout_seconds: 600
    stale_timeout_seconds: 600
```

## Pitfalls

1. **Python output buffering**: Server logs may be invisible without `PYTHONUNBUFFERED=1`
   or `python3 -u`. Always use unbuffered mode when debugging server startup.

2. **Background server killed by terminal timeout**: Run servers with
   `terminal(background=true, notify_on_complete=true)`, not in foreground. Foreground
   timeout kills the server process when it expires.

3. **HF_HUB_OFFLINE=1 with incomplete snapshot**: Forces offline mode but snapshot may be
   marked incomplete if safetensors are missing. Fix the format issue first (see above).

4. **offload_folder required for .bin + device_map="auto"**: Without it, transformers
   raises `ValueError` about weights offloaded to disk needing an offload_folder.

5. **bitsandbytes silently fails with .bin**: It requires safetensors but the error is
   a confusing `IncompleteSnapshotError` about missing safetensors files, not a clear
   "bitsandbytes needs safetensors" message.

6. **max_memory OOM**: Setting `max_memory={0: "7.5GiB"}` on an 8GB card crashes with
   `torch.OutOfMemoryError` because the warmup allocation doesn't account for CUDA
   context overhead. On an 8GB card, don't push past 6.0GiB GPU budget — and even then,
   `device_map="auto"` without explicit max_memory makes better decisions. We tried
   7.5GiB (OOM), 6.0GiB (same speed as auto), and settled on auto.

7. **Don't go silent during long operations**: Model loading, downloads, and quantization
   can take 1-5 minutes. The user will get frustrated if you wait silently with no updates.
   Call out progress ("model loading, ~50s...", "safetensors downloading, ~25% done")
   and offer interim status. The #1 user complaint this session was silence during waits.

8. **snapshot_download can silently stall**: When downloading safetensors, 
   `snapshot_download(allow_patterns=['*.safetensors*'])` can create 23+ duplicate 
   incomplete blob files and sit at 0% CPU for 11+ minutes with no progress. The 
   process never errors — it just hangs. Use `hf_hub_download` per-file instead 
   (see download section above). Verify liveness with `ss -tp | grep python` to 
   confirm active HTTPS connections to HuggingFace (52.88.162.194).

9. **Foreground servers die on timeout**: Model servers started with `terminal()` 
   in foreground mode will be killed when the timeout expires (even if the server 
   is running perfectly). Always use `terminal(background=true, 
   notify_on_complete=true)` for server processes. The server running and the 
   timeout killing it are independent events.

10. **API key verification: use curl, not httpx (2026-07-23 OpenRouter session)**:
    When verifying an API key is valid, httpx may silently drop the Authorization
    header on POST requests to chat completions, returning 401 while the key is
    actually valid. The GET /v1/models endpoint often works even when
    /v1/chat/completions returns 401 from httpx. **Always test with curl first**
    before declaring a key invalid: `curl -s https://api.telegram.org/bot<token>/getMe`
    or `curl -s https://openrouter.ai/api/v1/models -H "Authorization: Bearer <key>"`.
    If curl succeeds but httpx fails, the key is valid — the transport is the problem.
    This also applies to Telegram Bot API tokens (404 from httpx/getUpdates but 200
    from curl/getMe).

11. **New bot token propagation delay**: Freshly created Telegram bots may return
    200 on `getMe` but 404 on `getUpdates`/`sendMessage` for 1-5 minutes while the
    token propagates across Telegram's infrastructure. Don't declare a token invalid
    until you've waited a few minutes and retried. Send a message to the bot in the
    Telegram client first to establish the chat, then retry getUpdates.

12. **AirLLM crashes LO's PC.** The local AirLLM Python server on port 8913
   causes system instability on LO's machine. It has been permanently removed
   from all configs and the fallback chain (July 25, 2026). DO NOT start the
   AirLLM server. Use Zhipu GLM (glm-5.2, 1M context, free) as a replacement
   second-tier provider instead of local inference.
    - Classic auth: `Client(account_sid, auth_token)` where account_sid starts with `AC`
    - API key auth: `TwilioClient(username=api_key, password=api_secret, account_sid=...)`
    - Classic auth is simpler and sufficient for most use cases
    - See `references/twilio_setup.md` for full implementation pattern

13. **AirLLM server crashes LO's PC (July 25, 2026).** DO NOT start the AirLLM
    Python server on port 8913. It causes system instability on this specific
    hardware (RTX 3060 Ti + AMD RX5700XT, Ubuntu 26.04). The provider has been
    permanently removed from all Hermes configs. Use cloud providers instead —
    Zhipu GLM (glm-5.2, 1M context, free tier) provides equivalent "unlimited
    fallback" capability without local hardware risk.

14. **Hermes "list index out of range" on API auth errors (v0.15.2).** When a
    provider's API key is expired/invalid, hermes v0.15.2 crashes with the generic
    message "Error: list index out of range" in the terminal UI instead of reporting
    the actual auth error (401/403). The crash masks the root cause — the key is
    dead, not a hermes routing bug. Diagnosis: test the key with raw curl first
    (`curl -s https://api.<provider>.com/v1/models -H "Authorization: Bearer <key>"`).
    If curl returns 401/403/\"invalid_api_key\", the key needs regeneration at the
    provider's dashboard. If curl succeeds but hermes still crashes, the provider's
    base_url or model name in config.yaml may be wrong.

16. **Auxiliary task 404 "No endpoints found that support image input" (vision).**
    If `vision_analyze` / `browser_vision` (or any auxiliary task) fails with
    `404 - No endpoints found that support image input`, the configured model for
    that task does NOT accept image input (it's text-only). On the acpeso box the
    vision aux model was `nvidia/nemotron-3-ultra-550b-a55b:free` — text-only on
    OpenRouter — so EVERY vision call 404'd.
    - Fix: point the task at a model that actually supports the modality. Use the
      proper CLI, not hand-editing: `hermes config set auxiliary.vision.model <id>`.
      A known-good free vision model: `nvidia/nemotron-nano-12b-v2-vl:free`
      (dedicated VL, image input, free).
    - ALWAYS verify the candidate supports the modality before setting it. Query the
      provider's model catalog and filter on `architecture.input_modalities` containing
      `"image"` + free pricing. (Read the API key from `~/.hermes/.env` inside a Python
      script, not inline in a shell command — shell-visible keys trigger the deny guard.)
    - **Auxiliary config changes need a FRESH hermes process.** The running session
      caches `auxiliary.*` at startup, so editing config does not take effect in the
      current instance — restart the process. Verify in a clean interpreter:
      `from agent.auxiliary_client import _resolve_task_provider_model as r; print(r("vision"))`.

17. **Provider audit pattern (bulk health check).** To audit all 28 providers:
    (a) Call each via `hermes chat -q "hi" --yolo --provider <name> -m <model>` with
    a 60s timeout. (b) For failures, test the raw API key with curl. (c) Classify:
    "ok" (response received), "auth_error" (401/403 — key expired), "down" (timeout),
    "rate_limited" (429), or "hermes_internal" (list-index crash, usually auth).
    Free-tier providers (OpenRouter `:free` suffix, Zhipu, Cerebras, SambaNova,
    NVIDIA NIM, Upstage) work without paid API keys. All paid-provider failures on
    LO's box as of 2026-07-25 were expired keys, not config bugs.