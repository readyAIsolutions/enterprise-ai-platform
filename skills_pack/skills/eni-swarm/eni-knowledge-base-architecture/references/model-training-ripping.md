# Model Training Ripping (download → serve → rip → delete)

Feeds LO's local KB with real training from local AND cloud models. Two distinct
concerns — keep them separate (LO corrected this):

- **The local model that handles Hermes** (ENI Hermes Controller on `:8931`) is a
  UNIVERSALLY-BOOTABLE, infinite-iteration program → boots cross-platform, runs forever.
- **The Model Miner / Trainer** is an **enterprise MODULE** (in the enterprise repo),
  NOT a standalone bootable program and NOT a dashboard feature.

## Pipeline (validated E2E on this box)
`download → serve → rip → delete`, across multiple drives.

1. **Scan**: `eni_controller/model_miner.py` LocalModelScanner finds ollama /
   local OpenAI-compat endpoints / HF-cache safetensors.
2. **Download**: `model_trainer.py` pulls a HF model via `snapshot_download`,
   round-robin across ALL writable drives (DriveScanner.discover()). On this box:
   `/` (131GB) + `/media/hunter/Backup` (1.3TB). `HF_CACHE` config controls dest.
3. **Serve**: `serve_hf.py` (stdlib OpenAI-compatible) or the existing
   `/home/hunter/Dev/workers/airllm_server.py` (transformers+bitsandbytes 4-bit GPU).
4. **Rip**: curated 8-topic battery (agent-orchestration, enterprise-security,
   prompt-engineering, local-llm-serving, knowledge-management, testing-agents,
   system-monitoring, privacy-architecture) → each answer saved to KB as a deduped
   entry (tags `model_rip`, `hf_cache`, provenance=model) + MCP tool descriptor + LSP note.
5. **Delete**: AFTER rip, delete the downloaded model to free disk so the next /
   a bigger model fits. This is the key unlock for "SHIT tons of training".

Verified real run: Qwen2.5-0.5B-Instruct + Qwen2.5-1.5B-Instruct fully ripped
(8 topics each) and deleted (~2GB freed); free-router ripped (8); **24 KB entries**.

## CLI (cross-platform, all delegate to eni_miner_boot.py)
- `python3 eni_miner_boot.py --drives` — show drives + free space
- `python3 eni_miner_boot.py --train <HF_ID>` — rip one model (delete after)
- `python3 eni_miner_boot.py --train-batch --limit N` — rip N models, delete each
- `--no-delete` keeps models; `--daemon` = infinite ever-expanding loop
- Windows: `miner.bat` / `miner.ps1`; Linux: `miner.sh`

## Cloud-ripple (consistently rip cloud training as Hermes uses them)
`ModelRouter.chat()` calls `_maybe_cloud_ripple()` on EVERY successful completion
(both free-router and OpenRouter paths), persisting a sanitized (model, prompt,
response) KB entry tagged `cloud_rip`. Config flag `cloud_ripple: true` (default).
Verified: one live router call auto-created `controller_cloud_rip_*.md`.

## Pitfalls
- **Gemma-family (and any model that crashes the airllm_server path)**: `train_and_rip`
  must fall back once to the stdlib `serve_hf.py` server when the primary underperforms/
  crashes, so the model is fully ripped instead of skipped. Per-model isolation keeps a
  single crash from failing the batch.
- **Delete-after placement**: only delete after the FINAL rip attempt (not on the primary
  server's first failure) or you destroy the model before the fallback rip.
- **`run_batch` drive round-robin**: use `enumerate(models)` per model; never a manual
  counter.
- **HF download** may need `HF_TOKEN` for higher rate limits; unauthenticated works but
  slower.
- **Big batch timing**: ~6 min/model (download+GPU load+rip); a `--limit 6` batch ≈ 35-40
  min. Run in background with notify-on-complete.
- **chair-dupe**: re-ripping the same model/topic dedupes in the KB (search by dedupe_key),
  so KB count may stay flat while the session still fully processed+deleted each model.

## "Infinite iterations" / ever-expanding catalog
Enterprise catalog (`eni_controller/enterprise.py`) uses a `_fingerprint()` of the
modules dir; when a NEW module dir appears it auto-rescans (42 → 43 verified, no code
change). `ModelMiner.infinite_loop()` re-scans + rips new models forever (`max_passes=None`
= infinite; bounded only for tests).
