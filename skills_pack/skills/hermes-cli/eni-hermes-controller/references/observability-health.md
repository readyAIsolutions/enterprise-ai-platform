# ENI Hermes Controller — Observability, Health, and Pitfalls

Added during the 2026-08-07 enterprise hardening pass.

## Component health (`/health`)
The controller exposes a real component-level health check at `GET http://127.0.0.1:8940/health`
(and via CLI `python3 -m eni_controller.controller health`). It probes:
- `airllm` — local orchestrator brain (:8913)
- `free_router` — cloud free-model shim (:8920)
- `secrets` — SecretBroker attached? vault entries? audit-chain integrity?
- `enterprise` — catalog module count + with_tests
- `hermes_runner` — hermes binary on PATH?
- `queue` — pending job count

Report has per-check `ok` + an `overall.healthy` (all CRITICAL = {airllm, free_router, secrets} ok).

## Metrics (`/metrics`)
`GET http://127.0.0.1:8940/metrics` (and `... metrics` CLI) returns a thread-safe rolling
snapshot: per-provider ok/fail/rate-limit windows, latency p50/p95/avg, event ring buffer,
counters. Powered by `eni_controller/observability.py`. Never stores secret values.
Also included in `/status` under `metrics`.

## New CLI subcommands
`python3 -m eni_controller.controller {status|health|metrics|catalog}` — catalog dumps all
modules with their capability + `[tests]` flag.

## PITFALL — AirLLM health path
AirLLM serves `/health` at the server ROOT (`http://127.0.0.1:8913/health`), NOT under the
`/v1` API prefix. `urllib.request` does NOT normalize `..` path segments the way `curl` does,
so hitting `base_url + "/../health"` (= `/v1/../health`) returns 404 and falsely reports the
brain as unreachable even when it's up. Derive the root by stripping a trailing `/v1` from
`base_url` before appending `/health`.

## Free-model pool (config.py)
`DEFAULT_FREE_MODELS` now holds 12+ latest free models (DeepSeek V3.1, SambaNova DS-V3.1,
Upstage Solar Pro, Zhipu GLM-5.2, Nemotron family, Llama 3.1 405B, Qwen 2.5 72B, Mistral
Large 2). Keep this rotated as providers daily-cap / delist.

## PITFALL — CUDA OOM on the 8 GB GPU (local brain / airllm_server.py)
The trained Mistral-7B 4-bit brain (`eni-controller/merged`) used ~6.75 GB of the 3060 Ti's
8 GB at rest, leaving ~105 MB free — so multi-round tool loops (controller_expand → chat →
secrets) OOM'd and returned `Generation failed: CUDA out of memory`. Fixes (all in
`~/Dev/workers/airllm_server.py`):
1. `max_memory={0: "5GiB", "cpu": "24GiB"}` — offload ~1 GB more to CPU, leaving ~2.4 GB
   free at load for generation.
2. Prompt truncation `max_length=2048` (was 4096) — bounds the prefilled KV cache.
3. `torch.cuda.empty_cache()` right after each `generate()` in the tool loop — releases the
   caching allocator's generation peak back to free memory so multi-round loops don't
   ratchet up to OOM (verified: stays ~5.4 GB / 2.4 GB free instead of 7.4 GB).
4. `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` is already in the airllm.service
   Environment (helps fragmentation but is NOT sufficient alone).
Signs it worked: `nvidia-smi` free memory ≥ ~2.3 GB after load; multi-round expand/chat
completes with no `"detail"` OOM error. The 7B model's instruction-*abstraction* is weak
("your response" on complex re-format asks) but tool execution is correct — judge tool
calls by the action taken, not the model's prose summary.

## PITFALL — 7B tool-following is unreliable; use a deterministic verified footer
The fine-tuned 7B (`eni-controller/merged`) reliably EXECUTES tools but is NOT reliable at
(a) choosing the right data tool, or (b) reporting real result numbers — it hallucinates
plausible counts (e.g. "10 modules" / "12 modules" / "19 modules" when the real total was
47). Tilting the system prompt does NOT fix this: it's a model-capability floor at 7B scale.
Prompt experiments observed:
- Fenced/pretty JSON prompt → weak prose, tools not used.
- Inline example → model parrots the example's stale/fake values (999/889/"placeholder")
  even with explicit "never reuse" instructions.
- No example → model still invents numbers.

**The working fix (deterministic, in `airllm_server.py`):**
1. `_render_verified(name, result)` renders REAL fields from the actual tool result
   (status→total/with_tests/queue/free-router; expand→build_mode/recommended_modules/char
   count; secret_get/set→key only, value ALWAYS redacted; curl the rest to pass-through).
2. Keep `last_results` in the tool loop; after generation, append a `[verified]` footer to
   the reply from `_render_verified` for every successful tool call — so LO sees ground
   truth even when the 7B's prose misreports.
3. Deterministic fallback: if the user request is a status/count/health question and no
   `controller_status` ran, the server calls it ITSELF and appends the real numbers.
Result: LO always gets correct data; the model's prose is secondary. To *improve the prose*
(not just guarantee the numbers), re-fine-tune with faithful tool-use → summarization
traces (QLoRA, hours) — the deterministic layer stays as-a safety net regardless.

## Enterprise module test harness
Some enterprise `modules/<name>/__init__.py` files reference sibling submodules that aren't
implemented yet and thus crash on import. The repo root `conftest.py` pre-registers the
affected packages (e.g. `modules.rag`, `modules.mlops_lifecycle`) as lightweight namespace
packages (guarded by `os.path.isdir`) so the real implemented files stay testable. If adding
tests to a module whose `__init__.py` is broken, follow that conftest pattern rather than
editing imports ad hoc.
