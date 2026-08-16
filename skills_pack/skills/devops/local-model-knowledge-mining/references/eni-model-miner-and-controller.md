# ENI Model Miner + Hermes Controller — session detail

Concrete layout and real numbers from the build session (2026-08-05).

## The controller vs module split (what LO actually wanted)

- **Hermes Controller** = the local model that HANDLES Hermes. A standalone,
  universally-bootable program. Lives at `~/.hermes/controller/`.
  It got the cross-platform boot layer (`miner.bat`/`miner.ps1`/`miner.sh` →
  `eni_miner_boot.py`) AND runs as a systemd user service `eni-controller.service`
  (enabled + linger = auto-boot), with a desktop `.desktop` launcher.
- **Model Miner** = a tool/feature = an ENTERPRISE MODULE. Lives at
  `~/Desktop/Enterprise Builder/enterprise/modules/model_miner/`. Decorated
  `@module(name="model_miner")`, with initialize/health_check/shutdown + a
  `MinerFacade` that degrades gracefully when the controller package is absent.

Mistake made + corrected: I first built the miner as a standalone bootable program
(systemd `eni-model-miner.service` + desktop launcher + universal boot). LO
corrected: "this was for the locally running model that handles hermes not hermes
miner — miner should be a module." Fixed by stopping/removing the standalone miner
service and making it a proper enterprise module.

## File layout (controller package `~/.hermes/controller/`)

- `eni_miner_boot.py` — pure-stdlib cross-platform dispatcher (adds its own dir to
  sys.path; works from any CWD/OS).
- `serve_hf.py` — stdlib `http.server` OpenAI-compatible HF server (GPU 4-bit or
  CPU). Survives model arches that crash the FastAPI airllm server.
- `eni_controller/` package:
  - `model_miner.py` — scan (ollama/OpenAI-compat/HF-cache) → rip (8-topic battery)
    → KB. `LocalModelScanner`, `KnowledgeRipper`, `ModelMiner`, `infinite_loop()`.
  - `model_trainer.py` — download→serve→rip→delete. `DriveScanner.discover()`
    (round-robin across writable drives), `LocalServerManager`, `ModelTrainer`,
    `CloudRipple.capture()`, `TRAINABLE_MODELS` (16 small models).
  - `expander.py`, `router.py`, `secrets.py`, `scheduler.py`, `reinforce.py`,
    `enterprise.py`, `controller.py`.

## Real rip numbers (proven end-to-end)

- `Qwen/Qwen2.5-0.5B-Instruct`: download (to `/media/hunter/Backup` 1.9TB drive,
  1.3TB free) → GPU serve → 8 topics → KB → deleted, freed ~2GB.
- `Qwen/Qwen2.5-1.5B-Instruct`: full rip (8 topics) → KB → deleted.
- `google/gemma-2-2b-it`: downloaded + served, but local server crashed mid-rip
  (arch-specific) → per-model isolation skipped it, batch continued.
- KB banked: 24 model_rip entries (free-router 8 + Qwen0.5B 8 + Qwen1.5B 8).
- Drives: `/` (131GB free) + `/media/hunter/Backup` (1239GB free).

## KB entry shape

```
# [model:Qwen/Qwen2.5-1.5B-Instruct] agent-orchestration
_saved <ts> by ENI controller_ | tags: model_rip, hf_cache, engineering
<real model knowledge content>
```

MCP tool: `local_model_<id>` (description + inputSchema + endpoint + model_id).
LSample LSP note: `Local model '<id>' registered as a local knowledge/code
service (source=hf_cache, endpoint=<url>)`.

## Boot commands

```
python3 eni_miner_boot.py --train Qwen/Qwen2.5-0.5B-Instruct   # rip one, then delete
python3 eni_miner_boot.py --train-batch --limit 5              # rip N, delete each
python3 eni_miner_boot.py --train-batch --no-delete            # keep models
python3 eni_miner_boot.py --daemon                              # infinite loop
python3 eni_miner_boot.py --drives                              # free space across mounts
miner.bat / miner.ps1 / miner.sh ...                            # cross-platform boot
```

## Enterprise module facade methods

`train_and_rip`, `run_batch`, `drives`, `cloud_capture`, `infinite_loop`,
`mine`, `discover`, `status`.
