#!/usr/bin/env python3
"""Fast LLM OpenAI-compatible server — GPU-accelerated via transformers.

Drop-in replacement for AirLLM or any slow local inference backend.
Preloads model at startup, uses native chat templates, and exposes
standard /v1/chat/completions + /v1/models + /health endpoints.

Usage:
    python server_template.py --port 8913 --model mistralai/Mistral-7B-Instruct-v0.2

Environment:
    HF_HUB_OFFLINE=1          force cached model files (no network)
    PYTHONUNBUFFERED=1        visible startup logs
"""
import argparse
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

DEFAULT_MODEL = os.environ.get("AIRLLM_MODEL", "mistralai/Mistral-7B-Instruct-v0.2")
DEFAULT_PORT = int(os.environ.get("AIRLLM_SERVER_PORT", "8913"))

app = FastAPI(title="Fast LLM Server", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_model = None
_tokenizer = None
_loaded_model_id = None


def _load_model(model_id: str):
    global _model, _tokenizer, _loaded_model_id
    if _loaded_model_id == model_id and _model is not None:
        return

    print(f"[llm-server] Loading {model_id} ...", flush=True)

    # --- CONFIG: choose fp16 or 4-bit ---
    # For 4-bit (fits 7B in ~4.1GB VRAM, 20-30 tok/s on RTX 3060 Ti):
    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
    )
    _model = AutoModelForCausalLM.from_pretrained(
        model_id,
        quantization_config=quant_config,
        device_map="auto",
        trust_remote_code=False,
        attn_implementation="sdpa",
    )

    # For fp16 (fits partially, needs CPU offload for 7B on 8GB):
    # _model = AutoModelForCausalLM.from_pretrained(
    #     model_id,
    #     device_map="auto",
    #     trust_remote_code=False,
    #     attn_implementation="sdpa",
    #     torch_dtype=torch.float16,
    #     use_safetensors=False,         # if only .bin files cached
    #     offload_folder="/path/to/offload",  # required for .bin + device_map
    # )

    _model.eval()

    _tokenizer = AutoTokenizer.from_pretrained(model_id)
    if _tokenizer.pad_token is None:
        _tokenizer.pad_token = _tokenizer.eos_token

    _loaded_model_id = model_id

    gpu_mem = torch.cuda.memory_allocated() / 1e9
    devices = set(str(p.device) for p in _model.parameters())
    on_gpu = all("cuda" in d for d in devices)
    status = "ALL GPU" if on_gpu else f"split across {devices}"
    print(f"[llm-server] Model ready — {gpu_mem:.1f} GB VRAM ({status}).", flush=True)


def _messages_to_chat(messages: list) -> str:
    msgs = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
    try:
        return _tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    except Exception:
        parts = []
        for msg in msgs:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                parts.append(f"<|system|>\n{content}")
            elif role == "user":
                parts.append(f"<|user|>\n{content}")
            elif role == "assistant":
                parts.append(f"<|assistant|>\n{content}")
        parts.append("<|assistant|>")
        return "\n".join(parts)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: Optional[str] = None
    messages: list[ChatMessage]
    max_tokens: Optional[int] = 1024
    temperature: Optional[float] = 0.7
    stream: Optional[bool] = False


class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int = 0
    owned_by: str = "local-gpu"


@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [ModelInfo(id=_loaded_model_id or DEFAULT_MODEL, created=int(time.time()))],
    }


@app.get("/v1/models/{model_id:path}")
def get_model(model_id: str):
    return ModelInfo(id=model_id, created=int(time.time()))


@app.post("/v1/chat/completions")
def chat_completions(req: ChatRequest):
    model_id = req.model or DEFAULT_MODEL
    if _model is None or _loaded_model_id != model_id:
        try:
            _load_model(model_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Model load failed: {e}")

    prompt = _messages_to_chat([m.model_dump() for m in req.messages])
    max_new_tokens = min(req.max_tokens or 1024, 4096)
    temperature = req.temperature if req.temperature is not None else 0.7

    try:
        inputs = _tokenizer(prompt, return_tensors="pt", truncation=True, max_length=4096)
        inputs = {k: v.to(_model.device) for k, v in inputs.items()}

        with torch.no_grad():
            out_ids = _model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                do_sample=temperature > 0,
                pad_token_id=_tokenizer.pad_token_id,
                eos_token_id=_tokenizer.eos_token_id,
            )

        new_ids = out_ids[0][inputs["input_ids"].shape[-1]:]
        text = _tokenizer.decode(new_ids, skip_special_tokens=True).strip()

        # Safety: cut off hallucinated conversation continuations
        for cut in ["<|user|>", "<|system|>", "<|assistant|>", "<|im_start|>", "<|im_end|>"]:
            idx = text.find(cut)
            if idx != -1:
                text = text[:idx].strip()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}")

    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_id,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": text},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": inputs["input_ids"].shape[-1],
            "completion_tokens": len(new_ids),
            "total_tokens": inputs["input_ids"].shape[-1] + len(new_ids),
        },
    }


@app.get("/health")
def health():
    return {"status": "ok", "model": _loaded_model_id or DEFAULT_MODEL}


def main():
    global DEFAULT_MODEL
    parser = argparse.ArgumentParser(description="Fast LLM OpenAI-compatible server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    DEFAULT_MODEL = args.model
    os.environ["AIRLLM_MODEL"] = args.model

    print(f"[llm-server] Starting on {args.host}:{args.port}", flush=True)
    print(f"[llm-server] Model: {args.model}", flush=True)

    # Preload at startup so first request is fast
    _load_model(args.model)

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()