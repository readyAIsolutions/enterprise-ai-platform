# Live model picker — auto-fix failed API -> working API

User directive (2026-07-11): "automatically fix all failed apis to a working api."

Two layers make the ENI swarm self-healing against model/API failure:

## Layer 1 — config spine (verify, don't re-add)
Already correct on this box in BOTH `~/.hermes/config.yaml` and
`~/.hermes/profiles/eni/config.yaml`:
- `model.provider: openrouter`
- `model.default: tencent/hy3:free`
- `fallback_providers: [gemini]`
- `model.api_max_retries: 8`

This makes a transient 429 self-heal INSIDE a hermes session (retry 8x -> rotate to gemini).
Verify:
```bash
python3 -c "import yaml;d=yaml.safe_load(open('$HOME/.hermes/config.yaml'));print(d['model'],d['fallback_providers'])"
```

## Layer 2 — per-mini live picker (the part that was missing)
Every mini re-selects its model on each (re)launch and demotes any model that errors.

### eni_pick_model.sh (scripts/eni_pick_model.sh)
- Round-robin counter `/tmp/eni_model_ctr` + health file `/tmp/eni_model_health`
  (lines `model=epoch`).
- Candidates = ONLY the 3 known-live free slugs:
  `tencent/hy3:free`, `qwen/qwen3-coder:free`, `meta-llama/llama-3.3-70b-instruct:free`.
  A dead/unknown slug (400/404) is NEVER a candidate.
- A slug failed within the last 120s is excluded. If all 3 are freshly demoted, fall back
  to the full live pool (least-recently-failed) so a full outage still yields a model.

### eni_record_fail.sh (scripts/eni_record_fail.sh)
`eni_record_fail.sh <model>` appends `model=now` to the health file.

### Corrected run-script wrapper (templates/eni_mini_run_picker.sh)
Picks a model each loop, logs proxy output to `/tmp/eni_logs/<NAME>.log`, greps the log for
API-failure keywords (`429|rate limit|Bad Request|not a valid model|401|403|Too Many
Requests|ConnectionError|timed out`) and calls `record_fail` on a hit, and pauses 20s if
free RAM < 2.5 GB.

Concrete generated example (ENI5):
```bash
#!/usr/bin/env bash
export PATH="$HOME/.local/bin:$HOME/bin:$PATH"
cd /home/hunter
LOG="/tmp/eni_logs/ENI5.log"
mkdir -p /tmp/eni_logs
while true; do
  M="$(bash /tmp/eni_pick_model.sh)"
  python3 /home/hunter/.local/bin/eni_agent_term.py --name ENI5 --task "/home/hunter/.cache/eni_parallel/task_ENI5.txt" --repl "hermes chat --yolo -m $M --provider openrouter" --ctl /tmp/eni_ctl_ENI5 > "$LOG" 2>&1
  rc=$?
  if grep -qiE "429|rate limit|Bad Request|not a valid model|401|403|Too Many Requests|ConnectionError|timed out" "$LOG" 2>/dev/null; then
    bash /tmp/eni_record_fail.sh "$M"
  fi
  free -m | awk '/Mem:/{f=$7} END{if(f<2500){exit 1}}' || sleep 20
  sleep 3
done
```

## The 64-mini generator
`/home/hunter/Desktop/Commander/eni_swarm/paint_4ws_programs.py` emits:
- `/tmp/eni_tabs/run_ENI*.sh` (64 builders using the picker wrapper above)
- `/tmp/eni_tabs/master_chat.sh`, `/tmp/eni_tabs/heart_WS*.sh`
- `/tmp/eni_pick_model.sh`, `/tmp/eni_record_fail.sh` (picker helpers)
- `/tmp/paint_4ws_full.sh` — the paint script (4 X11 workspaces, 4 terms/screen,
  16 minis/workspace; WS1=STOCK/demiurge_scaffold, WS2=demiurge-3d, WS3=demiurge/forex,
  WS4=lumen leashed; memory-guarded + model-rotated).

Run: `python3 /home/hunter/Desktop/Commander/eni_swarm/paint_4ws_programs.py` then
`bash /tmp/paint_4ws_full.sh` (detached/background — a user message mid-spawn interrupts a
foreground paint).

## Verification
```bash
# picker rotates across the 3 live slugs:
for i in 1 2 3 4 5 6; do bash /tmp/eni_pick_model.sh; done
# after demoting one, it is dropped for 120s:
bash /tmp/eni_record_fail.sh "qwen/qwen3-coder:free"; bash /tmp/eni_pick_model.sh
# floor up:
pgrep -fc eni_agent_term.py      # expect = mini count (64 + 4 hearts)
xwininfo -root -tree | grep -c ENI
```

## Pitfalls
- **Painter does NOT regenerate run-scripts** (`paint_LO_new.sh` and successors). Always
  (re)generate `/tmp/eni_tabs/` run-scripts BEFORE painting or the floor comes up EMPTY
  (windows open, zero proxies, no build). This burned a full floor this session.
- With the live picker, a model-pool change = edit `LIVE` in `eni_pick_model.sh`; the next
  self-heal restart picks the new slug. Do NOT sed the generated runners or close windows
  (that was the old broken "MODEL CHANGE DOESN'T TAKE" dance).
- The round-robin counter is shared by all minis (concurrent writes are racy but harmless —
  only distribution skew, never a wrong model).
