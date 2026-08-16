# Auto-resume QLoRA watchdog (systemd) — survives reboot / crash / wifi-drop

The monitoring watchdog (`references/auto-serve-watchdog.md`) only ALERTS when
training goes quiet. To actually KEEP a long QLoRA run alive across machine
reboots (the common cause of "we lost wifi / it died on me"), wrap the trainer
in a systemd user service with `Restart=on-failure` + user linger. It restarts
itself at boot and resumes from the latest checkpoint.

## Why this beats a nohup / tmux manual restart

- **Reboot survival**: systemd user service with `WantedBy=default.target` +
  `loginctl enable-linger hunter` starts it automatically at login-boot. A
  nohup'd python dies with the session; this comes back on its own.
- **Crash restart**: `Restart=on-failure` + `RestartSec=15` relaunches within
  seconds after any non-zero exit (kernel hang, OOM, power blip) — and the
  resume-aware trainer (below) picks up from the newest checkpoint.
- **Clean-completion guard**: the wrapper exits 0 when `.DONE` exists, so a
  finished run does NOT loopf-0restart every 15s. `Restart=on-failure` only
  bites on non-zero exit.

## Recipe (copy-me files)

**Systemd user unit** — `~/.config/systemd/user/eni-train.service`:

```ini
[Unit]
Description=ENI Controller QLoRA training (auto-resume watchdog)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=hunter
WorkingDirectory=/home/hunter
ExecStart=/home/hunter/.hermes/controller/training/eni_train_watchdog.sh
Restart=on-failure
RestartSec=15
TimeoutStopSec=30
Environment=HF_HOME=/home/hunter/.cache/huggingface

[Install]
WantedBy=default.target
```

**Wrapper** — `~/.hermes/controller/training/eni_train_watchdog.sh`:

```bash
#!/usr/bin/env bash
# Resumes if a checkpoint exists; exits 0 (no restart) once .DONE is present.
set -u
OUT=/home/hunter/.hermes/controller/models/eni-controller
DATA=/home/hunter/.hermes/controller/training/eni_controller_train.jsonl
VENV=/home/hunter/.venvs/eni-train/bin/python
SCRIPT=/home/hunter/.hermes/controller/training/train_qlora_resume.py
LOG=/home/hunter/.hermes/controller/training/eni_train.log

if [ -f "$OUT/.DONE" ]; then
  echo "[eni-train] already DONE — exiting clean (no restart)."
  exit 0
fi
echo "[eni-train] $(date) starting/resuming training."
exec "$VENV" "$SCRIPT" \
  --base mistralai/Mistral-7B-Instruct-v0.2 \
  --data "$DATA" --out "$OUT" --resume 2>&1 | tee -a "$LOG"
```

**Install / start**:

```bash
chmod +x .../eni_train_watchdog.sh
systemctl --user daemon-reload
systemctl --user enable eni-train.service
loginctl enable-linger hunter      # start at boot even before login
systemctl --user start eni-train.service
systemctl --user status eni-train.service
tail -f ~/.hermes/controller/training/eni_train.log
```

## Resume-aware trainer (critical detail)

The trainer must (a) read the saved `trainer_state.json` and reuse its
`max_steps` so it continues TOWARD the same total, (b) keep `num_train_epochs`
a real float even when `max_steps > 0`.

```python
# find newest checkpoint-* in out_dir
ck = sorted(out_dir.glob("checkpoint-*"),
            key=lambda p: int(p.name.split("-")[1]))[-1]
ts = json.loads((ck / "trainer_state.json").read_text())
args.steps = int(ts["max_steps"])          # continue toward same total
# epochs stays args.epochs (a real number) — see pitfall below
...
trainer.train(resume_from_checkpoint=str(ck))
```

## Pitfall (bit me this session)

- Do NOT set `num_train_epochs=None` just because `max_steps > 0`.
  transformers' `trainer._validate_args()` does `if args.max_steps > 0 and
  args.num_train_epochs > 0:` and a `None > 0` raises
  `TypeError: '>' not supported between instances of 'NoneType' and 'int'`
  — AFTER the model has already loaded, so it wastes a full 4-bit load first
  (looks like a hang: GPU fills, then the process dies). Fix: always pass
  `num_train_epochs=args.epochs` (a real float); when `max_steps>0` transformers
  uses `max_steps` and logs "max_steps is given, it will override ... epochs".
- The skill's canonical `scripts/train_qlora.py` sets `save_strategy="no"`; the
  run that checkpointed every 2000 steps used `save_strategy="steps",
  save_steps=2000`. For resume to have anything to resume FROM, the live trainer
  must checkpoint (steps OR epochs), never `"no"`. Match `save_steps` to the
  cadence you want recoverable.
- `--resume` should auto-resolve the latest checkpoint from `out_dir` rather
  than hardcoding a number, so a re-run after another crash keeps advancing.
- Health-check `/api/v1/check` is reachable but the REAL signal signal-cli
  adapter lives in the separate `gateway` package
  (`site-packages/gateway/platforms/signal.py`), not in `hermes_cli`.

## Verification

After start, confirm: `systemctl --user is-active eni-train.service` (active);
GPU memory rises to ~6.5GiB + util ~70%; the log prints a
`[resume] latest checkpoint checkpoint-XXXXX at step N (target max_steps M)`
line and the step counter passes N.