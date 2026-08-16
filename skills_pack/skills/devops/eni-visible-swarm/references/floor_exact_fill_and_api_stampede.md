# ENI swarm: exact-fill packing + API-stampede hardening

Condensed from the 2026-07-11 session where LO said "terminals are not properly
sized to fill up screens" and "fix all api errors". Use this when (re)building the
visible ENI build floor so the terminals actually FILL each screen and don't
stampede OpenRouter's rate limit on boot.

## 1. Exact-fill packing (make terminals FILL screens)
Problem: `xfce4-terminal --geometry COLSxROWS+X+Y` sizes by characters; rendered
pixels are font-dependent, so a 2x2 grid with guessed pixel math leaves gaps.
Fix: launch the window, then force the exact pixel rect via `wmctrl -e`.

Screen pixel rects (LO's box, `xrandr --listmonitors`):
- left:   (0,    0,    1920, 1080)
- mid:    (1920, 0,    2560, 1080)
- right:  (4480, 0,    1920, 1080)
- bottom: (2274, 1080, 1920, 1080)

2x2 cell math (GAP=4):
  cw = (SW - 3*GAP)//2
  ch = (SH - 3*GAP)//2
  X  = SX + GAP + col*(cw+GAP)
  Y  = SY + GAP + row*(ch+GAP)      # col=slot%2, row=slot//2

`pack()` (bash, in the painter):
```
pack() {
  local t="$1" X="$2" Y="$3" W="$4" H="$5" ws="$6" w=""
  for i in $(seq 1 40); do
    w=$(wmctrl -l 2>/dev/null | grep -F "$t" | head -1 | cut -d" " -f1)
    [ -n "$w" ] && break; sleep 0.3; done
  [ -z "$w" ] && return
  wmctrl -i -r "$w" -e 0,"$X","$Y","$W","$H"
  wmctrl -i -r "$w" -t "$ws"
}
```
Call after all windows launched (+ `sleep 2` so the last one's frame exists):
```
packall() {
  pack "ENI1::build" 1924 4 1274 534 0
  # ...one per mini, per screen/slot/ws...
}
packall
```
Verify: `wmctrl -l -G` prints X,Y,W,H per window — cells must tile with no gaps.
Heartbeat + master are SMALL `72x6` overlays on the top strip of the MIDDLE
monitor (over the grid, not covering builders); master only on WS1.

## 2. Staggered boot (kill the 429 stampede)
Problem: 64 `hermes chat` minis forked at once exhaust OpenRouter free-tier
(HTTP 429 after 8 retries). Model rotation does NOT help — the 429 is
account-wide, so rotating just moves the stampede to the next slug.
Fix: one-time random pre-boot sleep in each run-script (BEFORE the self-heal loop):
```
sleep $(( (RANDOM % 50) + 3 ))
while true; do
  M="$(bash /tmp/eni_pick_model.sh)"
  python3 /home/hunter/.local/bin/eni_agent_term.py --name {name} \
    --task "/home/hunter/.cache/eni_parallel/task_{name}.txt" \
    --repl "hermes chat --yolo -m $M --provider openrouter" \
    --ctl /tmp/eni_ctl_{name} > /tmp/eni_logs/{name}.log 2>&1
  if grep -qiE '429|rate limit|Bad Request|not a valid model|401|403|Too Many Requests|ConnectionError|timed out' /tmp/eni_logs/{name}.log; then
    bash /tmp/eni_record_fail.sh "$M"
  fi
  free -m | awk '/Mem:/{f=$7} END{if(f<2500){exit 1}}' || sleep 20
  sleep 3
done
```
Also `sleep 2.5` between window spawns in the launch loop. Config spine already
set: `fallback_providers=[gemini]`, `api_max_retries=8`.

## 3. Lumen leash grep (avoid false positives)
Flag only the GUI app, not headless CLIs:
  pgrep -af 'python -m lumen[^-.]'      # matches `python -m lumen` (app)
  # does NOT match `python -m lumen.config` / `python -m lumen.doctor` (safe)
Task brief forbids `python -m lumen` / GUI / X surface; allows pytest/flake8/mypy/importlint.

## 4. Orphaned hermes-chat cleanup
  for pid in $(pgrep -f 'hermes chat --yolo'); do
    [ "$(ps -o ppid= -p $pid | tr -d ' ')" = "1" ] && kill -9 "$pid"
  done
Note: `pgrep -fc 'hermes chat --yolo'` also counts the ~69 proxy cmdlines
(their `--repl` contains that string) — subtract proxies before alarming.
