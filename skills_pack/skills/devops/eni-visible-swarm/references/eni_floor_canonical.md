# ENI Build Floor — Canonical Layout & 429-Stampede Fix (2026-07-11 session)

## Canonical floor (user re-confirmed — overrides the earlier 2026-07-11 FLOOR LAYOUT SPEC note)
- **4 terms per screen (2×2 grid) on EACH of the 4 X11 workspaces** (6400×2160 canvas, WS idx 0–3).
  Not just 3 side screens with 4 each — all four workspaces carry builders.
- **Builders = single-tab** xfce4-terminal windows, title `ENIx::build`.
  Do NOT open a master-chat tab inside each builder — that spawned 64 redundant
  `hermes chat` sessions → 429/OOM stampede (real bug this session).
- **Heartbeat = one small window per workspace**, title `WSx::heart`, pinned to the
  middle monitor top strip, sitting OVER the 4-terms grid.
- **Master coordinator = ONE window**, title `WS1::master`, on WS1 only, middle monitor
  top strip. (Not a master tab in every builder.)
- **One program per workspace:**
  - WS1 = STOCK / demiurge_scaffold (ENI1–16)
  - WS2 = demiurge-3d (ENI17–32)
  - WS3 = demiurge / forex (ENI33–48)
  - WS4 = lumen (LEASHED — code-only, ENI49–64)

## Verified geometry (absolute coords in the 6400×2160 virtual canvas)
- left  : (30,98) (961,98) (30,612) (961,612)
- right : (4510,98) (5441,98) (4510,612) (5441,612)
- bottom: (2304,1178) (3235,1178) (2304,1692) (3235,1692)
- mid   : (1920,245) (3200,245) (1920,655) (3200,655)   size 1244×400
- heartbeat/master overlays: `72x6+<mid_ox>+8` and `72x6+<mid_ox+960>+8`
  (mid_ox = 1920 on LO's box). Both on the top strip (y=8), over the grid.

## Staggered-boot run-script template (fixes OpenRouter 429 stampede)
```bash
#!/usr/bin/env bash
export PATH="$HOME/.local/bin:$HOME/bin:$PATH"
cd /home/hunter
LOG="/tmp/eni_logs/ENIx.log"
mkdir -p /tmp/eni_logs
# Stagger initial boot: spread 64 forks over ~50s so OpenRouter's free tier is
# not stampeded (which exhausts 8 retries with HTTP 429). ONE-TIME, before the loop.
sleep $(( (RANDOM % 50) + 3 ))
while true; do
  M="$(bash /tmp/eni_pick_model.sh)"
  python3 /home/hunter/.local/bin/eni_agent_term.py --name ENIx \
    --task "/home/hunter/.cache/eni_parallel/task_ENIx.txt" \
    --repl "hermes chat --yolo -m $M --provider openrouter" \
    --ctl /tmp/eni_ctl_ENIx > "$LOG" 2>&1
  if grep -qiE '429|rate limit|Bad Request|not a valid model|401|403|Too Many Requests|ConnectionError|timed out' "$LOG" 2>/dev/null; then
    bash /tmp/eni_record_fail.sh "$M"
  fi
  free -m | awk '/Mem:/{f=$7} END{if(f<2500){exit 1}}' || sleep 20
  sleep 3
done
```

## 429 stampede — diagnosis & fix
- **Symptom:** many logs show `Rate limited after 8 retries — HTTP 429: Provider returned error`.
- **Cause:** 64 simultaneous `hermes chat` forks overwhelm OpenRouter's free-tier rate
  limit. The live model picker rotates models, but a 429 is **account-wide**, so rotation
  alone does NOT fix a simultaneous fork.
- **Transient vs stuck:** count 429-log mtimes.
  ```bash
  now=$(date +%s); recent=0; old=0
  for f in /tmp/eni_logs/ENI*.log; do
    grep -qiE '429|rate limit' "$f" || continue
    [ $((now-$(stat -c %Y "$f"))) -lt 60 ] && recent=$((recent+1)) || old=$((old+1))
  done
  echo "recent=$recent old=$old"
  ```
  If `recent=0` (all 429s older than ~60s) the self-heal loop already recovered them —
  **do NOT kill minis**. A stuck floor shows `recent` climbing.
- **Durable fix:** staggered boot (template above) + picker (`eni_pick_model.sh`) +
  hermes config `fallback_providers: [gemini]` + `api_max_retries: 8`.

## Lumen leash — correct check (AMD RX5700XT box; Lumen app has rebooted the PC before)
- **ALLOWED (headless, no display):** `python -m lumen.config --schema`,
  `python -m lumen.doctor --json`, pytest/flake8/mypy/importlint.
- **FORBIDDEN (wedges GPU/X):** `python -m lumen` (the GUI app entry).
- **Correct leash probe** (flags ONLY the app, not config/doctor CLIs):
  `pgrep -af 'python -m lumen[^-.]'`
  (`lumen.config` / `lumen.doctor` have a dot after `lumen` → NOT matched).
- **NEVER kill a `lumen.config` / `lumen.doctor` CLI** — those are safe and expected.

## Proxy / hermes process-counting nuance
- `pgrep -fc 'hermes chat --yolo'` **double-counts**: the proxy cmdline itself contains
  `--repl "hermes chat --yolo -m ... --provider openrouter"`, so it counts the ~69
  proxies AND their ~69 hermes children (~138+).
- **Orphan check** (ppid==1 = reparented to init after a proxy kill):
  ```bash
  for pid in $(pgrep -f 'hermes chat --yolo'); do
    [ "$(ps -o ppid= -p "$pid" | tr -d ' ')" = "1" ] && echo "orphan $pid"
  done
  ```
  Healthy floor = 0 orphans. Never blanket-kill `hermes chat --yolo` (kills live builders).

## Editing the Python generator (`paint_4ws_programs.py`)
- Run-scripts are built by concatenating Python **string literals** passed to `write()`.
- Pasting unquoted bash into the template → `SyntaxError: invalid syntax` and the whole
  painter dies. Wrap added bash as quoted strings with `\n`:
  `"sleep $(( (RANDOM % 50) + 3 ))\n"`.
- Verify before regenerating: `python3 -m py_compile paint_4ws_programs.py`
  (NOT just `bash -n` on the generated output).

## Painter does NOT regenerate run-scripts
- `/tmp/eni_tabs/run_*.sh` must exist BEFORE any paint, or the floor comes up EMPTY.
  Always run the generator (`python3 paint_4ws_programs.py`) to (re)create the 64
  run-scripts + `/tmp/paint_4ws_full.sh`, THEN paint.
