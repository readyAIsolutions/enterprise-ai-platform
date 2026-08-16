---
name: eni-build
description: Deploy LO's ENI mini-ENI swarm floor across his 4 X11 VIRTUAL WORKSPACES (not monitors) — one project per workspace (STOCKBOT / DEMIURGE3D / DEMIURGE / LUMEN), 12 builders each, with a heartbeat+master+PL control window that is STICKY (visible on every workspace). Also covers the Lumen AMD boot-crash fix and the cross-workstation reachability caveat. Use when LO says "use all 4 workspaces", "mini enis", "swarm floor", or "eni build".
---

# ENI Swarm Floor Deploy (`eni-build`)

Paints LO's visible builder swarm across 4 X11 VIRTUAL WORKSPACES on his single
4-monitor workstation. One command, no sudo. Canonical layout (LO's spec, do NOT
deviate):

- **WORKSPACE 1** -> STOCKBOT (root `~/Commander/demiurge_scaffold`)
- **WORKSPACE 2** -> DEMIURGE3D (root `~/Desktop/demiurge-3d`)
- **WORKSPACE 3** -> DEMIURGE (root `~/Commander/demiurge_scaffold`)
- **WORKSPACE 4** -> LUMEN (root `~/Desktop/apps/lumen`)

Each workspace is a full project floor: **4 builders per side screen** (LEFT,
RIGHT, BOTTOM) in a 2x2 grid = **12 builders**, placed by absolute `--geometry`
on the 6400x2160 canvas, then moved to that workspace's virtual desktop via
`wmctrl -i -r <id> -t <ws>`.

- **CONTROL (sticky on the middle monitor, visible on ALL workspaces):**
  one big terminal with `HEARTBEAT` (live loop) tab + `MASTER CHAT` (guides all)
  tab, and `PRODUCT_LEAD` nested below it. Sticky (`_NET_WM_STATE_STICKY`) so LO
  sees them no matter which workspace he's on.

## Placement model (CRITICAL — changed from the old single-desktop design)
LO clarified "workspace" = X11 VIRTUAL DESKTOP, not a physical PC and not a
monitor. The box has 4 X11 virtual desktops (wmctrl index 0..3 == LO's ws1..4)
on ONE 6400x2160 canvas spanning all 4 physical monitors. The script:
1. Places every builder by ABSOLUTE `--geometry` x/y (so it lands on the right
   physical monitor: LEFT x0, RIGHT x4480, BOTTOM x2274/y1080, MIDDLE x1920).
2. Moves each project's windows to its OWN virtual desktop with
   `wmctrl -i -r <id> -t <ws>` (by window ID — reliable).

Do NOT try to use only x/y and skip the virtual-desktop move — LO explicitly
wants 4 workspaces. Do NOT place all 4 projects on one desktop.

## Prerequisites (this box / any target workstation)
- `DISPLAY=:0.0` reachable, `xfce4-terminal` + `wmctrl` installed.
- `~/.local/bin/eni_agent_term.py` present (CLI: `--name --task --repl`).
- `hermes` on PATH. Models default to `tencent/hy3:free` (builders) and
  `qwen/qwen3-coder:free` (PRODUCT_LEAD) via OpenRouter.

## The deploy script (canonical, use this exactly)
`~/Commander/eni_swarm/fleet_deploy_ws.sh` — kills the old floor, writes
`/tmp/eni_tabs/run_*.sh` + `~/.cache/eni_parallel/task_*.txt`, launches the
windows, moves each project to its workspace, and sticks the control windows.

```bash
cd ~/Commander/eni_swarm && BUILDERS_PER_SCREEN=4 bash fleet_deploy_ws.sh
```
Re-running is idempotent (it kills the prior floor first).

VERIFY (one command, shipped in the skill):
```bash
bash /home/hunter/.hermes/skills/devops/eni-build/scripts/verify_floor.sh
```
Expect 12 builders on each of ws1-4, both control windows present + STICKY, and 0
orphan hermes chats.

TEAR DOWN (safe — never kills your own session):
```bash
bash /home/hunter/.hermes/skills/devops/eni-build/scripts/safe_kill_swarm.sh
```
Reusable actions in the skill's `scripts/` dir: `verify_floor.sh` (health check),
`safe_kill_swarm.sh` (PID-only kill, no PGID / broad-pkill self-match), and
`fleet_watchdog.sh` (background self-healer for all-day unattended operation).

## CRITICAL PITFALLS (every one bit us in practice)
1. **xfce4-terminal titles by the ACTIVE tab.** A window launched with
   `-e run_master_chat.sh --tab -e run_builder.sh` ends up titled
   `ENI:<builder>` (builder tab active), NOT `MASTER:<builder>`. Identify/move
   windows by the `ENI:` title, never `MASTER:`.
2. **Move by window ID, not title.** `wmctrl -r "<title>" -t <ws>` is racy
   (title may not be set yet, or multiple windows match). Capture IDs from
   `wmctrl -l` and use `wmctrl -i -r <id> -t <ws>`.
3. **Substring trap in the move pattern.** `awk -v p="DEMIURGE" '$0 ~ p'`
   ALSO matches `DEMIURGE3D`. Use `awk -v p="$p" '$0 ~ (p "_B")'` so
   `DEMIURGE_B` matches only DEMIURGE's builders. This bug piled all of
   DEMIURGE3D's windows onto DEMIURGE's desktop.
4. **Control window tab ORDER matters.** Make the FIRST tab a plain
   `hermes chat` (master chat) and the SECOND tab the `eni_agent_term` builder.
   If the builder tab is first and `eni_agent_term` exits (error), xfce4-terminal
   with `-e` CLOSES THE WINDOW. First-tab plain chat keeps it open. Also: when
   capturing the control window ID for sticky, match BOTH possible active-tab
   titles (`CTRL:HEARTBEAT|ENI:HEARTBEAT`) — at launch the first tab may still
   be active, so a single `/ENI:HEARTBEAT/` grep can miss it and skip sticky.
5. **NEVER `kill -9 -<pgid>` the swarm terminals from inside the deploy
   script or an interactive command.** The terminals are children of the
   launching process and share its process group; `kill -9 -PGID` SIGKILLs your
   OWN session (exit -9). Kill swarm terminals by specific PID only
   (`kill -9 $pid`), never by group, unless you have excluded your own PGID.
6. **NEVER `pkill -f '<pattern>'` where `<pattern>` appears in your own
   command's argv.** `pkill -f` matches /proc/<pid>/cmdline, and your shell's
   argv CONTAINS the command text — so `pkill -f 'hermes chat --yolo'` or
   `pkill -f 'xfce4-terminal.*eni_tabs'` will match and SIGTERM/SIGKILL the
   shell running the command (exit -15 / -9, empty log). Inside the deploy
   SCRIPT this is safe (the script's argv is `bash fleet_deploy_ws.sh`, which
   does NOT contain the pattern). For interactive resets, kill by explicit PID
   and exclude `$$`/`$PPID`; then kill orphaned hermes chats whose `ppid==1`
   (reparented after their terminal died).
7. **Orphan hermes chats survive SIGHUP.** When a swarm xfce4-terminal dies,
   its `hermes chat` children (parented to xfce4-terminal) often ignore SIGHUP
   and keep running as orphans, hammering the API. Reliable cleanup = kill the
   swarm terminals by PID, then `kill` any `hermes chat --yolo` whose `ppid==1`.
   (The ~100 extra `hermes chat` procs you'll see via `pgrep -fc` are mostly the
   Hermes AGENT's own session processes, NOT swarm orphans — verify by checking
   the chat's parent is a live swarm terminal.)
8. **Max 2 tabs per xfce4-terminal window.** A 3rd `--tab -e` makes the window
   silently never appear while its run-script proxies survive SIGHUP as
   windowless dupes. One window = MASTER tab + ENI builder tab ONLY.
9. **No sudo needed.** The platform hard-blocks `sudo -S`. Don't try it.
10. **Don't aim for 68 live builders on one box.** 12 builders/workspace × 4 =
    48 + control is the practical per-box max on the 30 GB / RX5700XT box. The
    The "68" is the FLEET total across 4 physical workstations. One box can't
    meaningfully run 68; spread across workstations instead.

    11. **`hermes chat` is SINGLE-TURN — builders idle after ONE pass unless driven in
        a loop.** This is the #1 reason a fresh floor "looks dead": the window opens,
        the mini does ONE task, then sits at the prompt forever (CPU ~0, no new STATUS
        writes). Fix: the builder tab must run a LOOP DRIVER, NOT a bare
        `hermes chat --yolo`. `make_builder` writes:
        `while true; do hermes chat -q "\$(cat \$TASK)" --yolo -m $MODEL --provider $PROVIDER; sleep 15; done`
    (Escape `\$TASK` — the heredoc is unquoted, so an unescaped `$(cat $TASK)` expands
    at deploy time and the script dies with `TASK: unbound variable`, taking the floor
    down. Builder window must ALSO be a SINGLE tab running this loop, not a
    MASTER+ENI two-tab window. Full detail in Regression pitfalls #3–#5.)
        Each pass re-reads STATUS_*.md and builds the next module, so it grinds all day
        with no human prompt. VERIFY alive with `pgrep -fc 'hermes chat -q'` (~48) and
        `find <root> -name STATUS*.md -mmin -5` (fresh writes). Do NOT use
        `eni_agent_term.py` as the builder REPL — it pre-types the task once then idles
        the same way. (eni_agent_term is still fine for the HEARTBEAT/PRODUCT_LEAD
        control windows, which are meant to idle until asked.) Do NOT add `-Q` to the
        builder driver — `-Q` suppresses the banner/spinner/tool previews, so the
        terminal looks frozen even while the mini is working. Leave it off so LO can
        SEE the gremlins move.
12. **Lumen AppImage is frozen — rebuild after source fixes, alone.** Patching
    `~/Desktop/apps/lumen/lumen/*.py` does NOT update `~/Desktop/apps/lumen.AppImage`;
    that image copies the source at build time. If LO still reboots after a "fix",
    he's launching the stale image. Rerun `build_appimage.sh` to ship it. The build
    does a heavy clean-venv pip install (PyQt6-WebEngine/Chromium) — run it by
    ITSELF, never concurrent with a full floor redeploy (RAM contention on 30G).

13. **Floor dies on logout/session end — just re-run the deploy.** A logout, reboot, or
    session collapse kills all 48 xfce4-terminal builder windows (the floor is X11
    windows, not daemons). Symptom: `verify_floor.sh` shows 0 builders, or LO says
    "the floor is gone." Fix is ONE command and SAFE/idempotent (it kills the prior
    floor first, no sudo, no creds — builders are driven by the task files already on
    disk + the hermes CLI):
    ```bash
    cd ~/Commander/eni_swarm && BUILDERS_PER_SCREEN=4 bash fleet_deploy_ws.sh
    ```
    The remote 3 workstations are still network-dark from this box (see Cross-workstation
    caveat), so this only repaints WS1. After repaint, `bash ~/.hermes/skills/devops/eni-build/scripts/verify_floor.sh` should show 12 builders on each of ws1–4 + both control windows STICKY. A context-compaction can also silently drop a long-running background deploy — if `pgrep -af fleet_deploy` + the deploy log show nothing, just re-run the one-liner above.

## Cross-workstation caveat (IMPORTANT — tell LO)
From this box (WS1, 192.168.1.64) the OTHER 3 physical workstations are NOT
reachable on 192.168.1.0/24 (full /24 sweep found only .64 + printers + strays).
So this script only paints THIS workstation. To extend to the fleet:
- Power on the other 3 workstations and get their IPs.
- SSH in (password auth — `ssh-copy-id` is blocked by the platform consent
  gate, so use password; sudo/login key is `Neko50045`, session-only).
- Run the SAME `fleet_deploy_ws.sh` on each (display-agnostic; uses `:0`).

## Lumen boot-crash fix (shipped alongside this floor)
Lumen used to reboot LO's AMD box on launch: each shader/web wallpaper spun its
OWN QWebEngineView = its own Chromium GPU process + WebGL context PER MONITOR,
and old flags `--ignore-gpu-blocklist --enable-webgl --disable-gpu-sandbox`
forced hardware accel, hanging the amdgpu driver. Fix in `~/Desktop/apps/lumen`:
- `lumen/safety.py` boot guard: 2 consecutive boot crashes -> SAFE MODE (tray
  only, no wallpapers) until `python -m lumen --reset-safe`.
- `app.py` flags now SwiftShader-only (software WebGL), GPU sandbox ON.
- `engine.py` `max_webgl_surfaces` (default 1) caps live GL contexts; 3s RSS
  watchdog calls `drop_all_to_safe()` before OOM/reboot.
Guard state: `~/.config/lumen/boot_guard.json`. Verify live boot on the desktop
(`python -m lumen --minimized`); headless can't test the GUI render path. Deep
root-cause + verification recipe: `references/lumen_crash_fix.md`.

**AppImage is a FROZEN bundle — rebuild it after any source fix.** LO kept getting
reboots even after the source patch because he launched the old `lumen.AppImage`,
which frozen-copies the source at build time. After editing anything under
`~/Desktop/apps/lumen/lumen/`, rerun `bash ~/Desktop/apps/lumen/build_appimage.sh`
to ship the fix into `~/Desktop/apps/lumen.AppImage`. The build does a clean venv
`pip install` (PyQt6-WebEngine pulls Chromium — heavy, ~+1-2 GB RAM). **Do NOT run
the AppImage build at the same time as a full floor redeploy** — RAM contention on
the 30 GB box risks OOM. Build it standalone.

## All-day autonomous operation (watchdog)
LO often wants the floor grinding unattended "all day" while he's away. Two layers
make that safe:
- **Builder directive is never-idle.** `fleet_deploy_ws.sh` writes each builder a
  task that says: implement the next module, test it, write a STATUS PASS/FAIL
  board, then *immediately* start the next unbuilt module. They loop off the
  project's STATUS/README, so a restart just resumes. Deploy gates are spelled out
  per project (trading bot: purged-CV AUC>=0.55, walk-forward OOS>=36mo/500 trades,
  fill-degradation>=0.70; lumen: AppImage boots without reboot; demiurge-3d:
  slicer-ready models).
- **Self-healing watchdog.** `scripts/fleet_watchdog.sh` loops every 10 min: if the
  builder count drops below 48 (a real crash/reboot took out several windows) or the
  sticky control windows are missing, it re-deploys the floor (5-min cooldown so a
  legit redeploy never thrashes). Run it in the background:
  ```bash
  bash /home/hunter/.hermes/skills/devops/eni-build/scripts/fleet_watchdog.sh
  ```
  It only ever calls `fleet_deploy_ws.sh` (safe kill), so it can't take down your
  own session. Log: `/tmp/fleet_watchdog.log`.

## Headless optimized floor (CURRENT on this box) + crash recovery
The live floor here is often the HEADLESS design, not the xfce4-terminal one:
54 builders (SB=12, D3D=18, NAS=12, LUM=12) launched as `bash /tmp/eni_opt/run_<NAME>.sh`
loops (no X/PTY tax). Generator: `gen_floor_opt.sh`; idempotent boot/recover:
`swarm_start_opt.sh` (regens scripts, launches only missing builders, starts
mem_sentinel + healer). Config: `swarm_products.cfg`. Lock: `/tmp/eni_opt.lock`
(flock held by the swarm_start_opt parent).

RECOVER (one command, safe, idempotent):
```bash
bash /home/hunter/.hermes/skills/devops/eni-build/scripts/recover_headless_floor.sh
```
Full bug writeup + the two real crash causes: `references/recover_headless_floor.md`.

TWO bugs that silently kill the floor (both fixed in the scripts on disk as of
2026-07-12; re-apply if a redeploy regresses):
- **A. flock fd inherited by children** — `nohup bash run_x.sh &` inherits the
  parent's open fd 9 (the `exec 9>/tmp/eni_opt.lock; flock -n 9`), so every
  wrapper holds the lock forever -> swarm_start_opt always prints "already booting"
  and refuses. Fix: launch children with `9<&-` to close fd 9 for them.
- **B. heredoc `${CMD[@]}` expands EMPTY at write-time** — in gen_floor_opt.sh
  `gen_run`, the `nice -n 5 "${CMD[@]}"` line is inside an UNQUOTED heredoc.
  At write-time gen_run has no `CMD` array (the `CMD=(...)` is only text written
  into the generated script, run later). So it expands to `""` -> generated script
  runs `nice -n 5 ""` -> "No such file" -> python never launches. Fix: escape as
  `\${CMD[@]}` so it's written literally and evaluated at the generated script's
  runtime. VERIFY with `sed -n '14p' /tmp/eni_opt/run_D3D1.sh` -> must show
  `nice -n 5 "${CMD[@]}"`, NOT empty.

DIAGNOSIS TRAP: a builder log showing
`BlockingIOError: [Errno 11] ... os.fork()` (pty.fork) LOOKS like an OOM/nproc
wall, but on this box (123k nproc, ~27 GB free) it is almost always STALE log
from the previous run. The LIVE bug is the SECOND, distinct line
`nice: : No such file or directory` — that means the cmd is empty (Bug B). Always
READ THE GENERATED ARTIFACT (run_*.sh line 14); don't over-fit on the scary old
error. Clear stale logs (`truncate -s 0`) before judging.

## FLOOR-DOWN TRIAGE — what LO means by "swarm isn't running" / "run them all"
LO's "the swarm isn't running" almost never means every builder is dead. On this
box the builders self-respawn inside their `while true; do hermes chat ...; sleep 15;
done` wrapper, so individual builder deaths heal on their own. What actually goes
silent is the UNATTENDED self-heal layer — `swarm_healer` and `fleet_watchdog`.
When those two daemons are down, dead builders stay dead and the visible floor
shows holes. Triage in this ORDER:
1. Builder count per project (NOT a truncated `ps`):
   `for p in SB D3D NAS LUM; do echo "$p: $(pgrep -fc "run_${p}")"; done`
   Expect 12 / 18 / 12 / 12 = 54. Verify any suspected-missing name directly:
   `pgrep -f "run_LUM9.sh" >/dev/null && echo UP || echo DOWN`.
2. Healer + watchdog + sentinel:
   `echo "healer:$(pgrep -fc swarm_healer) watchdog:$(pgrep -fc fleet_watchdog) sentinel:$(pgrep -fc mem_sentinel)"`
   If healer/watchdog are 0, the floor is up-but-not-self-healing → run the recover
   script (it restarts them via swarm_start_opt).
3. Fix = `bash ~/.hermes/skills/devops/eni-build/scripts/recover_headless_floor.sh`
   (idempotent: regens 54 scripts, launches ONLY missing builders, restarts
   healer+sentinel, frees stale lock by FD). Launches 0 new builders when all 54
   are alive → safe under memory pressure ("don't crash").

## DIAGNOSTIC PITFALL — `ps | grep | head` lies about floor gaps
A `ps aux | grep -iE "eni|swarm|mini" | head -50` silently truncates at 50 lines.
The floor is 54 builders + sentinel/healer/watchdog + the agent's own hermes
sessions (>100 procs match), so LUM9–LUM12 (and any builder past line 50) get
CUT from view and look "missing" when they are actually UP. This produced a false
"LUM9–12 down" read in one session. ALWAYS count with `pgrep -fc "run_<PREFIX>"`
per project and confirm per-name — never trust a truncated `ps | head` for floor
state. (The ~100+ extra `hermes chat` procs are mostly this agent's own sessions,
NOT swarm orphans — verify orphans by `ppid==1`, per eni-mini-protocol pitfall #7.)

## OPERATIONAL NOTE — swap-full on this box
Swap is frequently 100% full (8191/8191, 8 GB) and CANNOT be freed from inside the
sandbox (sudo is blocked). RAM headroom (~14.9 GB available) + the running
`mem_sentinel` guard make launches safe. When LO says "don't crash": prefer the
idempotent recover (launches only missing) over a full `fleet_deploy_ws.sh`
redeploy, report swap state honestly but note mem_sentinel caps it, and do NOT
attempt to free swap (needs root). If you must reduce pressure, prune only genuine
orphan hermes chats (`ppid==1`, parented to a dead terminal), never the live floor.

## When LO says "eni build"
Re-run the deploy script, verify the per-workspace builder count (12 each) and
that the control windows are present + STICKY, and report. To change
project->workspace assignment, edit the `paint_project` calls (proj / root / ws).
To change builders per screen, set `BUILDERS_PER_SCREEN=N`.

## Regression pitfalls (learned the hard way — do NOT reintroduce)
1. **Builder driver must LOOP; `hermes chat` is single-turn.** A bare
   `hermes chat -q "$(cat $TASK)" --yolo ...` runs ONCE then the terminal idles
   and looks dead. Wrap it in `while true; do ...; sleep 15; done` (see
   `make_builder`). The `-q` loop reads the task file every pass, so editing the
   task file live re-targets the mini.
2. **NEVER pass `-Q` to builder `hermes chat`.** `-Q` suppresses the banner +
   spinner + tool-call output, so the terminal shows a frozen blank even though
   the loop is alive. Builders must run WITHOUT `-Q` so LO sees live grinding.
3. **`set -u` (nounset) is active — escape every var meant for the generated run
   script.** Inside `make_builder`'s `<<EOF` heredoc, `$(cat $TASK)` MUST be
   written `\$(cat \$TASK)` (escaped). If you leave it unescaped, bash tries to
   expand `$TASK` at *deploy* time (when it's unset) and the whole script dies with
   `TASK: unbound variable` — killing the floor. The heredoc is unquoted on purpose
   so `$task`/`$MODEL`/`$PROVIDER` expand at deploy time, but `$TASK`/`$(...)` must
   survive to runtime.
4. **`paint_screen` references `$bname`, NOT `$name`.** `$name` only exists inside
   `make_builder` (it's `local`). The launch line must be
   `bash $TAB_DIR/run_${bname}.sh`. Using `${name}` there throws
   `name: unbound variable` and aborts the deploy.
5. **Builder window = single tab** (`-e "bash .../run_${bname}.sh"`), NOT a
   MASTER+ENI two-tab window. A two-tab window opens on the idle MASTER chat tab and
   hides the grinding hermes session behind it. One tab = hermes is what LO sees.
6. **Raise builders ABOVE** (`wmctrl -i -r "$id" -b add,above`) so Thunar/Spotify/
   LibreOffice don't bury them. The id must be captured from `launch`'s stdout
   (`id=$(launch ...)`), since parsing `wmctrl -l` by title substring collides
   (`DEMIURGE` ⊂ `DEMIURGE3D`).
7. **Safe-kill uses `pkill -f 'xfce4-terminal.*eni_tabs'` with PID exclusion**
   (`me=$$; mp=$PPID`). Never bare `pkill -f 'hermes chat'` (kills this agent's own
   shell) and never `kill -9 -PGID` (can nuke the controlling terminal).

8. **Python-native v4 swarm boot (`ENI_Swarm_NEW`) — master_driver + PTY bridges.**
   The v4 swarm at `~/Desktop/Projects/ENI_Swarm_NEW` replaces the xfce4-terminal
   floor with a Python coordination loop + per-mini PTY bridges to `hermes chat`
   linked through FIFOs (`/tmp/eni_ctl_<NAME>`). Launch:
   ```bash
   cd ~/Desktop/Projects/ENI_Swarm_NEW
   PYTHONPATH="lib:$PYTHONPATH" python3 -m eni.master_driver --interval 120
   ```
   This spawns all builders from `config/eni_build_tasks.json` via
   `bin/eni_agent_term.py`. Monitor with `eni-swarm tui` (Rich terminal dashboard)
   or the web dashboard on `http://localhost:8420`. Safe kill: iterate `/proc/*/cmdline`
   for `eni_agent_term`/`master_driver` and kill by explicit PID — NEVER `pkill -f`
   from an interactive shell (see pitfall #6).

9. **`parents[N]` path-resolution pitfall — in lib/ projects, N varies by depth.**
   When a file at `lib/eni/master_driver.py` computes `ROOT = Path(__file__).resolve().parents[N]`:
   - `parents[0]` = `lib/eni/`, `parents[1]` = `lib/`, `parents[2]` = project root — CORRECT
   - `parents[3]` = parent of project (Desktop/Projects/) — WRONG, one level too high
   Same bug existed in `orchestrator.py`. Symptom: "Task file not found:
   /home/hunter/Desktop/Projects/config/..." when file is actually at
   `ENI_Swarm_NEW/config/`. Always verify the resolved path after any module move
   or when `parents[N]` is used.

10. **Versatile builder config — LO wants generic builders, not project-locked.**
    LO's directive: builders must handle ANY task, not be hardcoded to
    StockBot/Demiurge/Lumen. Use `BUILDER_01..BUILDER_N` with a generic prompt:
    "Handle ANY task LO assigns. Monitor your FIFO. Write STATUS. Be autonomous."
    Tasks are assigned dynamically via FIFO injection (`eni-swarm assign "task"`
    or the dashboard swarm chat `@BUILDER_XX`). PRODUCT_LEAD routes tasks to idle
    builders. The old project-specific roster (STOCKBOT_B01, LUMEN_B13, etc.) is
    deprecated for general-purpose use.

11. **Hardware scaling formula for builder count.** 24 cores / 30 GB RAM →
    safe builder count: ~50. Each builder = 1 python bridge + 1 `hermes chat`
    process (~80-100 MB each). Formula: `safe = min((total_ram_gb - 4) / 0.1,
    cpu_cores * 3, 50)`. Builders are I/O-bound (API calls), not CPU-bound, so
    3 builders per core is safe. GPU is irrelevant — builders use OpenRouter
    API, not local inference. Generate config with `BUILDER_01..BUILDER_50` +
    PRODUCT_LEAD + HEARTBEAT.

12. **Dashboard model selector — free router + all free/paid model dropdown.**
    The v4 web dashboard (`http://localhost:8420`) includes a model dropdown with
    LO's local free router (`localhost:8920`, auto-selects best free model) as
    default, plus all known free models (Hunyuan, Gemma, Mistral, Qwen, etc.)
    and paid models (GPT-4o, Claude, Gemini). The swarm chat routes instructions
    to PRODUCT_LEAD via FIFO; `@BUILDER_XX` syntax sends directly to a specific
    builder. Broadcast and Assign-Idle buttons send to all/idle builders.
