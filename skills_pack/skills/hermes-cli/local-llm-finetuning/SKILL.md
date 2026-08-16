---
name: local-llm-finetuning
description: >-
  Fine-tune a chat/agent model into a custom local model on a consumer GPU
  (RTX 3060 Ti 8GB here) using QLoRA/4-bit + LoRA, then merge and serve it.
  Covers the modern-stack pitfalls that bite trl/transformers (SFTConfig vs
  TrainingArguments, processing_class vs tokenizer, loss_type chunked_nll vs
  nll, bf16 vs fp16, exclude lm_head from LoRA targets), the PEP-668 venv
  requirement for pip installs, merged-model export, and wiring the result into
  a serving brain (airllm) plus the honest limits of a small LoRA (reliable at
  tool-format/intent, flaky at faithfully restating tool RESULTS). Use whenever
  the user says "train our own model", "fine-tune", "QLoRA", "train a LoRA on
  this box", or wants to specialize an existing local model for a controller /
  persona / tool-calling task.
---

# Local LLM Fine-tuning (QLoRA on consumer GPU)

Turn a base chat model into a bespoke one on the local box. Proven on an RTX
3060 Ti (8GB VRAM, 24-thread Ryzen 3900X, 30GB RAM). Method: 4-bit QLoRA +
LoRA adapters -> SFT -> merge back to a standalone model.

## When to use
- "Train our own model", "fine-tune it", "train a LoRA on this box".
- Specializing a base model for a persona, tool-calling schema, or controller
  behavior (e.g. the ENI Hermes Controller brain).

## Fastest correct stack (as of Aug 2026, transformers 5.x / trl 1.9 / torch 2.13)
Create a dedicated venv (system python is PEP-668-externally-managed — `pip
install` fails without --break-system-packages, which you must NOT do on the
system python):
```bash
python3 -m venv ~/.venvs/eni-train
~/.venvs/eni-train/bin/pip install -q --upgrade pip
~/.venvs/eni-train/bin/pip install -q torch transformers accelerate peft trl datasets bitsandbytes
```
Verify CUDA + versions in the venv, not system python:
```bash
~/.venvs/eni-train/bin/python -c "import torch;print(torch.__version__,torch.cuda.is_available());import peft,trl,transformers,datasets,bitsandbytes;print(peft.__version__,trl.__version__,transformers.__version__,datasets.__version__,bitsandbytes.__version__)"
```

## Data
OpenAI-format `{"messages":[{role,content},...]}` JSONL. Generate programmatic
VARIETY (dozens-hundreds of records), not a few hand-written examples — a
"general" model needs breadth. For agent/tool models, include:
- exact tool-calling JSON for every tool (intent -> `{"tool":..,"arguments":..}`)
- persona/system behavior
- security/privacy refusals (never echo real secrets)
- general assistant turns
Split a small eval file too.

## The modern-stack pitfalls (each cost a failed run)
1. **SFTConfig, not TrainingArguments.** Newer trl moved SFT params into
   `trl.SFTConfig`. Pass `args=SFTConfig(...)`, and put `max_length`,
   `dataset_text_field`, `packing`, `loss_type` in the config.
2. **`processing_class=tokenizer`, not `tokenizer=`** on `SFTTrainer`. Newer trl
   removed the `tokenizer` kwarg — passing it raises
   `TypeError: SFTTrainer.__init__() got an unexpected keyword argument 'tokenizer'`.
3. **`max_length`, not `max_seq_length`.** `SFTConfig` renamed it; passing the
   old name errors with a "Did you mean 'max_length'?" hint.
4. **Do NOT include `lm_head` in LoRA `target_modules`.** With trl's default
   `loss_type='chunked_nll'` (or when the head is wrapped by a PEFT adapter) it
   raises: "loss_type='chunked_nll' is not supported when lm_head is wrapped by
   a PEFT adapter." Either drop `lm_head` from targets AND set
   `loss_type="nll"` in SFTConfig.
5. **bf16 training on Ampere.** bnb 4-bit compute dtype is bfloat16; if you set
   `fp16=True` you crash with
   `NotImplementedError: "_amp_foreach_non_finite_check_and_unscale_cuda" not implemented for 'BFloat16'`.
   On an RTX 3060 Ti (Ampere) set `bf16=True, fp16=False` to match the
   quantized compute dtype.
6. **gradient_checkpointing=True + paged_adamw_8bit + gradient_accumulation** is
   the 8GB fit combo. per_device_train_batch_size=1, grad_accum=4.

## Merge + export
```python
model = model.merge_and_unload()
model.save_pretrained(out/"merged")
tokenizer.save_pretrained(out/"merged")
```
Save the adapter too (`trainer.save_model(out/"adapter")`). The merged dir is a
standalone model (config.json + model.safetensors + tokenizer) you can point a
serving brain at.

## Wire into a serving brain
Add the merged model path as a resolvable alias so the server can load it by a
short name (e.g. `"eni"` -> `/path/to/merged`). Update the serving unit's
`--model` to the merged path and its caller's default model name to the alias.

## HONEST LIMITS (read before promising)
A 7B QLoRA (small dataset, ~100 records, ~22k tokens) learns the FORMAT and the
persona and intent-mapping extremely well (final token-acc ~0.99, loss ~0.3),
but is FLAKY at the second step of agentic work: faithfully consuming a tool
RESULT and restating real numbers. In tests it sometimes invented plausible-but
-fake output ("Latency 5.2ms", "Enterprise modules: installed") instead of the
real data, or echoed a template. Expect it to be reliable at:
- emitting the correct tool-calling JSON for the right intent ✅
- keeping the persona / refusing to leak secrets ✅
and unreliable at:
- reading a returned JSON result and re-reporting it verbatim ⚠️

Mitigations: (a) far richer "tool result -> summary" training pairs (the single
biggest lever), (b) a base model with stronger native tool-calling (e.g. Qwen
over Mistral-7B), or (c) keep the agent's tool EXECUTION server-side &
deterministic (fail-closed, hard-coded) and treat the model as the intent layer
only — never let the model be the sole authority over side effects or secrets.

## Verification
- Final train_loss + mean_token_accuracy from the trainer log.
- Merged dir has config.json + model.safetensors + tokenizer files.
- Serving /health reports the merged model path.
- End-to-end: ask for a tool call and confirm (a) it emits valid JSON, AND
  (b) if tool execution is server-side, that the REAL result (not a
  hallucinated one) comes back — verify against the real endpoint, not the
  model's summary.

## Support files
- `scripts/train_qlora.py` — the working QLoRA + merge trainer (SFTConfig,
  processing_class, loss_type=nll, bf16, lm_head excluded).
- `scripts/build_agent_dataset.py` — programmatic agent/tool-calling dataset
  generator (persona + exact tool JSON + security refusals + general).
- `references/auto-serve-watchdog.md` — systemd oneshot-timer pattern that
  auto-serves a freshly-trained model the moment its merge finishes (poll for
  the merged artifact or a `TRAIN DONE` marker, restart the serving unit, verify
  against the real endpoint). Use for any long (multi-hour) training you want
  served without babysitting.

## Honest limits (a small LoRA is an intent layer, not an oracle)
See `references/corpus-and-qualitative.md` for the 5M-token assembly recipe and
the real ETA math; for a run killed mid-train (wifi drop / reboot) see
`references/resume-interrupted-run.md` (read trainer_state.json global_step vs
max_steps, resume via `--resume_from_checkpoint`, watchdog against silent death);
to make that recovery AUTOMATIC across reboots, use the ready-made systemd
auto-restart watchdog `templates/resume-autowatchdog-systemd.md`
(`Restart=on-failure` + `enable-linger` — a nohup/tmux run dies with the session,
a systemd user service does not). Note the resume pitfall: keep
`num_train_epochs` a real float even when `max_steps>0` — `Trainer._validate_args()`
raises `TypeError: NoneType` otherwise, AFTER the model loads.
see `eni-hermes-controller` →
`references/tool-call-parser-and-real-result-verification.md` for why a model
that "calls tools" still must be verified against the REAL endpoint (small
fine-tunes are flaky at faithfully restating tool RESULTS). Keep side-effecting
tool execution server-side and deterministic (fail-closed); never let the model
be the sole authority over side effects.
