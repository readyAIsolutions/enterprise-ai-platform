#!/usr/bin/env python3
"""QLoRA fine-tune a chat model into a custom local model (RTX 3060 Ti 8GB).
Modern-stack-correct (transformers 5.x / trl 1.9 / torch 2.13):
  SFTConfig (not TrainingArguments), processing_class=tokenizer,
  max_length (not max_seq_length), loss_type='nll', lm_head NOT in LoRA targets,
  bf16=True on Ampere. Merges back to a standalone model.

Run in a dedicated venv (PEP-668): ~/.venvs/eni-train/bin/python train_qlora.py
"""
from __future__ import annotations
import argparse
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="mistralai/Mistral-7B-Instruct-v0.2")
    ap.add_argument("--data", required=True,
                    default="/home/hunter/.hermes/controller/training/eni_controller_train.jsonl")
    ap.add_argument("--out", required=True,
                    default="/home/hunter/.hermes/controller/models/eni-controller")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--steps", type=int, default=0, help="override steps (0=epochs)")
    args = ap.parse_args()

    import torch
    from datasets import load_dataset
    from transformers import (
        AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig,
    )
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from trl import SFTTrainer, SFTConfig

    assert Path(args.data).exists(), f"missing dataset {args.data}"

    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
        llm_int8_enable_fp32_cpu_offload=True,
    )
    torch.cuda.empty_cache()
    model = AutoModelForCausalLM.from_pretrained(
        args.base, quantization_config=bnb, device_map="auto",
        max_memory={0: "6GiB", "cpu": "16GiB"}, trust_remote_code=False,
    )
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(model)
    tokenizer = AutoTokenizer.from_pretrained(args.base)
    tokenizer.pad_token = tokenizer.eos_token

    # No lm_head here — including it clashes with trl loss_type (chunked_nll).
    lora = LoraConfig(
        r=args.rank, lora_alpha=args.rank * 2, lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        bias="none", task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    ds = load_dataset("json", data_files=args.data, split="train")
    text_ds = ds.map(lambda x: {
        "text": tokenizer.apply_chat_template(x["messages"], tokenize=False,
                                              add_generation_prompt=False)
    })

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    max_steps = args.steps or -1
    epochs = None if args.steps > 0 else args.epochs

    cfg = SFTConfig(
        output_dir=str(out_dir),
        num_train_epochs=epochs,
        max_steps=max_steps,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        gradient_checkpointing=True,
        learning_rate=args.lr,
        warmup_ratio=0.03,
        logging_steps=5,
        save_strategy="no",
        report_to=[],
        fp16=False,          # Ampere: bf16 matches bnb 4-bit compute dtype
        bf16=True,
        max_grad_norm=0.3,
        optim="paged_adamw_8bit",
        lr_scheduler_type="cosine",
        max_length=2048,     # max_seq_length was renamed to max_length
        dataset_text_field="text",
        packing=False,
        loss_type="nll",     # avoid chunked_nll + lm_head clash
    )

    trainer = SFTTrainer(
        model=model,
        args=cfg,
        processing_class=tokenizer,   # 'tokenizer=' kwarg was removed
        train_dataset=text_ds,
    )
    trainer.train()
    trainer.save_model(str(out_dir / "adapter"))
    tokenizer.save_pretrained(str(out_dir / "adapter"))

    merged = out_dir / "merged"
    merged.mkdir(parents=True, exist_ok=True)
    try:
        m = model.merge_and_unload()
        m.save_pretrained(str(merged))
        tokenizer.save_pretrained(str(merged))
        print(f"MERGED model -> {merged}")
    except Exception as e:  # noqa: BLE001
        print(f"merge skipped ({e}); adapter saved at {out_dir/'adapter'}")
    print("TRAIN DONE")

if __name__ == "__main__":
    main()
