# Auto-serve a finished model via a systemd watchdog timer

For a long training run (this session: 5M tokens / ~13h on an 8GB 3060 Ti), a
foreground wait dies on timeout or loses state. Instead: run training with
`notify_on_complete=true`, AND set up a systemd **oneshot timer** that polls for
completion and, the moment the merged model exists, auto-wires it into the
serving brain. LO explicitly asked for this ("set this up so it self-serves when
done") — the pattern is reusable for ANY long compute job that must be served
when it finishes.

## The three pieces

1. Training writes the merged model to a fixed path, e.g.
   `~/.hermes/controller/models/eni-controller/merged/model.safetensors` and
   prints `TRAIN DONE` to its log.

2. A watchdog shell script (run as a `Type=oneshot` systemd unit) that is
   IDEMPOTENT — it does nothing if the model isn't merged yet, and acts once it
   is:

```bash
MERGED="/home/hunter/.hermes/controller/models/eni-controller/merged"
TRAIN_LOG="/tmp/eni_train3.log"
if [ ! -f "$MERGED/model.safetensors" ]; then
  grep -q "TRAIN DONE" "$TRAIN_LOG" 2>/dev/null || { echo "still training; nothing to do"; exit 0; }
fi
# re-point airllm unit at the merged model if needed (sed the ExecStart --model=)
# re-point controller default at the trained-model alias if needed
systemctl --user daemon-reload
systemctl --user restart airllm.service eni-controller.service
# wait (poll /health) for model load, then verify REAL tool results come back
```

3. A `Type=oneshot` service + `OnUnitActiveSec=15min` timer (plus
   `OnBootSec`/`Persistent=true` so it also catches a reboot mid-run). The
   service runs the watchdog; the timer re-arms it every few minutes.

```
# ~/.config/systemd/user/eni-autoserve.service
[Service]
Type=oneshot
ExecStart=/path/to/auto_serve_model.sh

# ~/.config/systemd/user/eni-autoserve.timer
[Timer]
OnBootSec=2min
OnUnitActiveSec=15min
Persistent=true
[Install]
WantedBy=timers.target
```
Then: `systemctl --user daemon-reload && systemctl --user enable --now eni-autoserve.timer`.

## Verification baked into the watchdog

After restarting the serving brain (airllm), confirm:
- `curl :PORT/health` reports `"model": "<merged path>"` (proves it loaded the
  trained model, not the base).
- `curl :CONTROLLER/chat use_hermes=false` returns `backend: airllm`.
- Do the REAL-result check: the model's picked tool's result must carry the REAL
  endpoint values (e.g. actual module count), not the model's invented numbers.
  See `eni-hermes-controller` → `references/tool-call-parser-and-real-result-verification.md`.

## Pitfalls

- The watchdog must key on the MERGED ARTIFACT or a `TRAIN DONE` log marker, not
  on process liveness — a killed training (SIGTERM, exit -15) leaves no merged
  model and must NOT trigger serving. Check the artifact or marker explicitly.
- `restart` (not `start`) the serving unit so it reloads the new weights; a plain
  start when it's already up is a no-op.
- Keep the timer idempotent and fast when "nothing to do" so it's cheap to poll
  every 15 min.
