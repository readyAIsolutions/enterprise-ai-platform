# Resuming / diagnosing an interrupted QLoRA run

Symptom: user reports "we lost wifi while training" and asks whether the fine-tune
finished. Often the wifi drop coincided with a machine reboot that killed the run
silently — nothing auto-restarts it.

## Diagnose BEFORE assuming anything

Check in order (all cheap, no token burn):

1. Is a train process alive? `ps aux | grep -E 'python|qlora' | grep -v grep`.
   Look for `train_qlora.py` / a `SFTTrainer` run. If absent, the run is dead.
2. GPU: `nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv`.
   A live fine-tune shows high util; idle (0%) confirms nothing is training.
3. Uptime vs last checkpoint mtime:
   `uptime` + `last reboot` (if `last` is missing, rely on uptime / `who -b`).
   If checkpoint mtime is older than the boot time, the run never resumed.
4. Checkpoint dirs: `ls -la <out_dir>/` — every save_steps interval leaves
   `checkpoint-<N>/` with a full PEFT adapter + `optimizer.pt` + `trainer_state.json`.
5. The authoritative answer lives in `checkpoint-<last>/trainer_state.json`:
   - `global_step` vs `max_steps` → `global_step/max_steps` is the real percent done.
   - `epoch`, `loss`, `mean_token_accuracy` (log_history[-1]) → is it actually learning.
   - A merged standalone model exists only if a separate merged dir was written by
     `merge_and_unload()`; its absence means only the raw PEFT adapter survived.

Concrete observed case (eni-controller, Mistral-7B, Aug 7): global_step 24000 /
max_steps 29772 (~81%), loss 0.575, token-acc 87.5%, box booted 55 min after the last
checkpoint → reboot killed it at 81%. Fully resumable.

## Resuming — the crash you MUST avoid

`train_qlora.py` as written has `save_strategy="no"`, no `--resume` flag, and passing
`num_train_epochs=None` alongside a `max_steps` will CRASH on the SFTConfig/trainer
init with:
```
TypeError: '>' not supported between instances of 'NoneType' and 'int'
```
This bit twice in one session. Root cause: transformers `_validate_args` evaluates
`if args.max_steps > 0 and args.num_train_epochs > 0` — if you null out epochs while
setting max_steps, the `None > 0` comparison throws.

**Correct resume config (proven working):** keep `num_train_epochs` as a real number
(epochs, e.g. 3) AND set `max_steps`; transformers uses max_steps when both are set
and logs a notice, no crash:
```python
# on resume, read the saved target:
saved_max = json.loads((ckpt/"trainer_state.json").read_text()).get("max_steps")
args.steps = int(saved_max) if saved_max else args.steps   # target, e.g. 29772
...
max_steps = args.steps if args.steps > 0 else -1
epochs    = args.epochs       # ALWAYS a number, never None, even when steps>0
cfg = SFTConfig(..., max_steps=max_steps, num_train_epochs=epochs,
                save_strategy="steps", save_steps=2000)
trainer = SFTTrainer(..., train_dataset=text_ds)
trainer.train(resume_from_checkpoint=str(ckpt) if ckpt else None)
```
Note the ORIGINAL live run used `save_strategy="steps"` (checkpoints every 2000),
which is why `checkpoint-N/` dirs existed — the skill's `save_strategy="no"` copy
differs from how it actually ran. On resume write checkpoints too.

A ready resume-capable script exists (adapted this session, tested fast enough to hit
24.0k→24.3k then continue to completion):
`~/.hermes/controller/training/train_qlora_resume.py` — accepts `--resume`,
auto-finds latest `checkpoint-*`, reads `max_steps` from trainer_state, resumes the
optimizer/scheduler at full LR position, checkpoints each `--ckpt_every`, merges to
`--out/merged` at the end, and touches a `.DONE` marker.

## Prevent the silent-death recurrence (proven: systemd + linger)

`nohup`/tmux can't resurrect after a reboot. Use a systemd USER unit that comes back
on boot (the wifi-drop lesson was really a REBOOT killed the process):
```
# ~/.config/systemd/user/eni-train.service
[Service]
Type=simple
ExecStart=/home/hunter/.hermes/controller/training/eni_train_watchdog.sh
Restart=on-failure
RestartSec=15
Environment=HF_HOME=/home/hunter/.cache/huggingface
[Install]
WantedBy=default.target
```
```bash
systemctl --user daemon-reload
systemctl --user enable eni-train.service
loginctl enable-linger hunter          # <-- survives reboot
systemctl --user start eni-train.service
```
`enable-linger` is the critical piece — without it the unit dies with the logged-in
session and won't restart training after a reboot. The wrapper script checks for a
`.DONE` marker and `exit 0`s (no restart loop) when training already finished, and
re-launches `train_qlora_resume.py --resume` otherwise. Since base model + dataset are
local, resume needs ZERO network — wifi being down is irrelevant.
Verify it's really progressing: `tail` the log, watch `step/29772` climb, and check
GPU util is high (not idle, which means it crashed again).
- Aim for a watchdog (see `auto-serve-watchdog.md`) that pings the checkpoint mtime
  and alerts if training goes quiet.
- Wifi loss alone shouldn't kill local GPU training (no upload needed), but a kernel /
  power event / reboot will. Treat "wifi dropped mid-train" as a hint to check for a
  reboot + dead process, not as the direct cause.

## Auto-RESTART watchdog (not just monitor)

Diagnosis + an alert are not enough — a long QLoRA run must come back by itself
after a reboot. Build a systemd user service (`Restart=on-failure` +
`loginctl enable-linger`) that relaunches a resume-aware trainer at boot and
picks up the newest checkpoint. Complete copy-me recipe + the resume-aware
trainer essentials: `templates/resume-autowatchdog-systemd.md`.

## Pitfall

- Don't reassure "almost done at 81%, fine" or rebuild from scratch — the checkpoint
  is a complete, valid resume point. Either resume (preferred) or merge what exists.
  Check trainer_state FIRST so you quote real numbers, not vibes.
- When making the trainer resume-aware, do NOT set `num_train_epochs=None` just
  because `max_steps > 0`. `transformers.Trainer._validate_args()` runs
  `if args.max_steps > 0 and args.num_train_epochs > 0:`; a `None > 0` throws
  `TypeError: '>' not supported between instances of 'NoneType' and 'int'`
  AFTER the model already loaded (looks like a flash-crash / fake hang: GPU fills,
  then the process dies). Always pass `num_train_epochs=args.epochs` (a real float) —
  with `max_steps>0` transformers overrides epochs anyway ("max_steps is given, it
  will override ... num_train_epochs"). Also keep the trainer's `save_strategy="steps"`
  (not "no") or there is nothing to resume from.