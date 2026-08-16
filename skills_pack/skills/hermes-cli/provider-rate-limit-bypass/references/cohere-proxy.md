# Cohere SSE Streaming Proxy

Cohere's native API is NOT OpenAI-compatible. Build a local proxy.

## Working implementation: /tmp/cohere_final.py on LO's machine (port 8914)

Key: cohere_gBRDlQK6PnVcYonoOoTSfOQBXyEPDxdBccnA46ie3B1E2D

### Critical: Hermes streams by default
The proxy MUST return SSE format. Plain JSON is rejected as "(empty)".

### SSE chunk format:
```
data: {"choices":[{"delta":{"content":"text"}}],"object":"chat.completion.chunk",...}\n\n
data: [DONE]\n\n
```

### Provider config in hermes:
```yaml
cohere-local:
  base_url: http://127.0.0.1:8914/v1
  api_key: local
  discover_models: false
  default_model: command-r-plus-08-2024
  context_length: 128000
```

### Systemd: ~/.config/systemd/user/demiurge-cohere.service
Auto-starts on boot via demiurge.target