# Complete Local-Only Stack Recipe (with Tool Calling)

**End-to-end local orchestration: Mistral-7B 4-bit on RTX 3060 Ti (8GB) controls everything.**

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        LO (Human)                               │
└──────────────────────────┬──────────────────────────────────────┘
                           │ terse instruction
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              LOCAL MODEL (Mistral-7B 4-bit)                     │
│  Port 8913 — airllm_server.py with TOOL CALLING                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Tools: controller_expand, controller_chat,             │   │
│  │         controller_status, free_router_chat,            │   │
│  │         secret_get/set, model_mine, queue_job, respond  │   │
│  └─────────────────────────────────────────────────────────┘   │
│  Decision: use tool? → execute → feed result → decide next     │
└──────────────────────────┬──────────────────────────────────────┘
                           │ tool calls
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ ENI Hermes      │ │ Free Router     │ │ Local Security  │
│ Controller      │ │ (port 8920)     │ │ Server          │
│ (port 8940)     │ │ 4 free models   │ │ (port 8931)     │
│                 │ │ rotation        │ │ SecretBroker    │
│ - expand prompt │ │                 │ │                 │
│ - privacy gate  │ │ - Nemotron 3    │ │ - Secrets in    │
│ - route to      │ │ - Nemotron 3    │ │   ~/.hermes/    │
│   Hermes -z     │ │   Super         │ │   secrets.enc   │
│ - 429 auto      │ │ - Nemotron Nano │ │ - Audit log     │
│   retry         │ │ - DeepSeek R1   │ │ - Fail-closed   │
│ - 6pm deferral  │ │                 │ │   proxy         │
│ - KB reinforce  │ │                 │ │                 │
└────────┬────────┘ └─────────────────┘ └─────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│              HERMES AGENT (hermes -z)                           │
│  One-shot execution with full skill/tool access                 │
│  Runs expanded prompt with enterprise modules loaded            │
└─────────────────────────────────────────────────────────────────┘
```

## Prerequisites

- NVIDIA RTX 3060 Ti (8GB VRAM) or similar
- CUDA 13.2, Python 3.14, PyTorch with CUDA
- HuggingFace cache with `mistralai/Mistral-7B-Instruct-v0.2` (safetensors required for 4-bit)
- ENI Hermes Controller installed at `~/.hermes/controller/eni_controller/`
- Local security server at `~/.hermes/security/local_security_server.py`

## One-Command Deploy (after initial setup)

```bash
#!/usr/bin/env bash
# deploy-local-stack.sh — run this to bring up the full local stack

set -euo pipefail

echo "=== Killing old processes ==="
pkill -f "airllm_server.py" 2>/dev/null || true
pkill -f "free_router.py" 2>/dev/null || true
sleep 2

echo "=== Starting Free Router (port 8920) ==="
cd ~/.hermes/scripts
python3 free_router.py --port 8920 &
FREE_ROUTER_PID=$!
sleep 3

echo "=== Starting Local Security Server (port 8931) ==="
cd ~/.hermes/security
python3 local_security_server.py --port 8931 &
SECURITY_PID=$!
sleep 2

echo "=== Starting ENI Hermes Controller (port 8940) ==="
systemctl --user start eni-controller.service
sleep 3

echo "=== Starting Local LLM Server with Tool Calling (port 8913) ==="
cd /home/hunter/Dev/workers
python3 airllm_server.py --port 8913 --model mistralai/Mistral-7B-Instruct-v0.2 &
LLM_PID=$!

echo "=== Waiting for model load (~50s first time) ==="
for i in {1..60}; do
    if curl -sf http://127.0.0.1:8913/health | grep -q '"status":"ok"'; then
        echo "Local LLM server ready!"
        break
    fi
    sleep 1
done

echo "=== Verifying tool calling ==="
curl -s http://127.0.0.1:8913/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"airllm","messages":[{"role":"user","content":"check controller status"}],"max_tokens":200}' | jq -r '.choices[0].message.content'

echo "=== All services up ==="
echo "Local LLM (orchestrator):  http://127.0.0.1:8913"
echo "Free Router:               http://127.0.0.1:8920"
echo "Security Server:           http://127.0.0.1:8931"
echo "ENI Controller:            http://127.0.0.1:8940"
```

## Hermes Config (run once)

```bash
# Point Hermes to local model as DEFAULT with NO cloud fallback
hermes config set model.default mistralai/Mistral-7B-Instruct-v0.2
hermes config set model.provider airllm
hermes config set model.fallback_chain '[]'

# Auxiliary models to local (avoids OpenRouter 429)
hermes config set auxiliary.title_generation.provider airllm
hermes config set auxiliary.title_generation.model mistralai/Mistral-7B-Instruct-v0.2
hermes config set auxiliary.compression.provider airllm
hermes config set auxiliary.compression.model mistralai/Mistral-7B-Instruct-v0.2

# Disable model catalog hijack
hermes config set model_catalog.enabled false

# FULLY RESTART HERMES (exit completely, relaunch)
# Then in TUI: /model airllm  (should already be default)
```

## Usage Examples

### 1. Direct API (scripting)
```bash
curl -s http://127.0.0.1:8913/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "airllm",
    "messages": [{"role": "user", "content": "build the full enterprise platform with all modules"}],
    "max_tokens": 4000,
    "temperature": 0.3
  }' | jq -r '.choices[0].message.content'
```

### 2. Hermes TUI (interactive)
```bash
hermes
# Type: build the enterprise platform
# Local model expands via controller → pushes to hermes -z → streams back
```

### 3. Check controller status
```bash
curl -s http://127.0.0.1:8913/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"airllm","messages":[{"role":"user","content":"controller status"}],"max_tokens":500}'
```

### 4. Queue work for 6pm
```bash
curl -s http://127.0.0.1:8913/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"airllm","messages":[{"role":"user","content":"queue this massive build for 6pm"}],"max_tokens":200}'
```

## Key Config Values (in airllm_server.py)

```python
# Model loading — works on 8GB VRAM
quant_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",
    llm_int8_enable_fp32_cpu_offload=True,  # CRITICAL
)

_model = AutoModelForCausalLM.from_pretrained(
    model_id,
    quantization_config=quant_config,
    device_map="auto",
    max_memory={0: "6GiB", "cpu": "16GiB"},  # CRITICAL
    trust_remote_code=False,
    attn_implementation="sdpa",
)

# Tool calling system prompt
system_prompt = (
    "You are ENI, LO's local orchestrator brain... "
    "When LO gives you an instruction, you MUST respond with a JSON object..."
    "Available tools: controller_expand, controller_chat, controller_status, "
    "free_router_chat, secret_get, secret_set, model_mine, queue_job, respond"
    "IMPORTANT: Always include \"arguments\": {} even if empty. Output ONLY the JSON."
)
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `CUDA out of memory` on load | Ensure `max_memory={0: "6GiB", "cpu": "16GiB"}` + `llm_int8_enable_fp32_cpu_offload=True` |
| Model doesn't call tools | Check system prompt includes tool list + format; increase `max_tokens` to 2000+ |
| Tool result not fed back | Verify `<|tool_result|>` format in prompt append |
| Hermes shows 256K context | `hermes config set model_catalog.enabled false` + full restart |
| Auxiliary 429 errors | Point aux models to local: `hermes config set auxiliary.*.provider airllm` |
| Secrets not working | Security server must be running on 8931; broker attached in controller status |

## Files in This Stack

| File | Purpose |
|------|---------|
| `/home/hunter/Dev/workers/airllm_server.py` | Local LLM server with tool calling (port 8913) |
| `~/.hermes/scripts/free_router.py` | Free model router (port 8920) |
| `~/.hermes/security/local_security_server.py` | SecretBroker (port 8931) |
| `~/.hermes/controller/eni_controller/` | ENI Hermes Controller package (port 8940) |
| `~/.config/systemd/user/eni-controller.service` | Systemd service for controller |
| `~/.config/systemd/user/free-router.service` | Systemd service for free router |

## Verification Checklist

- [ ] `curl localhost:8913/health` → `{"status":"ok","tools":8}`
- [ ] Tool calling: "check controller status" → real controller JSON returned
- [ ] `nvidia-smi` → ~4.1 GB VRAM, GPU util >0% during inference
- [ ] Server logs → "ALL GPU"
- [ ] Hermes TUI → "Mistral-7B-Instruct-v0.2 · Nous Research" + ctx ~8K
- [ ] Auxiliary ops (title/compression) work without 429
- [ ] `model.fallback_chain = []` — pure local