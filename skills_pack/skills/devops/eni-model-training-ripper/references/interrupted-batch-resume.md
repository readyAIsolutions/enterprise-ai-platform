# Interrupted batch → resume pattern (2026-08-05)

Learned when a `--train-batch --limit 6 --deep` run was SIGTERM'd (exit -15)
mid-download. Distilled into a repeatable recovery flow.

## The failure signature
- Background process notifies: completed with exit code -15 (SIGTERM).
- The batch was killed during the DOWNLOAD phase (log shows only `Fetching N files`
  hf_hub progress bars), so **NOTHING was banked** — KB model-rip count unchanged.
- A kill in the download phase leaves `*.incomplete` blobs in the HF cache
  (e.g. Mistral-7B partials totalling ~5.4GB across 3 `.incomplete` shafts).

## The key fact that saves time
Huggingface hub resumes `*.incomplete` blobs automatically. A relaunch of the SAME
model does NOT re-download the whole snapshot — it continues from the partial bytes.
Evidence: a fresh `--train-batch` jumped straight to `Fetching 7 files: 29%` within
~20s because it picked up an existing `.incomplete` shaft instead of starting at 0.

So: **an interrupted download is NOT wasted work.** Don't delete the `.incomplete`
blobs (that forces a full re-download). Just relaunch.

## Recovery checklist before relaunching
1. Confirm the process is really dead: `pgrep -f eni_miner_boot` (empty = gone).
   Note: a stale PID can linger briefly during teardown — re-check once if it appears.
2. Confirm no orphaned server on the trainer port: `ss -ltnp | grep 8613` (expect free).
3. Confirm GPU is available: `nvidia-smi` (expect low used MiB, not a held 7B).
4. Confirm free-router still up: `curl -s localhost:8920/v1/models`.
5. Check KB count before AND after so you know what (if anything) got banked:
   `ls ~/.eni/kb/controller_model_rip_*.md | wc -l`.
6. Only then relaunch with proper background tracking (see below).

## How to launch the batch so this doesn't bite
Use Hermes background tracking + completion notify, NOT a shell background wrapper:
- `terminal(background=true, notify_on_complete=true)` running
  `cd /tmp && python3 ~/.hermes/controller/eni_miner_boot.py --train-batch --limit N --deep`
- Redirect output to a log file you can tail.
- Do NOT use `nohup ... &` / `disown` / `setsid` — the tool rejects them and you lose
  process tracking. Use the native background param instead.

## Verifying success after a resumed batch
- Wait for the completion notification (notify_on_complete fires once).
- Tail the log for the real end (serve + rip + `deleted ... freed ~N MB` + delete),
  not just download progress.
- Confirm KB model-rip count increased by the expected number of models × topics.
- Confirm weights were deleted (disk freed) and no server lingers on :8613.
