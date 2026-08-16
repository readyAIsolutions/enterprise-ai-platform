# THE crash root cause (2026-07-11) — competing relaunchers + titleless windows

LO's box crashed/rebooted 3x. Root cause was NOT steady-state agent count — it was
a RUNAWAY multiplication from multiple auto-relaunchers fighting each other, made
invisible by a window-title bug. Fix both or the crash returns.

## Root cause 1 — MULTIPLE competing auto-relaunchers running at once
Three independent systems were live simultaneously, each self-healing on a loop,
each using DIFFERENT window/proc naming so none deduped the others:
- `swarm_watchdog.sh` (in ~/Desktop/Commander/eni_swarm/) — an infinite
  `while true; do ...; sleep 30; done` that calls `ensure_builder`/`ensure_viewer`
  for 48 minis EVERY 30s. This is a PROCESS/WINDOW BOMB when its dedup check fails.
- `paint_4ws_programs.py` floor (run_ENIx.sh windows) — a second painter model.
- `pl_stockbot_cycle.sh` (crontab, */5) — relaunches STOCKBOT_B* builders.
Together they doubled/tripled wrappers (observed 128 wrappers for 64 windows) until OOM.

DIAGNOSIS (do this FIRST when the floor keeps respawning after you kill it):
- `pgrep -af 'watchdog|paint_|relaunch|supervisor'` — find the supervisor.
- `crontab -l` — find cron relaunchers (pl_stockbot_cycle, etc.).
- If killing builders and they come back within ~30s, a supervisor is alive.

FIX (kill the ROOT, not the leaves):
1. Kill + NEUTRALIZE the watchdog so it can't restart:
   `mv swarm_watchdog.sh swarm_watchdog.sh.disabled; chmod -x` (kill its PID too).
2. Pause competing cron: `crontab -l | sed 's#.*pl_stockbot_cycle.*#\#&#' | crontab -`
   (keep status_hub — it's a harmless aggregator).
3. THEN nuke the floor and confirm it STAYS at zero for 20s (no respawn).
4. Run ONE painter only. Do NOT run a 30s-interval global re-paint watchdog. Self-heal
   belongs in each builder's OWN `while true` run-script (restarts only ITS proxy), NOT
   in a global re-painter that relaunches the whole floor.

## Root cause 2 — xfce4-terminal --title DOES NOT STICK (windows show as "Terminal")
`xfce4-terminal --disable-server --title "SB01::build" -e ...` produces a window whose
wmctrl title is generic "Terminal", NOT "SB01::build" (dynamic-title override; worse with
a `--tab` second tab whose command sets no title). An OSC escape
(`printf '\033]2;TITLE\007'`) also did NOT reliably override the initial --title.

WHY THIS CAUSES THE CRASH: `swarm_lib.sh`'s `ensure_viewer`/`ensure_master` check
`wmctrl -l | grep -qF "SB01::build"` to decide if the window already exists. Since the
title never matches, the check ALWAYS says "missing" → relaunches a new window every
watchdog cycle → hundreds of windows → OOM. Grep-by-title dedup is BROKEN on this box.

FIX — never rely on window titles for placement/dedup. Use ID-DIFF capture:
```bash
before=$(wmctrl -l | awk '{print $1}' | sort)
xfce4-terminal --disable-server -e "bash $runscript" --geometry 90x24+$X+$Y </dev/null >/dev/null 2>&1 & disown
for i in $(seq 1 40); do
  after=$(wmctrl -l | awk '{print $1}' | sort)
  new=$(comm -13 <(echo "$before") <(echo "$after") | head -1)
  [ -n "$new" ] && break; sleep 0.3
done
wmctrl -i -r "$new" -e 0,$X,$Y,$W,$H   # exact pixel fill
wmctrl -i -r "$new" -t "$WS"           # move to workspace
```
Launch windows SEQUENTIALLY (one at a time) so the before/after diff is unambiguous.
This is a ONE-SHOT paint (kill-all first, launch each once), so no title-based dedup is
needed at all. Combine with the per-builder staggered boot + memory guard.

## Root cause 3 (tooling) — proxy CLI is `--ctl`, not `--fifo` (verify with --help!)
This session `eni_agent_term.py` REJECTED `--fifo` ("unrecognized arguments: --fifo")
and required `--ctl /tmp/eni_ctl_<NAME>`. The skill elsewhere says `--fifo`. The CLI has
drifted before — ALWAYS run `python3 ~/.local/bin/eni_agent_term.py --help` and match the
actual flag. A wrong flag makes every builder error instantly and loop forever (no boot).

## Memory safety for 64+ agents on a 30GB box
64 builders + masters grow memory as their contexts fill (each caps ~262K tokens). At full
context this can exceed 30GB+swap → OOM. Two guards make the floor self-limiting:
- Per-builder run-script memory guard: `while [ "$(free -m|awk '/Mem:/{print $7}')" -lt 3000 ]; do sleep 15; done`
  BEFORE (re)starting the proxy — a dead builder won't restart while RAM is tight (parks it).
- A KILL-ONLY sentinel daemon (`mem_sentinel.sh`): if avail RAM < 1500MB, SIGTERM the single
  highest-RSS `hermes chat` agent. It NEVER launches anything (cannot cause a runaway). The
  killed agent's memguard then keeps it parked until RAM frees. Result: the floor runs as
  many agents as physically fit and parks the rest instead of crashing.

## Self-kill trap (bit me 4x this session)
`pkill -f 'PATTERN'` AND `pgrep -f 'PATTERN' | kill` BOTH kill your own shell (exit -9/-15)
when PATTERN appears anywhere in the running command line (it always does — it's in the
pkill/pgrep arg). ALWAYS put kill patterns in a SCRIPT FILE (`bash /tmp/kill.sh`) whose
invoking cmdline doesn't contain the pattern, or kill by numeric PID only.

## execute_code 50-tool-call cap
`execute_code` silently stops after 50 tool calls. Do NOT loop `hermes_tools.write_file`
for 64×3=192 files — it stops at ~16 and reports "success". Use plain Python
`open(path,'w').write()` for bulk file generation to /tmp (no tool-call limit), then verify
counts with one `ls`. (The gen_floor.py phantom-fail note about open().write() applies to
the eni_swarm/ dir specifically; /tmp is fine.)
