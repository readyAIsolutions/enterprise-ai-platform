# Agent death, detection & revival (parallel ENI swarm)

Companion to the "Agent death, detection & revival" section in SKILL.md.
Copy these commands; they are the difference between a swarm that runs for
hours and one that silently dies in the first five minutes.

## 1. Launch correctly (the two lethal mistakes)

PERSISTENT agent (the swarm default) — use the PTY bridge, NO `-q/--yolo` one-shot:
```bash
HERMES_CTL_FIFO=/tmp/eni_ctl_${name} python3 ~/.local/bin/eni_agent_term.py \
  --name "${name}" \
  --task "$CACHE/task_${name}.txt" \
  --repl "hermes chat --yolo -m ${model} --provider openrouter"
  --yolo -m tencent/hy3:free -p openrouter
```
ONE-SHOT agent — only then is `-q/--yolo` acceptable, and it will exit
after one loop by design (do not expect it to keep receiving FIFO guidance):
```bash
hermes -p eni chat -q "$(cat /tmp/task_NAME.txt)" --yolo -m tencent/hy3:free -p openrouter
```

KEY/PROVIDER guard before launch (every agent dies at startup without this):
```bash
ls -l ~/.hermes/profiles/eni/.env          # must contain OPENROUTER_API_KEY
grep -q OPENROUTER_API_KEY ~/.hermes/profiles/eni/.env || \
  cp ~/.hermes/.env ~/.hermes/profiles/eni/.env
```

## 2. Verify liveness right after launch (do not trust "launcher exited 0")

Real agent count (the proxy dies with the agent, so this is the truth):
```bash
pgrep -fc 'hermes -p eni chat --y[o]lo'
```
Per-agent (keyword lives in the PROXY argv, not hermes's — grep the proxy):
```bash
pgrep -fc 'eni_agent_term[.]py.*NEWS'      # correct
pgrep -fc 'hermes -p eni chat.*NEWS'       # WRONG — never matches
```
Real API activity in the last 2 minutes (zombie shell if zero):
```bash
find ~/.hermes/profiles/eni/sessions/ -name 'request_dump_*.json' -newermt '-2 minutes' | wc -l
```
Spot a dead window's error:
```bash
# the xfce4-terminal tab shows one of:
#   "No LLM configured for this provider"  -> bad -p or missing key
#   blank after first task                  -> you used -q/--yolo (one-shot)
```

## 3. Why the `-q/--yolo` one-shot kills a swarm

`hermes chat -q X --yolo` is the one-shot query path: it feeds X as the single
user turn, runs the model until it stops, prints the result, and EXITS. The
PTY bridge instead spawns `hermes chat` (interactive REPL), waits for the
"Hermes Agent is ready" banner, then writes the task as the first keystroke —
leaving the REPL alive and listening on the control FIFO. Use the bridge for
anything that must persist.

## 4. Revival recipe (small dedicated window, no full relaunch)

When `pgrep` shows a dead agent, open ONE xfce4-terminal with just the dead
ones as tabs, reusing the existing task files:
```bash
mkdir -p /tmp/eni_revive
CACHE=/tmp/eni_revive
PROXY=~/.local/bin/eni_agent_term.py
xfce4-terminal --title="ENI-REVIVE" \
  --command "bash -c 'HERMES_CTL_FIFO=/tmp/eni_ctl_NEWS python3 $PROXY \"\$(cat $CACHE/task_NEWS.txt)\" /home/hunter/Commander/demiurge_scaffold --yolo -m tencent/hy3:free -p openrouter; exec bash'" \
  --tab --command "bash -c 'HERMES_CTL_FIFO=/tmp/eni_ctl_FEATURES python3 $PROXY \"\$(cat $CACHE/task_FEATURES.txt)\" /home/hunter/Commander/demiurge_scaffold --yolo -m tencent/hy3:free -p openrouter; exec bash'"
```
The persistent MASTER driver keeps the still-alive agents producing; LO sees
exactly which agents came back. Re-run the liveness checks above to confirm.

## 5. Free-model 429s are survivable; typed-loop death is not

When every free slug 429s, a persistent bridge agent retries/throttles and
eventually answers. A `-q/--yolo` one-shot agent that exited after one query never
retries. So: prefer the bridge, spread agents across >=2 working models
(`scripts/probe_free_models.sh`), and tolerate 429s — they self-heal. The
providers.yaml auto-pruned by the probe script can STILL 429; that is normal,
not a death.
