# QLoRA fine-tune a local controller model on an 8GB card (RTX 3060 Ti)

Recipe proven 2026-08-05 to fine-tune Mistral-7B-Instruct-v0.2 into a
general-purpose ENI controller model, entirely on-box. Base stays in your local
model, LoRA adapters add the ENI persona + tool-calling + security rules; merge
back into a standalone model and point airllm/controller at it.

## Environment (the whole point — it fits in 8GB)

- GPU: RTX 3060 Ti 8GB. Base MST-7B cached at ~/.cache/huggingface/hub (52GB on disk).
- Use a DEDICATED venv — system python is PEP-668 protected (pip refuses;
  `--break-system-packages` risks the system interpreter airllm runs from).
  `python3 -m venv ~/.venvs/eni-train` then
  `pip install torch transformers accelerate peft trl datasets bitsandbytes`.
  Verified: torch 2.13+cu130, peft 0.20, trl 1.9.2, transformers 5.14, bnb 0.50.
- FREE VRAM FIRST: stop any running model server (airllm/Ollama) so the card has
  headroom. `nvidia-smi --query-gpu=memory.used,memory.free` — want ~6GB free.
  Restart that server after training.

## Dataset

Mistral chat format via tokenizer.apply_chat_template. Programmatic variety
beats a handful of hardcoded examples for a "general" model. Cover:
  1. Exact tool-calling JSON — match the airllm_server.py TOOLS schema verbatim
     (controller_expand/chat/status, secret_get/set, model_mine, queue_job,
     free_router_chat, respond). The model must emit `{"thought","tool","arguments"}`.
  2. ENI persona + privacy boundary (never leak a real secret; fail-closed).
  3. General assistant/plan/explain/decide turns that resolve via respond().
Output JSONL `{"messages":[{role,content},...]}` incl. a small eval split.
~90-100 records / ~20-25k tokens was plenty for a controller LoRA on 8GB.

## Training config (working, on-box values)

- 4-bit base: `BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=bfloat16,
  bnb_4bit_use_double_quant=True, bnb_4bit_quant_type="nf4",
  llm_int8_enable_fp32_cpu_offload=True)`; `device_map="auto", max_memory={0:"6GiB","cpu":"16GiB"}`.
  Then `prepare_model_for_kbit_training(model)`.
- LoRA: rank 16, alpha 32, dropout 0.05, `target_modules=[q,k,v,o,gate,up,down]_proj`
  (do NOT include lm_head — see pitfall). `peft_config`/`get_peft_model`.
- Train: SFTConfig batch 1, grad_accum 4, grad checkpointing, lr 2e-4, cosine,
  max_grad_norm 0.3, optim paged_adamw_8bit, 3 epochs → ~72 steps, ~5.7s/it ≈ 7 min.
- Save: SFTTrainer.save_model(adapter), then `model.merge_and_unload()` →
  save_pretrained(merged) + tokenizer for a standalone model airllm can load.

## trl v1.9 API pitfalls (broke every naive call this session)

1. `SFTTrainer.__init__` no longer takes `tokenizer=` — use `processing_class=tokenizer`.
2. `max_seq_length=` / `dataset_text_field=` / `packing=` moved OUT of the trainer
   into `SFTConfig(...)`; the catalog name for seq length is `max_length`, NOT
   `max_seq_length`.
3. Default `loss_type="chunked_nll"` crashes with
   "not supported when lm_head is wrapped by a PEFT adapter". Either drop lm_head
   from target_modules AND set `loss_type="nll"`, or keep lm_head and use nll.
4. fp16 + bf16 mismatch on Ampere: if the bnb compute dtype is bfloat16, train
   with `bf16=True, fp16=False`. fp16 with bf16 grads throws
   `"_amp_foreach_non_finite_check_and_unscale_cuda" not implemented for BFloat16`.
5. `warmup_ratio` is deprecated (removed in v5.2) — use `warmup_steps` if it warns.

## Wiring the trained model

- Point airllm_server.py / the controller at the merged model dir
  (`~/.hermes/controller/models/eni-controller/merged`).
- Set `ENI_AIRLLM_MODEL` / the controller's local-backend model to it so
  `/chat` resolves to the trained brain. Keep SecretsBoundary in front.

## Honest expectation setting (say this to LO, don't over-promise)

On 8GB a QLoRA gives a small-but-real fine-tune: persona, tool-calling
discipline, security rules. It is NOT the raw knowledge of a 400B model. If LO
wants more raw capability, the lever is a bigger base that still fits the card,
or CPU-offload a larger quant.
