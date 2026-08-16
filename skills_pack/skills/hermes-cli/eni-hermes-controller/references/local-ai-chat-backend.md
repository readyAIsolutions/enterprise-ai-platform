# Make the controller a REAL local AI chat — not a cloud shim

## LO's standing rule (learned the hard way, 2026-08-05)

When LO says the controller "doesn't work like an ai chat", he means the
controller must feel like talking to a real LLM — and the backend must be a
LOCAL model on his box, not a round-trip through the free-router → cloud shim.
He killed the free-router-first chat path as "ass". The local chat backend is
either **airllm** or **Ollama**; LO's preference order this session was
"use ollama" then he settled on "ok then use airllm" (the existing Mistral-7B
orchestrator was already built for exactly this).

## Backend options on this box (RTX 3060 Ti 8GB, Ryzen 9 3900X 24T, 30GB RAM)

- **airllm** — `http://127.0.0.1:8913` — Mistral-7B-Instruct-v0.2 4-bit as the
  "orchestrator brain" with TOOL CALLING. It already proxied into the controller
  (:8940), the security server (:8931), and free-router (:8920) via JSON tool
  turn-taking. `GET /health` → `{"status":"ok","model":"...","tools":8}`.
  This is the intended local-brained experience — LO's tool-calling harness.
- **Ollama** — `http://127.0.0.1:11434` — `ollama pull qwen2.5:7b` (best
  quality-per-VRAM for 8GB chat), or qwen2.5:3b for max speed/headroom. Also
  served as a systemd user unit. Prefer airllm when its tool-calling harness is
  wanted; prefer Ollama to train/serve our own model later.

## Deciding factor before wiring chat: SCAN THE HARDWARE FIRST

LO: "scan my fucking hardware find best model". Do NOT pick a model blind. Run
`nvidia-smi --query-gpu=memory.total,memory.free,name` + `lscpu` + `free -h`
first. Watch for **another process already eating VRAM** — a stale airllm/other
server can hold 4-6GB and OOM any new model load even though the card is 8GB.

## Wiring rule

Route `/chat` and `/v1/chat/completions` on the controller through the local
model backend (airllm or Ollama), keeping `SecretsBoundary` sanitize-on-egress
in front. Never make free-router/cloud the primary interactive chat path. If LO
later trains his own model, point the same backend at that model in Ollama.

## Pitfall: stale GPU inference process 500s while holding VRAM

Symptom: `airllm_server.py` process is alive and RSS-heavy but every request
returns `500 Internal Server Error` (even `/health` or `/`). Root cause: an
older instance loaded long ago is in a broken/locked state and still holds
multiple GB of VRAM, so a fresh model load OOMs against it
(`torch.OutOfMemoryError ... Process <pid> has N GiB memory in use`).

FIX (not "airllm is broken"):
1. `nvidia-smi --query-compute-apps=pid,used_memory,name` — identify the stale PID.
2. `kill <stale-pid>`, confirm VRAM frees (`nvidia-smi memory.free`).
3. Restart cleanly as a systemd user unit (`airllm.service`, enabled +
   `Restart=on-failure`, `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`) so it
   auto-boots and restarts on failure instead of running as a raw `nohup` shell.
4. Verify `curl :8913/health` → ok, then a real chat round-trip.

Keeping long-lived model servers as raw background shells is the trap; give each
a systemd unit so lifecycle is managed and a stale instance is trivially replaceable.
