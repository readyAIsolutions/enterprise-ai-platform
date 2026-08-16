# Verified Benchmarks: RTX 3060 Ti (8GB) + Mistral-7B-Instruct-v0.2

Session date: 2026-07-23. All numbers empirically measured via `time curl`.

## Hardware
- GPU: NVIDIA RTX 3060 Ti, 8192 MiB total, ~7.66 GiB usable
- Driver: 595.71.05, CUDA 13.2
- PyTorch: 2.13.0+cu130
- transformers: 5.12.1
- bitsandbytes: installed (for 4-bit)
- Flash attention: NOT available (no CUDA toolkit, no `nvcc`)

## Speed Progression

| Configuration | Tok/s | Time for 10 tok | VRAM | Notes |
|--------------|-------|-----------------|------|-------|
| AirLLM (disk offloading, 4bit compression) | 0.09 | 112s | ~1.3 GB | GPU idle, layers read from ~/.airllm_cache per forward pass |
| fp16, device_map="auto" (GPU/CPU split) | 0.75 | 14s | ~6.5 GB | ~60% layers on GPU, rest on CPU |
| 4-bit NF4, device_map="auto" (full GPU) | 23 | 3.5s (80 tok) | 4.1 GB | **ALL** layers on GPU verified by parameter device check |

## 4-bit NF4 Config That Works

```python
from transformers import BitsAndBytesConfig

quant_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",
)

model = AutoModelForCausalLM.from_pretrained(
    model_id,
    quantization_config=quant_config,
    device_map="auto",
    attn_implementation="sdpa",
)
```

Result: 4.1 GB VRAM, ALL layers on GPU, 23 tok/s sustained, clean output.

## Max GPU Budget

Setting `max_memory={0: "7.5GiB"}` crashes with OOM during warmup allocation. The 8GB card
has ~7.66 GiB usable; PyTorch's warmup tries to allocate ~6.5 GiB in one shot and fails.
Recommendation: let `device_map="auto"` decide -- it consistently makes optimal choices.

## Download Time

Safetensors for Mistral-7B (3x4.7GB shards): ~10-12 minutes with 4 parallel HTTPS connections
via `hf_hub_download`. `snapshot_download` was observed to stall with 23 duplicate incomplete
blob files at 0% CPU for 11+ minutes without completing -- use per-file download instead.