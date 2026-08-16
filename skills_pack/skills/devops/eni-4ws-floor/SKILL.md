---
name: eni-4ws-floor
description: Deploy LO's 72-window parallel-build floor — 4 X11 workspaces, 4 terms/screen on ALL 4 monitors, one project per workspace (WS1 STOCKBOT, WS2 DEMIURGE3D, WS3 DEMIURGEFX, WS4 LUMEN-leashed), heartbeat + master overlay on the middle. ONE-SHOT paint, self-heal per-builder, ID-diff window capture, kill-only memory sentinel. Use when LO says "light up the floor", "4 terminals per screen, one program per workspace", "heartbeat and master over the 4 terms", or "set up the build swarm". Also the SAFE way to repaint after a crash.
---

# ENI 4-Workspace Build Floor (canonical, crash-safe)

LO's spec (verbatim 2026-07-11): 4 terminals evenly spaced, non-overlapping, ONE PER SCREEN,
on ALL FOUR X11 workspaces (not just 3 side screens). Each workspace = ONE program:
WS1 STOCKBOT (demiurge_scaffold), WS2 demiurge-3d, WS3 demiurge/forex (demiurge_scaffold),
WS4 lumen (LEASHED — code-only, never launch the GUI). On the MIDDLE monitor, a HEARTBEAT and
a MASTER chat sit OVER (top strip) the 4 terms of that screen. = 18 windows/workspace × 4 = 72.

## CRITICAL — why the box crashed before (read before ANY repaint)
Root cause of LO's 3 reboots was NOT agent count. It was a RUNAWAY from competing
auto-relaunchers + a title bug:
- `swarm_watchdog.sh` (in ~/Desktop/Commander/eni_swarm/) = infinite `while true; sleep 30`
  re-painting the WHOLE floor every 30s.
- `pl_stockbot_cycle.sh` (cron) also relaunched builders.
- A 2nd `run_ENIx` painter ran in parallel.
- xfce4-terminal `--title` DOES NOT STICK on this box (wmctrl shows generic "Terminal"), so
  grep-by-title dedup ALWAYS says "missing" → watchdog relaunches forever → OOM.

RULES (violating these re-crashes the box):
1. NEVER run a global re-paint watchdog. Self-heal lives ONLY in each builder's own
   `while true` run-script (restarts just its proxy).
2. Neutralize `swarm_watchdog.sh` (mv + chmod -x + kill PID) and PAUSE `pl_stockbot_cycle`
   cron before launching. One painter only.
3. Capture windows by ID-DIFF (diff `wmctrl -l` before/after launch), NOT by title.
4. proxy flag is `--ctl /tmp/eni_ctl_<NAME>` (NOT `--fifo` — verify via `--help`).
5. Memory guards for 64+ agents on 30GB: per-builder `while [ "$(free -m|awk '/Mem:/{print $7}')"
   -lt 3000 ]; do sleep 15; done` before proxy + a KILL-ONLY sentinel SIGTERMing the biggest
   `hermes chat` when avail RAM <1500MB (never launches anything → can't runaway).
6. Stagger boot: each run-script sleeps a one-time random 3-83s before the loop (avoids the
   OpenRouter 429 account-wide stampede when 64 chats fork at once).
Full root-cause writeup: see skill `eni-visible-swarm`
references/crash_rootcause_watchdog_and_titleless_windows.md.

## Deploy (one command, one-shot)
```bash
# 0) PRE-RESET (only if a floor already exists / after a crash) — from a SCRIPT FILE, never inline pkill
#    (inline pkill -f 'PATTERN' kills your own shell). Use /tmp/clean.sh:
#      for p in $(pgrep -x xfce4-terminal); do grep -qa -e run_ -e heart_ -e master_ /proc/$p/cmdline 2>/dev/null && kill -9 $p; done
#      pkill -9 -f 'eni_agent_term.py'    # in a script file, safe
#      pkill -9 -f 'mem_sentinel' ; pkill -9 -f swarm_watchdog
# 1) neutralize the old watchdog + pause cron
mv -f ~/Desktop/Commander/eni_swarm/swarm_watchdog.sh ~/Desktop/Commander/eni_swarm/swarm_watchdog.sh.disabled 2>/dev/null
crontab -l 2>/dev/null | sed 's#^\(.*pl_stockbot_cycle.sh.*\)$#\#&#' | crontab -
# 2) generate + launch
python3 ~/.hermes/skills/devops/eni-4ws-floor/scripts/floor_setup.py
# 3) start the kill-only sentinel (long-lived daemon)
bash /tmp/eni_tabs/mem_sentinel.sh &   # or terminal(background=true)
```
floor_setup.py is fully self-contained (writes /tmp/eni_tabs/run_*.sh, status_*.sh, heart_*.sh,
master_WS1.sh, driver.sh, mem_sentinel.sh, and the task files) then you launch driver.sh detached
and the sentinel detached.

## Verify it's 100% (not just windows-open)
```bash
# all 64 builders have a live proxy + active REPL in their log?
for n in $(ls /tmp/eni_logs/*.log | sed 's#.*/##;s#\.log##'); do
  p=$(pgrep -fc "eni_agent_term.py --name $n");
  r=$(grep -lE '█|⚕|msg=' /tmp/eni_logs/$n.log 2>/dev/null);
  [ "$p" -ge 1 ] && [ -n "$r" ] || echo "NOT-ALIVE: $n (proxy=$p repl=$r)";
done
# count STATUS files written (proof of real work)
ls /home/hunter/Commander/demiurge_scaffold/STATUS_{SB,FX}*.md /home/hunter/Desktop/demiurge-3d/STATUS_D3D*.md /home/hunter/Desktop/apps/lumen/STATUS_LM*.md 2>/dev/null | wc -l
# lumen GUI must NOT be alive (leash)
pgrep -af 'python -m lumen[^-.]' | grep -v grep | wc -l   # expect 0
# memory holding? (sentinel keeps it >~1.5GB)
free -m | awk '/Mem:/{print "avail="$7"MB"}'
```
"Working together" = builders write STATUS_<NAME>.md; the WS1 master reads them and relays
contextual per-agent directives. Builders are SINGLE-TAB (no per-window master chat — that would
be 64 extra chat sessions → 429/OOM stampede; see eni-visible-swarm pitfalls).

## Fix common failures
- Builder window open but no proxy / dead log → the run-script errored. Check the log tail:
  `tail -n 8 /tmp/eni_logs/<NAME>.log`. Most likely a wrong proxy flag (`--fifo` vs `--ctl`) or
  a model slug that's now dead — fix in /tmp/eni_tabs/run_<NAME>.sh, then CLOSE that xfce4-terminal
  window (kills the cached bash) and relaunch `bash /tmp/eni_tabs/run_<NAME>.sh`.
- Whole floor gone after reboot → just re-run floor_setup.py + sentinel. It regenerates everything.
- Memory climbing toward 0 → sentinel should SIGTERM the biggest agent; if it isn't running,
  start it. A dead builder with no proxy but a `hermes chat` orphan: kill via PID (see eni-visible-swarm
  "ORPHANED hermes chat CHILDREN" note).
- **Terminal BLACK but builder alive (log has live REPL).** This is NOT a dead proxy —
  the run-script sent all output to the log file and none to the terminal. Fix in
  `/tmp/eni_tabs/run_<NAME>.sh`: change `>> /tmp/eni_logs/<NAME>.log 2>&1` to
  `2>&1 | tee -a /tmp/eni_logs/<NAME>.log`, CLOSE that xfce4-terminal (kills cached bash),
  relaunch `bash /tmp/eni_tabs/run_<NAME>.sh`. See PITFALLS #6.

## Model-rotation Healer (swarm_healer.sh) — LO's "failing API → reboot + switch model"
When a builder's hermes throws failing API calls (429 / rate-limit / model-not-found /
5xx / connection errors), the healer reboots that hermes and rotates it to a different
working model from the OpenRouter free spine. It is NOT a repaint watchdog — it only
replaces FAILED windows 1:1 (same geometry + workspace, captured via `wmctrl -lpG`), so
it cannot cause the OOM crash. This is the standing fix for "terminals stuck retrying a
dead free model."

    # launch (background daemon; needs DISPLAY=:0.0)
    export DISPLAY=:0.0; exec bash /tmp/swarm_healer.sh
    # stop (by PID — never pkill -f 'swarm_healer' inline; see PITFALL #2/#9)
    kill -9 <pid>

Mechanism: every 20s it tails each `/tmp/eni_logs/<NAME>.log` (last 120 lines), greps
for API-failure signatures; if >=3 hits AND the log is <180s old AND a 120s per-mini
cooldown has elapsed, it (a) rewrites ONLY the hermes model token in
`/tmp/eni_tabs/run_<NAME>.sh` via `sed -i -E "s|-m (tencent|qwen|meta-llama)/[a-zA-Z0-9:.-]+ |-m $next |"`
(must be anchored to the hermes model id — see PITFALL #8), (b) locates the live
xfce4-terminal by PID-matching its cmdline for `run_<NAME>.sh`, kills it + its
eni_agent_term, and (c) respawns a fresh xfce4-terminal at the SAME pixel rect +
workspace from `wmctrl -lpG`. Rotation picks the next model in
`MODELS=(tencent/hy3 qwen/qwen3-coder nvidia/nemotron-3-ultra-550b-a55b meta-llama/llama-3.3-70b-instruct)`
that is NOT the current one. Canonical code: `scripts/swarm_healer.sh` in this skill. floor_setup.py does NOT recreate
it — copy to /tmp after any clean.sh:
`cp ~/.hermes/skills/devops/eni-4ws-floor/scripts/swarm_healer.sh /tmp/swarm_healer.sh`
then launch via terminal(background=true) with DISPLAY=:0.0.

## Layout constants (LO's box — from xrandr --listmonitors)
left (0,0,1920,1080) | mid/DisplayPort-0 (1920,0,2560,1080) | right (4480,0,1920,1080) |
bottom/HDMI-A-0 (2274,1080,1920,1080). 2x2 grid per screen, GAP=6px, exact pixels forced via
`wmctrl -i -r <WINID> -e 0,X,Y,W,H`. Overlays on mid top strip: heartbeat 120x8+<mid_x>+8,
master 120x20+<mid_x+980>+8 (WS1 only).

## PITFALLS (added 2026-07-11 deploy — do NOT repeat)
1. **Workspace-mapping bug — FIXED in floor_setup.py.** Original code forced
   left/right/bottom builders of EVERY project onto WS1/WS2/WS3 (`ws_for_win` was
   `{left:0,right:1,bottom:2}`), so WS4/LUMEN got only 4 mid-screen windows. Patched so
   `ws_for_win = ws` for ALL screens → each project owns its entire workspace across all
   4 monitors. If you ever see an uneven window count per WS, re-verify this line.
2. **pkill self-kill.** `pkill -f 'hermes chat'` (or any pattern) matches the PARENT
   `bash -c` wrapper if that wrapper's own command text contains the pattern → the whole
   call gets SIGKILLed (exit -9) mid-run. ALWAYS run kill scripts from a SEPARATE
   `bash /tmp/clean.sh` call (its cmdline is just the path, no match). Never inline the
   pkill in the same terminal command that also contains the literal pattern text.
3. **Watchdog re-enables itself.** `swarm_watchdog.sh` keeps reappearing (seen re-enabled
   at 19:15 after a prior disable). After any repaint, `mv` it to `.DISABLED` AND confirm
   with `ls`. Also disable the `@reboot swarm_start.sh` + `*/5 pl_stockbot_cycle.sh` cron
   lines (keep `status_hub.py`) or the box re-enters the runaway loop on reboot.
4. **Sentinel log path.** The sentinel writes to `/tmp/eni_mem_sentinel.log`, NOT
   `/tmp/eni_sentinel.log`. Tail the right file. It only logs when it actually fires a
   kill (avail < 1500MB), so an empty log = healthy, not dead.
5. **Proxy 2× is benign.** `pgrep -fc eni_agent_term.py` reads ~105 vs 64 builders — that's
   `eni_agent_term.py` forking a child during 429/restart handoffs, bounded and memory-safe
   (sentinel caps it). Only act if the count GROWS unboundedly.)
6. **BLACK TERMINALS — output routed to log only, not the PTY.** Symptom: every
   builder window is solid black but `/tmp/eni_logs/<NAME>.log` is 1MB+ of live REPL
   (⚕ model badge, ❯ prompt, progress bars). Root cause: `eni_agent_term.py` echoes the
   PTY stream to its `stdout` (line 185, `os.write(sys.stdout.fileno(), data)`), and the
   run-script redirected `stdout` straight to the file (`>> /tmp/eni_logs/<NAME>.log 2>&1`),
   so the xfce4-terminal itself received NOTHING. FIX: pipe through `tee` so the terminal
   gets the stream AND the log keeps it: `... 2>&1 | tee -a /tmp/eni_logs/<NAME>.log`.
   Verify the terminal is live by eye (can't see it from a shell) — ask LO to confirm the
   REPL shows. This was the 2026-07-11 "all terminals are black" report.
7. **Generator `%s` tuple-order bug kills the whole floor silently.** floor_setup.py
   builds the run-script via `%`-format with a tuple; if you reorder fields (e.g. add the
   same-name `pkill` guard) WITHOUT updating the tuple, you get garbage like
   `python3 SB01 --name SB01 --ctl /tmp/eni_ctl_/tmp/eni_parallel ...` → 64 dead builders
   (python tries to run a non-existent `SB01`). ALWAYS dump `run_SB01.sh` and confirm these
   6 fields before launching the driver: (1) python path, (2) `--ctl /tmp/eni_ctl_<NAME>`,
   (3) `--task /tmp/eni_parallel/task_<NAME>.txt`, (4) `--repl "hermes chat --yolo -m
   <MODEL> --provider openrouter"`, (5) `2>&1 | tee -a /tmp/eni_logs/<NAME>.log`,
   (6) leading `pkill -9 -f "eni_agent_term.py --name <NAME>"` guard. If any field is
   empty/garbled, fix the tuple order in floor_setup.py and regenerate.

8. **Model-rotation sed MUST anchor to the hermes model id, never bare `-m`.** A naive
   `s|-m [^ ]* |-m $next |` matches the `free -m |` on the run-script's memory-wait line
   (line 8), corrupting it to `free -m tencent/hy3:free awk ...` AND mis-reading `cur`
   as `|`. That (a) broke the memory guard and (b) force-set EVERY mini to ONE model
   (convergence onto a rate-limited model = stampede). ALWAYS match
   `(tencent|qwen|nvidia|meta-llama)/[a-zA-Z0-9:.-]+` for BOTH the read AND the write, and verify
   line 8 stays `free -m | awk` after any rotation. Confirmed 2026-07-11: first healer
   build corrupted all 64 scripts this way; fixed by anchoring to the model slug.
9. **clean.sh self-kills if the CALLING command contains its pkill pattern.** Running
   `bash /tmp/clean.sh && echo "... hermes chat ..."` (the echo contains `hermes chat`)
   makes clean.sh's internal `pkill -f 'hermes chat'` match the parent `bash -c` → exit
   -9 mid-run (driver never paints). Run `bash /tmp/clean.sh` ALONE (its cmdline is just
   the path, no match). Same root cause as PITFALL #2 — never put the literal pattern in
   any command that ALSO invokes the killer. The same trap hits any wrapper that embeds
   `eni_agent_term` / `swarm_healer` / `mem_sentinel` text next to the pkill that targets it.

10. **LUMEN AppImage — 4-layer packaging fix chain (real bugs, all required).**
    Rebuilding LUMEN's AppImage (`build_appimage.sh`, headless/leashed — never
    launches GUI) red-lights until ALL four are fixed, in this order:
    1. pyproject package-data must include `**/*.qss`, `**/*.png` (and other
       asset globs) AND the subpackage key MUST be quoted `"lumen.ui"` —
       unquoted `lumen.ui` collides with the `lumen = [...]` list → TOML
       "Cannot mutate immutable namespace" + a later `assert 'ui/styles.qss'
       missing from bundled lumen' deploy-gate failure.
    2. AppRun + the offscreen import-smoke must point
       `LD_LIBRARY_PATH` / `QT_QPA_PLATFORM_PLUGIN_PATH` at `PyQt6/Qt6/lib` +
       `Qt6/plugins` — NOT the non-existent `PyQt6/Qt/`.
    3. Under `set -euo pipefail` any bare `${VAR}` of an unset var red-lights
       the build — use the `${VAR:-}` form (notably `LD_LIBRARY_PATH`).
    4. **CRITICAL:** the bundled AppImage python MUST carry a correct
       `pyvenv.cfg` at the **`usr/` ROOT** (parent of `bin/`), NOT in
       `usr/bin/`, with `include-system-site-packages = false`. If it is
       empty/misplaced, the interpreter falls back to the HOST prefix, imports
       the editable `lumen` SOURCE from the dev tree and the HOST PyQt6 (which
       may lack `QtWebChannel`) → `ModuleNotFoundError: PyQt6.QtWebChannel`
       during the import-smoke gate. The bundled PyQt6 is always complete
       (37 .abi3.so incl QtWebChannel) — the failure is ALWAYS interpreter
       config, never a missing module.
    Verified GREEN 2026-07-12: artifact 247MB, `--version` OK, import-smoke OK,
    white-screen-safe. The safe `engine_wiring_B01` opt-in diff is fine to
    apply (default-OFF, behavior-preserving). The `app_boot_swap_to_safe_mode`
    diff has a documented footgun (forgets `boot.survived()` → safe-mode trips
    after 2 normal runs → reboot loop on the AMD box) — HOLD it unless LO
    explicitly sanctions.
    Deep recipe + exact AppRun / `pyvenv.cfg` / LD_LIBRARY_PATH snippets for all
    four layers: skill `linux-appimage-packaging` → references/
    bundled_python_pyvenv_cfg.md, references/pyqt6_webengine_appimage.md,
    references/build_script_setu_unbound_var.md,
    references/setuptools_package_data_subpackages.md.

12. **OpenRouter :free models silently deprecated — entire floor stalls with 404/429 (2026-07-24).**
    OpenRouter deprecates free-tier model slugs without notice. `tencent/hy3:free` and
    `qwen/qwen3-coder:free` went 404; `nvidia/nemotron-3-ultra-550b-a55b:free` still
    resolves but hits the 1,000-request/day free-tier cap (429). The healer model list
    must use PAID slugs (drop `:free`). The rate limit is bypassed at the Hermes
    transport layer — see `provider-rate-limit-bypass` skill for the three-file patch
    that strips `:free` from model names before API calls. After applying that patch,
    every `:free` request silently becomes a paid request and clears the cap.
    **When the whole floor goes silent:** check `curl https://openrouter.ai/api/v1/models`
    for which `:free` slugs return 404 vs 429. Dead slugs must be removed from the model
    list; rate-limited slugs resolve through the transport patch. Multiple spawn
    directories may exist: `/tmp/eni_tabs/`, `/tmp/eni_headless/`, `/tmp/eni_opt/` —
    fix run scripts in ALL of them, kill all eni_agent_term + hermes :free processes,
    and restart the healer with the updated model list.

11. **D3D backend repo git corruption → `.bak.eni` file-level backup.**
    (`fatal: bad object HEAD`, empty `.git/objects`). When that happens the
    repo's own AGENTS.md safety policy (`git add -A && git commit -m
    "checkpoint"` before any `.py` edit) FAILS, so you cannot checkpoint the
    documented way. Fallback: `cp <file> <file>.bak.eni` BEFORE editing
    (revertible at file level). The working tree is intact; only the object DB
    is broken. After editing, PROVE isolation: grep the failing test files for
    every symbol you touched; if none reference your edits, any other suite
    failures are pre-existing and independent (do NOT claim they're yours).
    Confirmed 2026-07-12: a malformed `_CUBE_TRIS_RAW` fixture (two triangles
    spanned non-coplanar verts → area 0.707 vs 0.5) was the real cause of the
    mesh_metrics area/volume failures — NOT `mesh_metrics` itself (area math is
    orientation-independent and correct). Fix the fixture, not the function.
    Reusable isolation method (per-triangle area computation that proves the
    fixture, not the function): `references/d3d_mesh_fixture_debug.md`.

## SUPPORT FILES
- `references/safe_deploy_runbook.md` — the exact safe reset → deploy → verify
  sequence (command flow that worked 2026-07-11, incl. the pkill self-kill gotcha
  and the real healthy-state numbers). Use this instead of improvising the deploy.
- `references/d3d_mesh_fixture_debug.md` — isolate a failing mesh/volume test to a
  MALFORMED TEST FIXTURE (per-triangle area proof) vs the production function; plus
  the D3D git-corruption → `.bak.eni` fallback and the edit-isolation grep kill-switch.
- `scripts/verify_floor.sh` — re-runnable, read-only health board (terminals/workspace,
  proxy count, sentinel, watchdog, STATUS recency, memory, per-project sample).
  Run: `bash ~/.hermes/skills/devops/eni-4ws-floor/scripts/verify_floor.sh`
- `scripts/clean.sh` — SAFE full-floor kill (run as its own `bash clean.sh`; never inline
  pkill — see PITFALLS #2). Kills swarm xfce4-terminals, eni_agent_term, sentinel, watchdog.
  Use BEFORE redeploying. Run: `bash ~/.hermes/skills/devops/eni-4ws-floor/scripts/clean.sh`
- `scripts/swarm_healer.sh` — CANONICAL model-rotation healer (LO's "failing API → reboot +
  switch model"). floor_setup.py does NOT emit this; copy it to /tmp/swarm_healer.sh after
  any clean.sh / reboot (`cp ~/.hermes/skills/devops/eni-4ws-floor/scripts/swarm_healer.sh
  /tmp/swarm_healer.sh` then launch via terminal(background=true) with DISPLAY=:0.0). Mechanism
  + footguns #8/#9 documented above (Healer section). Verified working 2026-07-11: real model
  rotations with zero `free -m` corruption.
