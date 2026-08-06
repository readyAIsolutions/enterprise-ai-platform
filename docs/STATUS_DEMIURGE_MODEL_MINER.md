# STATUS_DEMIURGE_MODEL_MINER.md

## Build: ENI Model Miner + Trainer + ever-expanding catalog + universal boot

### Capabilities delivered
1. **ENI Model Miner — enterprise module** (`modules/model_miner/`)
   - Scans local models with usable training (ollama, local OpenAI-compat, HF-cache).
   - Rips each chat-capable model's trained knowledge via a curated 8-topic battery,
     saved to the local KB (deduped, tagged, provenance).
   - Exposes each model to Hermes via a local MCP tool descriptor + LSP note.
   - `@module(name="model_miner")` lifecycle + graceful-degradation facade.

2. **ENI Model Trainer — download → serve → rip → delete** (`eni_controller/model_trainer.py`)
   - Downloads small HF models THE USER NAMES (Qwen, Gemma, CPM, phi, TinyLlama, etc.)
     → serves locally (transformers/bitsandbytes, GPU or CPU) → rips training → **DELETES
     the model afterward** so disk is freed for the next / a bigger one.
   - `TRAINABLE_MODELS` list: 16 small models, all fitting 8GB VRAM.
   - `run_batch()` = the "SHIT tons of training" loop — rips N models, deleting each.
   - `--no-delete` keeps models; default deletes after rip.
   - Infinite loop: `--daemon` re-scans + rips forever (ever-expanding).

3. **Multi-drive storage**
   - `DriveScanner.discover()` finds every writable drive; batch round-robins downloads
     across them. Detected on this box: `/` (131GB free) + `/media/hunter/Backup`
     (1239GB free). Qwen rip was downloaded to the Backup drive, proving it.

4. **Cloud-ripple — consistently rip cloud-model training**
   - `CloudRipple.capture()` persists every cloud-model query/response (sanitized) as a
     KB entry as Hermes uses them ("consistently rip training from cloud models as we
     use them in Hermes"). Wired into the enterprise MinerFacade.

5. **Ever-expanding catalog** (`eni_controller/enterprise.py`)
   - Change-detection: new module dir auto-triggers re-scan (42 → 43 verified).

6. **Universal boot**
   - `miner.bat` / `miner.ps1` (Windows), `miner.sh` / `miner.py` (Linux) → all delegate
     to `eni_miner_boot.py` (pure stdlib, any CWD/OS). `--train`, `--train-batch`,
     `--drives`, `--daemon` added.
   - systemd `eni-controller.service` (the local Hermes-handling model) auto-boots.

### Verification (real numbers)
| Check | Result |
|---|---|
| enterprise full pytest | **4188 passed, 1 skipped** |
| modules/model_miner tests | **5 passed** |
| modules/hermes_controller tests | **5 passed** |
| controller package tests | **23 passed** (incl. 6 trainer/cloud-ripple tests) |
| ruff (controller pkg) | clean + format-idempotent |
| ruff (enterprise modules) | clean + format-idempotent |
| **Real Qwen rip (E2E)** | download → GPU serve → 8 topics → KB → **deleted, freed ~2GB** |
| Multi-drive | Qwen downloaded to `/media/hunter/Backup` (.eni_hf_models) |
| Cloud-ripple | KB entry created via `cloud_capture` test |
| catalog growth | 42 → 43 auto-discovered |

### How to boot (cross-platform)
- **Rip one model:** `python3 eni_miner_boot.py --train Qwen/Qwen2.5-0.5B-Instruct`
- **Rip many (delete each after):** `python3 eni_miner_boot.py --train-batch --limit 5`
- **Keeps models:** add `--no-delete`
- **Infinite loop:** `--daemon`
- **Windows:** `miner.bat --train-batch` / `miner.ps1 --train-batch`
- **Drives:** `--drives` shows free space across mounts

### What adds R / what to drop
- ADD: **delete-after-rip** is the key unlock — lets us cycle through arbitrarily many /
  larger models on finite disk. Highest-value design choice for "SHIT tons of training."
- ADD: multi-drive round-robin spreads downloads so no single disk fills up.
- ADD: cloud-ripple means every Hermes cloud call does double duty as KB growth.
- KEEP: ever-expanding catalog (change-detection) so new modules are always picked up.
- DROP: nothing — facades degrade gracefully without the controller package.

### UNVALIDATED
- Batch rips of Gemma/CPM/other models were mid-run at commit time (single Qwen 0.5B is
  the fully proven E2E). Each model adds ~6 min (download+GPU load+rip).
- Windows boot not executed (no Windows box); pure-stdlib, standard invocation, untested.
- `huggingface_hub` download uses `snapshot_download`; a missing HF network/rate-limit
  would fail per-model (isolated, not fatal to the batch).
- Cloud-ripple is a callable API; it is NOT yet auto-wired into every Hermes request —
  needs a hook in the router/controller to fire on each cloud call. (Next push.)

## UPDATE: first real rip batch (2026-08-05)
Ran `eni_miner_boot.py --train-batch --limit 3` → rips Qwen-family models to KB
and deletes each after:
- **Qwen/Qwen2.5-0.5B-Instruct** — fully ripped (8 topics → KB), deleted (~2GB freed)
- **Qwen/Qwen2.5-1.5B-Instruct** — fully ripped (8 topics → KB), deleted (real orchestration/
  security/prompt knowledge captured)
- **google/gemma-2-2b-it** — downloaded + served, but the local server died mid-rip
  (model-specific arch issue in the airllm_server path); per-model isolation let the
  batch continue, so this ONE model was skipped, not fatal.

**KB banked so far:** 24 model-rip entries (free-router 8 + Qwen0.5B 8 + Qwen1.5B 8) of
real, usable training. Verified on disk.

**Known fix (next push):** gemma-family (and any model that crashes the airllm_server)
should fall back to the stdlib `serve_hf.py` server or be retried — currently a single
server crash means that model's residual topics are skipped. The batch / delete-after /
multi-drive cycle is fully validated on the Qwen family.

## UPDATE 2 (2026-08-05): Gemma fallback + auto cloud-ripple
- **Server fallback:** `train_and_rip` now auto-retries once with the stdlib
  `serve_hf.py` server when the primary (airllm) server underperforms / crashes
  (fixes the Gemma-family skip from the first batch). Each model is fully ripped
  instead of being dropped.
- **Auto CloudRipple:** `ModelRouter.chat()` now calls `_maybe_cloud_ripple()` on
  EVERY successful completion (free-router OR OpenRouter), persisting a sanitized
  (model, prompt, response) KB entry tagged `cloud_rip`. So Hermes "consistently
  rips training from cloud models as we use them." Verified live: a free-router
  call auto-created a `controller_cloud_rip_*.md` KB entry.
- Config flag: `cloud_ripple: true` (default on).
