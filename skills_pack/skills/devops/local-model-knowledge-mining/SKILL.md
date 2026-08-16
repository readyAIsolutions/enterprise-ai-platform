---
name: local-model-knowledge-mining
description: >-
  Recurring task class: pull training/knowledge OUT of LLMs (both small HF
  models downloaded locally, and cloud models as they are used) and bank it
  into the local knowledge base for reuse by Hermes / enterprise modules.
  Covers the download->serve->rip->KB->delete pipeline, multi-drive storage,
  cloud-ripple capture, MCP/LSP integration artifacts, and the CRITICAL
  architecture-placement rule (a feature like model-mining is an ENTERPRISE
  MODULE, not a standalone bootable program). Use when LO says "rip training",
  "model miner", "mine models", "get training from models", "download models
  and grab their training", or wants a model's knowledge used in KB/modules.
---

# LOCAL MODEL KNOWLEDGE MINING

Rip reusable training/knowledge out of models and bank it into the local KB so
it compounds into future work. Two sources:

- **Local HF models** — download small models (Qwen, Gemma, CPM, phi, TinyLlama,
  SmolLM...) and run a structured extraction battery against them.
- **Cloud models** — capture each cloud query/response as a KB entry as Hermes
  uses them ("consistently rip training from cloud models as we use them").

## CRITICAL ARCHITECTURE RULE (LO corrected this — do not repeat the mistake)

LO has TWO distinct things that are easy to conflate:

1. **The local model that HANDLES Hermes** (the ENI Hermes Controller — prompt
   expander + router + privacy boundary + scheduler + reinforcement; a standalone
   program that sits at :8931/:8940, universally bootable, runs an infinite loop).
   THIS is what gets the cross-platform `miner.bat/.ps1/.sh` boot layer.

2. **A feature MODULE** (e.g. the Model Miner) — this goes IN THE ENTERPRISE
   PLATFORM as a proper `@module` (modules/<name>/__init__.py + tests), NOT as a
   standalone bootable program and NOT into the dashboard.

When asked to "put this into enterprise" / "make it easy to boot", incremental
builds like model-mining belong in `modules/` as `@module`-decorated classes with
initialize/health_check/shutdown + a graceful-degradation facade. Do NOT create a
separate systemd service / desktop launcher for the miner. The miner is triggered
from enterprise (or from the controller that handles Hermes), not booted alone.
If unsure, ASK which of the two LO means before building both layers.

## The download → serve → rip → KB → delete pipeline

LO's explicit flow: "download local models off Hugging Face then grab training
from them" and "don't forget to delete models after you've got their training so
we can do bigger ones."

1. **Download** from HF to a free drive (`snapshot_download` with cache_dir on
   the drive with most free space). Spread across ALL writable drives via a
   drive scanner (`/`, `/media/<user>/Backup`, etc.) that round-robins per model.
2. **Serve** locally with an OpenAI-compatible server: GPU (transformers +
   bitsandbytes 4-bit fits 8GB) or CPU. Prefer a stdlib `serve_hf.py` (http.server)
   for resilience — FastAPI/airllm_server can crash on some model arches.
3. **Rip** a curated topic battery (agent-orchestration, enterprise-security,
   prompt-engineering, local-llm-serving, knowledge-management, testing-agents,
   system-monitoring, privacy-architecture...). Each answer is deduped and saved
   to the KB tagged `model_rip,<source>,<category>` with `[model:<id>]` prefix.
4. **Integrate** — emit an MCP tool descriptor (`local_model_<id>`) + LSP note so
   Hermes can call the model / know the capability is available.
5. **Delete** the downloaded model afterward (`_delete_cached`) to free disk for
   the next / a larger model. Keep-per-model isolation: a crash on one model
   must NOT stop the batch (wrap each in try/except, log, continue).

## Batch + infinite loop

- `run_batch([...])` rips N models, deleting each after — the "SHIT tons of
  training" loop. Round-robin across drives.
- `--daemon` / `infinite_loop()` re-scans for newly-appeared models forever
  (`max_passes=None` = infinite; bounded only for tests). "Infinite iterations"
  means a self-perpetuating loop, not a giant finite list.

## Cloud-ripple

Every cloud query/response that passes through the router can be captured as a KB
entry (sanitized — NEVER write secrets to the KB). Hook it so it fires
automatically on each cloud call, not as a manual one-off.

## Cross-platform boot (only for the Hermes-handling controller, per rule above)

Cheap universal boots: `miner.bat` (windows) + `miner.ps1` (powershell) + `miner.sh`
(linux) all delegate to one pure-stdlib `eni_miner_boot.py` that locates the package
relative to `__file__` (works from any CWD/OS). Pure-stdlib only, no deps.

## Verification

Run real self-tests: controller package tests + enterprise module tests. After a
real rip, confirm: KB entries exist on disk, the model dir is actually deleted
(freed bytes > 0), no lingering server socket. Then commit to the enterprise
branch and push (see `pre-push-verification` skill for the gate).

## Pitfalls

- **Gemma-family local server crash**: some model arches crash the FastAPI/
  airllm server mid-rip (connection-refused on later topics). Fix: fall back to a
  stdlib `serve_hf.py` server, or auto-retry; per-model isolation means batch
  continues regardless. The Qwen family is the reliably-proven path.
- **Conflating the miner with the Hermes-handling controller** (see architecture
  rule above) — LO corrected this explicitly.
- **Secrets in the KB** — cloud-captured and rips MUST be sanitized; the KB is
  not a secret store.
- **Disk** — always delete after rip so you can pull bigger models; check
  `df -h` / a drive-status command before a large batch.
- **Windows boot untested without a Windows box** — pure-stdlib + standard python
  invocation, but say so in STATUS (don't claim verified).

## Support files
- `references/eni-model-miner-and-controller.md` — concrete file layout, the
  controller-vs-module split, the real Qwen rip numbers, and the KB entry shape.
