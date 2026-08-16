---
name: eni-model-training-ripper
description: >-
  Rip training/knowledge out of models into LO's local KB. Two sources: (a) LOCAL
  models — download small HF models (Qwen/Gemma/CPM/phi/etc.), serve them
  OpenAI-compatible, probe a curated topic battery, save answers to the KB, then
  DELETE the model to free disk for the next/bigger one; (b) CLOUD models —
  auto-capture every cloud exchange the local Hermes-handling controller routes,
  as KB entries. Spans MULTIPLE drives. Use when LO says "rip training", "scan
  local models", "SHIT tons of training", "mine models", "delete after", or wants
  to expand the knowledge base from model weights.
---

# ENI MODEL TRAINING RIPPER

Extracts the trained knowledge out of models (local HF weights OR cloud models
being used) into LO's local knowledge base (`~/.eni/kb`), so the enterprise
platform can reuse it. The key insight LO cares about: mine a model, keep the
knowledge, then DELETE the weights so there's room to mine bigger/better models.

## Architecture (critical — LO corrected this once, don't repeat it)

- The **Model Miner** (`modules/model_miner/` in the enterprise repo) is an
  ENTERPRISE MODULE. It is NOT a separate standalone bootable program.
- The **ENI Hermes Controller** (the local model that *handles Hermes* —
  expand → route → reinforce) is the standalone, universally-bootable program.
  It lives in `~/.hermes/controller/`. Miner is a module it / the platform uses.
- Miner module exposes a facade: `scan/rip/discover` (model_miner) AND
  `train_and_rip/run_batch/drives/cloud_capture` (model_trainer). All degrade
  gracefully when the controller package isn't importable.

## The pipeline (download → serve → rip → delete)

Core file: `eni_controller/model_trainer.py` + `eni_controller/model_miner.py`
under `~/.hermes/controller/`.

1. **Download** — pull small HF models via `snapshot_download`, spread across
   MULTIPLE drives. `DriveScanner.discover()` finds every writable mount
   (home `/` + backup/data mounts); `run_batch` round-robins across them and
   each download picks the drive with most free space.
2. **Serve** — start a headless OpenAI-compatible server. Prefer the existing
   `airllm_server.py`; fall back to stdlib `serve_hf.py` (no FastAPI dep).
3. **Rip** — run a curated topic battery (`KnowledgeRipper.rip`, ~8 topics:
   agent-orchestration, enterprise-security, prompt-engineering, local-llm-
   serving, knowledge-management, testing-agents, system-monitoring,
   privacy-architecture). Each answer → a deduped/tagged KB entry.
4. **Delete-after** — `delete_after=True` (default) removes the weights so the
   next / a bigger model fits. `--no-delete` keeps them. This is what lets LO
   "do bigger ones" on finite disk.
5. **Integrate** — each model gets an MCP-style tool descriptor
   (`local_model_<name>`) + an LSP note + its KB entries.

## Cloud-ripple (consistently rip cloud training as Hermes uses it)

`ModelRouter.chat()` calls `_maybe_cloud_ripple()` on EVERY successful cloud
completion (both free-router and OpenRouter paths). It persists a sanitized
(model, prompt, response) KB entry tagged `cloud_rip`. Flag: `cloud_ripple: true`
(default on in config). Best-effort — never breaks the request.

## Ever-expanding catalog

The enterprise module catalog auto-re-scans when the modules dir changes
(fingerprint of dir names). New module dir → automatically discovered, no
hardcoded list. Verified 42 → 43 by dropping in a module.

## Universal boot (Windows + Linux)

The controller is cross-platform bootable:
- `miner.bat` / `miner.ps1` (Windows) + `miner.sh` / `miner.py` (Linux) all
  delegate to `eni_miner_boot.py` (pure stdlib, runs from any CWD/OS).
- Flags: `--train <model>`, `--train-batch --limit N`, `--drives`, `--no-delete`,
  `--daemon` (infinite ever-expanding loop, rip any newly-appeared model forever).
- Desktop `.desktop` launcher + systemd user service (`eni-controller.service`).

## Verified flow (real numbers from this box)

- Single Qwen0.5B rip: download → GPU serve → 8 topics → KB → deleted, ~2GB freed.
- Batch (limit 3): Qwen0.5B + Qwen1.5B fully ripped (8 topics ea) to KB, deleted;
  Gemma-2-2b server crashed (pre-fallback) → skipped via per-model isolation.
- Cloud-ripple: one live free-router call auto-created a `cloud_rip` KB entry.
- Frontier: 16 trainable small models in `TRAINABLE_MODELS` (Qwen, Gemma, CPM,
  phi, TinyLlama, SmolLM, Olmo, Mistral).

## Pitfalls
- **Silent zero-rip**: a batch can exit 0, download + delete every model, and bank
  ZERO KB entries. See `references/silent-zero-rip.md` for the full signature + fix
  (`topics or []` clobbers the battery default; `deep` not propagated through
  run_batch/train_and_rip; delete-after-rip fires even when saved==0).
- **Interrupted download is NOT wasted work** — HF resumes `*.incomplete` blobs.
  See `references/interrupted-batch-resume.md`.

## References
- `references/silent-zero-rip.md` — exit-0-but-nothing-banked failure + delete-after-rip guard
- `references/interrupted-batch-resume.md` — SIGTERM mid-download resume checklist
- `references/deep-rip-battery-and-value.md` — DEEP_TOPICS battery + value of strong-model rips
- `references/trainer-session-batch.md` — batch run details

## References
- `references/silent-zero-rip.md` — exit-0-but-nothing-banked failure + delete-after-rip guard
- `references/interrupted-batch-resume.md` — SIGTERM mid-download resume checklist
- `references/deep-rip-battery-and-value.md` — DEEP_TOPICS battery + value of strong-model rips
- `references/trainer-session-batch.md` — batch run details

1. **Gemma-family crashes the airllm server mid-rip.** Fixed by a fallback:
   if the primary server yields 0 saved topics / crashes, `train_and_rip`
   auto-retries ONCE with stdlib `serve_hf.py` on a different port. Always
   retry-with-alternate-server before concluding a model can't be ripped.
2. **Per-model isolation** in `run_batch`: one model crashing/failing must NOT
   abort the batch. Wrap each model in its own try/except; report ok/failed.
3. **Delete happens only AFTER final attempt** — don't delete weights on the
   first attempt if you're going to retry with a fallback server.

## Battery choice drives value (see references/deep-rip-battery-and-value.md — expert deep battery vs tiny-model fluff, the strategic verdict.
references/interrupted-batch-resume.md — recovery flow when a --train-batch is killed mid-download: HF `.incomplete` blobs resume on relaunch (don't delete them), verify clean before relaunch, use background+notify not nohup.)
Match the topic battery to model strength: BASIC `RIP_TOPICS` (8 shallow topics) for
tiny models (<~2B), DEEP `DEEP_TOPICS` (`--deep`, 10 expert probes + demanding
"senior staff engineer" system prompt) for strong models (7B+/free-router/strong
cloud). Deep ripping a tiny model returns textbook-level generic prose (MEDIUM value);
deep ripping a strong model returns expert, OWASP-grounded, buildable knowledge (HIGH
value). The compounding asset is the pipeline + auto cloud-ripple (`classify_topic()`
derives KB topic from the actual prompt, wired into both free-router and OpenRouter
paths behind `cloud_ripple: true`), not the tiny-model output. Prefer deep rips of
strong/cloud models.
4. **Writability test before using a drive** — check you can create+delete a
   file under each mount; skip unwritable ones (`S112/BLE001` guarded).
5. **Multi-drive round-robin** — don't pin downloads to one disk; spread so no
   single drive fills up. `--drives` shows free space per mount.
6. **The `***` redactor in tool output** is normal — it masks strings in
   transcripts (`TOKENIZER=AutoTokenizer.from_pretrained(...)` shows as
   `TOKENIZER=***during display). The bytes on disk are correct; verify with
   `python3 -c` repr / `od -c`, not the redacted display.

## References

- `references/trainer-session-batch.md` — real first-batch transcript detail
  (which Qwen/Gemma models ripped/deleted, sizes, the Gemma crash + fallback
  fix, cloud-ripple verification).
