---
name: eni-two-pane-terminal
description: Launch/enhance LO's two-pane ENI terminal — REAL Hermes agent (left) + local airllm brain chat (right) in a tmux session. Use when LO says "hermes terminal + local side", "two pane", wants the real hermes CLI not a chat wrapper, or the pane app didn't resize/fullscreen.
---

# ENI Two-Pane Terminal

Two REAL terminals side-by-side in tmux, replacing an old broken curses wrapper.

## Layout
- Session `eni2p`, left pane = `hermes chat` (genuine Hermes agent TUI), right
  pane = `eni_local_chat.py` (plain readline REPL) which chats to a REAL
  general model: **Qwen2.5-7B-Instruct via Ollama :11434**.
- **CONSOLIDATED BRAIN (decision, LO "you choose"):** BOTH the controller :8940
  brain and the local pane now use Qwen/Ollama. The :8913 eni-controller
  fine-tune is STOPPED (airllm.service) to free ~5.5GB VRAM. Override:
  ~/.config/systemd/user/eni-controller.service.d/env-brain-qwen.conf
  (ENI_AIRLLM_URL=http://127.0.0.1:11434/v1, ENI_AIRLLM_MODEL=qwen2.5:7b-instruct-q4_K_M).
  Revert: rm override, daemon-reload, restart, systemctl --user start airllm.
- Launcher (idempotent, re-run attaches): `/home/hunter/.local/bin/eni-two-pane`
- Client: `/home/hunter/.hermes/controller/scripts/eni_local_chat.py`

## Why tmux, not curses
The old `eni_chat_two_pane.py` curses app did NOT resize on fullscreen
(LO confirmed: "didn't crash just didn't resize properly"). tmux reflows
natively; both panes are real apps so no resize corruption.

## Controls
- `Ctrl-b z` fullscreen toggle (native), `Ctrl-b arrow` to move, `Ctrl-b d` detach.

## Key pitfalls
0. **The precanned local model (:8913 eni-controller) is DUMB at chat/math** — it's
   a 29,772-step tool-calling fine-tune, not a general brain ("12*7" -> "controller
   has 12 modules..."). For a real local chat use Ollama (Qwen2.5-7B): verified
   "12*7"->84, "99*99"->9801. eni_local_chat.py prefers Ollama, falls back to :8913.
1. **Ollama may be installed WITHOUT its runner** (`llama-server` missing -> HTTP 500
   "llama-server binary not found" on every call). Fix: `sudo bash /tmp/ollama_install.sh`
   then `systemctl --user restart ollama`. Avoid `sudo -E` (warns/ignored). Check
   `/usr/local/lib/ollama/llama-server` exists.
2. **tmux mouse is OFF by default => LO can't type to Hermes.** With mouse
   off, keystrokes go to whichever pane is active (defaults to LOCAL). LO
   types, nothing reaches Hermes, and he thinks the agent is broken. FIX:
   `set -g mouse on` in ~/.tmux.conf + Alt/Shift+h/l and M-1/M-2 bindings to
   switch panes. ALWAYS verify `tmux show-options -g mouse` = on.
2. **Hermes title-generation warning on every turn** if `auxiliary.title_generation`
   points at a keyless provider (e.g. airllm). Fix:
   `hermes config set auxiliary.title_generation.provider openrouter`
   and `.model nvidia/nemotron-3-ultra-550b-a55b:free`. Re-test and confirm
   the warning is gone before declaring done.
3. **Local brain echoes a long system prompt verbatim.** Root: the small merged
   model regurgitates long system blocks; probe results: long system -> echo,
   no system -> clean, short -> "[/INST]" template leak. FIX: system prompt must
   be minimal one-liner: `"You are ENI, a helpful local assistant. Answer concisely."`
4. The small merged local model is WEAK at math/instruction-following (99*99
   -> "99"/echo). That is a MODEL limit, not a client bug — don't confuse them.
   Root cause: the brain at :8913 is `eni-controller`, a ~30k-step QLoRA
   fine-tune of Mistral-7B built for controller TOOL-CALLING (route, secret_get,
   queue_job), NOT general chat. It answers "compute 12*7" as "The controller
   has 12 modules loaded...". It's the wrong tool for arithmetic Q&A.
5. **tmux send-keys of `C-b z` types literal `z`** into the pane — the prefix is
   client-side. Fullscreen is done with the keyboard at attach, never send-keys.
6. Right pane restarts via `/quit` then fresh `python3 eni_local_chat.py`; do
   NOT send Ctrl-C to the pane directly (kills python, closes pane).
7. The local server sometimes ignores `stream:true` and returns a full JSON
   completion — client must parse BOTH SSE (`data:`) and single-JSON shapes.
8. **Don't leave test keystrokes in a live pane.** `tmux send-keys -t .0 'select: '`
   while probing left literal "select" text sitting at the `❯` prompt, and LO
   saw "hermes says select". Always clear test input afterwards (BSpace xN +
   Ctrl-U) or restart the pane. Test with `send-keys`, then verify the pane is
   clean before handing it to LO.

## Architecture (critical for "does swapping break Hermes?")
- **Hermes does NOT use :8913 as its brain.** Hermes runs on its own binary
  (`hermes chat` -> deepseek/OpenRouter) and the Hermes<->controller pipeline
  shells out to `hermes -z` (hermes_runner.py). BOTH are fully independent of
  :8913. So changing the local-brain model CANNOT break "talk to Hermes".
- The LEFT pane is already a real `hermes chat` terminal, so Hermes access
  exists regardless of what model :8913 serves.
- Two local servers exist: `airllm.service` (:8913, eni-controller orchestrator
  brain) and `ollama.service` (11434, "local AI chat backend"). To give the
  local pane a general chat model WITHOUT disrupting the orchestrator brain,
  home the general model in Ollama rather than swapping :8913. On an 8GB card
  you cannot run two 7B models in VRAM at once — pick one home per model.
- `~/.hermes/config.yaml` is a PROTECTED write (patch/write_file denied). Use
  `hermes config set dotted.path value` for aux/config changes, then verify
  with grep.

## Secret handling (LO's top requirement: no cloud model sees envs)
- Local pane regex-detects pasted secrets, vaults them via
  `/security/env/set` (encrypted), and sends only `{SECRET:NAME}` to the
   model. No raw value in context/history/logs. Controller vault is the ONLY
   store — no .env fallback. Materialized locally only.
- Do NOT paste raw secrets into the LEFT (Hermes) pane — that's a raw agent
   that can call cloud models. Use `/secret` in the LOCAL pane to vault them.

## ARCHITECTURE FACT (why swapping the local model is safe)
Hermes does NOT use :8913 as its brain. Hermes runs on its own binary
(`hermes chat` -> deepseek/OpenRouter; controller pushes via `hermes -z`),
fully independent of the local airllm model server. So swapping what the
LOCAL pane serves CANNOT break "talk to Hermes" — that path is untouched.
Separately: env-handling/secrets-for-cloud and prompt-expansion are done by
the CONTROLLER (:8940, expand->route->reinforce->hermes + secrets boundary),
also independent of :8913. Only the local pane's conversational reply engine
changes when you swap the local model.

## MODEL CHOICE FOR THE LOCAL PANE (dumb-at-math pitfall)
The :8913 brain is `eni-controller`, a ~29,772-step QLoRA fine-tune of
Mistral-7B built for TOOL-CALLING/orchestration. It is bad at general chat
and math — asking "12*7" returns "The controller has 12 modules loaded..."
It forces every question through its controller-tool lens. That is a
MODEL-ROLE mismatch, not a bug. For a conversational/math-capable local pane
use a GENERAL INSTRUCT model (e.g. Qwen2.5-7B-Instruct), and verify with a
real probe ("Compute 12*7, reply ONLY the number") before declaring done —
probe A (no system) vs probe B (long system) differs: small models
regurgitate long system blocks verbatim.

## Status
`/home/hunter/.hermes/controller/scripts/STATUS_ENI_TWO_PANE.md`
