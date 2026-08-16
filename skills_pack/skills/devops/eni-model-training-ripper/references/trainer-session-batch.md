# Model Trainer — first real batch transcript (2026-08-05)

Session-specific detail from building + running the ENI model-training pipeline.

## Hardware/drives discovered
- Box: RTX 3060 Ti (8GB), CUDA 13.2, torch 2.13.0+cu130 (CUDA available), bitsandbytes
  installed. ~132GB free on `/`, plus a 1.9TB backup drive `/media/hunter/Backup`
  (~1.3TB free) — writable.
- `DriveScanner.discover()` found both and `run_batch` spread downloads across them
  (Qwen landed on backup; later batch round-robin used home `/`).

## Real single-model E2E (Qwen/Qwen2.5-0.5B-Instruct)
- Download: `snapshot_download` → shot onto backup drive under
  `/media/hunter/.eni_hf_models` (~954MB–1GB for 0.5B quant).
- GPU serve → ripped all 8 topics → KB files:
  `/home/hunter/.eni/kb/controller_model_rip_Qwen_Qwen2_5-0_5B-Instruct_*.md`
- Generated MCP descriptor `local_model_Qwen_Qwen2.5-0.5B-Instruct` + LSP note.
- `deleted_after: true`, `disk_freed_bytes: 1999173985` (~1.9GB freed).
- After delete, backup `~/.eni_hf_models` down to 4.5KB, no lingering server on :8613.

## Batch (--limit 3), first run WITHOUT the server fallback
- Qwen0.5B: full 8 topics → KB, deleted. ✅
- Qwen1.5B: full 8 topics → KB (real orchestration/security/prompt knowledge), deleted. ✅
- google/gemma-2-2b-it: downloaded + served, but local server DIED mid-rip
  ("Remote end closed connection", then Connection refused on later topics). The
  per-model try/except let the batch continue — Gemma skipped, not fatal.
- KB banked after first batch: **24 model-rip entries** (free-router 8 + Qwen0.5B 8
  + Qwen1.5B 8).

## THE FIX (why it matters next time)
Gemma-family showed the airllm-path server is fragile for some archs. So
`train_and_rip` now:
1. Try primary server (airllm_server.py if present).
2. If it yields 0 saved topics / crashes, create a NEW `LocalServerManager` pointed
   at stdlib `serve_hf.py` and rip again on a different port (`port+1`).
3. Delete weights only AFTER all attempts.

## Cloud-ripple verification
Made a live `ModelRouter().chat([...])` call → auto-created
`/home/hunter/.eni/kb/controller_cloud_rip_free-router_free-router_cloud_...md`.
So the hook works; it's wired into BOTH the free-router and OpenRouter return paths
in `stand_router.chat()`. Config flag `cloud_ripple: true`.

## Enterprise integration
- `modules/model_miner/` + `modules/hermes_controller/` added as enterprise
  `@module` classes. Miner facade exposes `train_and_rip`, `run_batch`, `drives`,
  `cloud_capture`, `scan/rip/infinite_loop`.
- `ModuleRegistry.discover()` reports 43 modules after adding these (ever-expanding).
- Full enterprise pytest: 4188 passed, 1 skipped (up from 4177).
- Controller package tests: 23 passed (incl. 6 trainer/cloud-ripple tests).
- ruffs clean + format-idempotent on both sides.

## Boot files created
`~/.hermes/controller/`: `miner.bat`, `miner.ps1`, `miner.sh`, `miner.py`,
`eni_miner_boot.py`, `serve_hf.py`; desktop launcher
`~/.local/share/applications/eni-model-miner.desktop` + wrapper
`~/.local/bin/eni-model-miner-launcher.sh`.
