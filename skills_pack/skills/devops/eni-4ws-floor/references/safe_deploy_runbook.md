# Safe Deploy Runbook — ENI 4-Workspace Build Floor

Exact sequence that took the floor from a pre-crash runaway state to a stable,
self-building 70-window floor on 2026-07-11. Reuse this after any reboot, crash,
or "I don't see the build floor" report. ONE painter only — never a global
re-paint watchdog.

## 0. State probe (no changes)
```bash
id                                     # expect uid 1000(hunter), in sudo group
echo "DISPLAY=$DISPLAY"                # must be :0.0 to paint the host X
wmctrl -d                              # 4 workspaces, 6400x2160 canvas
pgrep -xc xfce4-terminal               # how many windows already alive
pgrep -af swarm_watchdog | grep -v grep   # Is the runaway re-painter live?
crontab -l | grep -v '^#' | grep -v '^$'  # dangerous lines: pl_stockbot_cycle, @reboot swarm_start
free -m | awk '/Mem:/{print "avail="$7}'  # <2000MB = already in trouble
```

## 1. Clean-kill the runaway (SCRIPT FILE, never inline)
Write `/tmp/clean.sh` and run `bash /tmp/clean.sh` as its OWN terminal call.
**GOTCHA (cost one wasted call):** `pkill -f 'hermes chat'` matches the
PARENT `bash -c` wrapper if that wrapper's own text contains the pattern -> the
whole call is SIGKILLed (exit -9) mid-run. Keep the kill script in a separate
file so its cmdline is just `/tmp/clean.sh` (no match). Never put the pkill in
the same command that also spells out the pattern.

clean.sh body:
```bash
#!/usr/bin/env bash
set +e
pkill -9 -f swarm_watchdog.sh 2>/dev/null
pkill -9 -f swarm_start.sh 2>/dev/null
for p in $(pgrep -x xfce4-terminal); do
  grep -qaE 'run_|heart_|master_|status_|eni_tabs' /proc/$p/cmdline 2>/dev/null && kill -9 "$p"
done
pkill -9 -f eni_agent_term.py 2>/dev/null
pkill -9 -f 'hermes chat --yolo' 2>/dev/null
pkill -9 -f 'hermes chat' 2>/dev/null
sleep 2
echo "xfce4-term left: $(pgrep -xc xfce4-terminal 2>/dev/null || echo 0)"
echo "hermes chat left: $(pgrep -af 'hermes chat' 2>/dev/null | wc -l)"
```

## 2. Neutralize the crash vectors
```bash
mv -f ~/Desktop/Commander/eni_swarm/swarm_watchdog.sh \
      ~/Desktop/Commander/eni_swarm/swarm_watchdog.sh.DISABLED 2>/dev/null
crontab -l 2>/dev/null | sed -E 's#^(.*(pl_stockbot_cycle|swarm_start).*)$#\#&#' | crontab -
# keep status_hub.py — it's read-only aggregation
```

## 3. Full perms on build paths
```bash
chmod -R u+rwx /tmp/eni_tabs /tmp/eni_logs 2>/dev/null
mkdir -p /tmp/eni_parallel /tmp/eni_logs
chmod -R ug+rwX /home/hunter/Commander/demiurge_scaffold \
  /home/hunter/Desktop/demiurge-3d /home/hunter/Desktop/apps/lumen 2>/dev/null
```

## 4. Regenerate the canonical floor (scripts only, no launch)
```bash
python3 ~/.hermes/skills/devops/eni-4ws-floor/scripts/floor_setup.py
# emits 64 run_*.sh + 64 status_*.sh + 4 heart_*.sh + 1 master_WS1.sh + driver.sh + mem_sentinel.sh
# workspace spread must read 16/16/16/16 across -t 0/1/2/3
grep -oE 'wmctrl -i -r "\$new" -t [0-3]' /tmp/eni_tabs/driver.sh | sort | uniq -c
```
NOTE: floor_setup.py was patched so `ws_for_win = ws` for ALL screens — each
project owns its whole workspace across all 4 monitors. The original bug dumped
every project's side-screen builders onto WS1/2/3, starving WS4/LUMEN.

## 5. Launch (tracked background, NOT setsid-in-foreground)
Launch driver and sentinel as TWO separate `terminal(background=true)` calls.
The harness blocks setsid/nohup wrappers in a foreground command.
```bash
# call A (background, notify_on_complete=true — driver is bounded, exits after painting)
export DISPLAY=:0.0; exec bash /tmp/eni_tabs/driver.sh
# call B (background, notify false — sentinel is a daemon)
export DISPLAY=:0.0; exec bash /tmp/eni_tabs/mem_sentinel.sh
```

## 6. Verify (~90s later) — or just run scripts/verify_floor.sh
Healthy target state (measured 2026-07-11):
- terminals/workspace: WS1=20, WS2=17, WS3=17, WS4=16 (70 total; +1s are heartbeat/master overlays)
- eni_agent_term proxies: ~105 (benign 2x handoff, NOT growth)
- STATUS files in rolling 5-min window: ~30 (real work happening)
- memory avail: flat ~8.5GB (NOT climbing toward zero)
- watchdog: disabled; sentinel: alive (pid check), log empty = healthy
- samples per project show real content (SB RUNNING, FX DONE w/ new module, etc.)

## What a BAD state looks like (re-run clean + redeploy)
- watchdog PID alive -> OOM in minutes
- proxy count GROWING unboundedly -> runaway (sentinel should cap, but if it can't, kill + redeploy)
- memory avail < 2000MB and falling -> sentinel should be killing; if not, start it
- uneven per-workspace window counts -> re-check the ws_for_win patch in floor_setup.py
