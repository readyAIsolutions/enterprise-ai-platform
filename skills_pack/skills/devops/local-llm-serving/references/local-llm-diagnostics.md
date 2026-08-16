# Diagnosing local LLM backends — Ollama 500 & model-role mismatch

## Ollama returns HTTP 500 on every model call
Symptom: a model downloads fine (`ollama pull` -> "success"), but the first
`/v1/chat/completions` (or `/api/chat`) returns `HTTP 500: Internal Server
Error`. `ollama ps` shows nothing loaded.

Root cause to check FIRST: the `llama-server` runner binary is missing from
the install. A partial Ollama install has only `/usr/local/bin/ollama` (the
launcher, ~38 MB) but no runner. Confirm via journalctl:
`journalctl --user -u ollama --since "-2 min" --no-pager` shows:
  `error starting llama-server: llama-server binary not found
   (checked: /usr/local/lib/ollama/llama-server, ...)`
  `Run 'cmake -S llama/server --preset cpu && cmake --build --preset cpu'`
Check the dist dir:
  `ls -laR /usr/local/lib/ollama/`  -> should contain `ollama` + `llama-server`
  (here it only had `cuda_v12/`, no runner).

Fix: complete the install so the official distro tarball lays down the runner
(the official script pulls the full tarball that includes `llama-server`):
  `curl -fsSL https://ollama.com/install.sh -o /tmp/ollama_install.sh && \
   sudo sh /tmp/ollama_install.sh`
Then confirm `ls /usr/local/lib/ollama/` now has a `llama-server`.
NOTE: this uses sudo + network. If LO blocks it, do NOT force it — stop and
offer the cached-model alternative (below). Note also a 7B wants more than the
~2.3 GB free when the controller brain (:8913) already holds 5.5 GB of an 8 GB
GPU, so even a fixed Ollama running a 7B will partially fall back to CPU.

## Model-role mismatch (fine-tune is not a general chatbot)
When a local model answers arithmetic with orchestration-flavored text
(e.g. "12*7" -> "The controller has 12 modules loaded..."), it is a
TOOL-CALLING fine-tune, not a general chat model. Check the merges/model card:
  `cat <model_dir>/README.md` -> `base_model`, `model_name`, "sft"/"trl".
A high-step tooling fine-tune (e.g. eni-controller: 29,772 steps of
Mistral-7B for routing/secret_get/queue_job) is good at orchestration, bad
at math/chat. For a chat pane pick a GENERAL INSTRUCT model; verify with a
minimal probe: "Compute 12*7. Reply with ONLY the number." (no system prompt
is cleanest; a long system block makes small models regurgitate it verbatim).
