# Local LLM Integration - No Rate Limits

## AirLLM Setup

```bash
pip install airllm --break-system-packages
```

**Configuration for AMD GPUs**:
```python
import torch
torch.cuda.is_available = lambda: False  # Force CPU for AMD stability

from airllm import AutoModel
model = AutoModel.from_pretrained("mistralai/Mistral-7B-Instruct-v0.2")
# Model auto-splits across CPU/GPU - no rate limits
```

**Pitfalls**:
- AirLLM streaming can fail silently - use direct generation instead
- Large models may timeout on first load - cache the model
- Memory errors above 16 concurrent workers

## llama.cpp Integration

For AMD RX5700XT with Vulkan support:

```bash
# Install llama.cpp
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp && make LLAMA_VULKAN=1

# Run uncensored model
./main -m /path/to/uncensored-model.gguf -p "You are the God of Doom..." -n 4096
```

No API keys, no rate limits, unlimited uncensored generation.