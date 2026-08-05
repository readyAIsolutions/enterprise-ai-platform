# STATUS_DEMIURGE_MODEL_MINER.md

## Build: ENI Model Miner + ever-expanding catalog + universal-boot Hermes controller

### What was built
1. **ENI Model Miner — enterprise module** (`modules/model_miner/`)
   - Scans local models that have training worth using (ollama, local OpenAI-compat
     endpoints, HF-cache safetensors). Found on this box: controller-free-router,
     Mistral-7B-Instruct-v0.2, all-MiniLM-L6-v2, LLMLingua.
   - Rips each chat-capable model's trained knowledge via a curated 8-topic battery,
     saves each answer to the local KB (deduped, tagged, provenance=model).
   - Exposes each model to Hermes via a local MCP-style tool descriptor + LSP note.
   - Runs as a proper enterprise `@module(name="model_miner")` with initialize /
     health_check / shutdown lifecycle + graceful-degradation facade.
2. **ENI Hermes Controller — module** (`modules/hermes_controller/`, from earlier)
   - Facade over the controller package (expand / route / reinforce).
3. **Ever-expanding catalog** (`eni_controller/enterprise.py`)
   - Change-detection fingerprint: when a new module dir appears, the catalog
     re-scans automatically (no hardcoded list). Verified 42 → 43 on boot.
   - Introspects README/docstrings for modules without static hints.
4. **Universal-boot Hermes controller** (`~/.. /hermes/controller/`)
   - Cross-platform boot: `miner.bat` / `miner.ps1` (Windows), `miner.sh` / `miner.py`
     (Linux) → all delegate to `eni_miner_boot.py` (pure stdlib, works on any CWD/OS).
   - Infinite ever-expanding loop: `--daemon` re-scans + rips new models forever
     (`max_passes=None` = infinite iterations; bounded for tests).
   - Runs as systemd user service `eni-controller.service` (auto-boot via linger).
   - Desktop launcher `.desktop` (boot via double-click).

### Verification (real numbers)
| Check | Result |
|---|---|
| enterprise full pytest | **4188 passed, 1 skipped** (was 4177; +11 from 2 new modules) |
| modules/model_miner tests | **5 passed** |
| modules/hermes_controller tests | **5 passed** |
| integration boot (registry discovery) | **1 passed** (model_miner discovered) |
| controller package tests | **17 passed** |
| ruff (controller pkg) | **All checks passed** |
| ruff (new enterprise modules) | **All checks passed** |
| ruff format idempotency | clean on all changed files |
| catalog growth | 42 → 43 modules auto-discovered (no code change needed) |
| model rip E2E (free-router) | 8/8 topics extracted + saved to KB |
| eni-controller.service | active + enabled (auto-boot) |

### Live model discovery on this box (scan)
- `controller-free-router` (openai_compat, chat-capable) — used for E2E rip
- `mistralai/Mistral-7B-Instruct-v0.2` (hf_cache, trainable) — rippable when served
- `sentence-transformers/all-MiniLM-L6-v2` (hf_cache, trainable)
- `microsoft/llmlingua-2-xlm-roberta-large-meetingbank` (hf_cache, trainable)

### How to boot
- **Linux terminal:** `python3 ~/.hermes/controller/eni_miner_boot.py --daemon --interval 300`
- **Windows:** `miner.bat --daemon` (or `miner.ps1 --daemon`)
- **systemd:** `systemctl --user start eni-controller` (already enabled)
- **Desktop:** "ENI Model Miner" launcher

### What adds R / what to drop
- ADD: every module dir is auto-picked-up — catalog stays evergreen as LO adds
  modules. This is the highest-leverage design choice.
- KEEP: infinite loop bounded only by `max_passes` (default infinite) so new
  downloads get ripped automatically.
- DROP: nothing — the facades degrade gracefully when the controller package isn't
  installed, so the enterprise repo stays importable on any box.

### UNVALIDATED
- **Real local-GPU rip** (Mistral on :8913) not run live — the E2E used the
  free-router chat endpoint. The identical pipeline will work against a local
  endpoint once airllm/transformers server is running; the `/chat` call is generic
  OpenAI-compatible.
- **Windows boot** not executed (no Windows box here) — scripts are pure-stdlib and
  follow the standard python-invocation pattern, but untested on an actual Windows
  host.
- Full ripping of ALL local models into KB not yet done at scale (only free-router
  was ripped in the smoke test).
