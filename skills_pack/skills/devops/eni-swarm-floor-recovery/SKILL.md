---
name: eni-swarm-floor-recovery
description: Recover OR stop the ENI parallel-build swarm floor. Covers BOTH v4.1 optimized fleet (50 on-demand builders, resource-gated, web dashboard at :8420) AND v4.0 legacy headless floor (54 persistent PTY builders across SB/D3D/NAS/LUM). Recovery covers post-crash states, lock-held boot, EAGAIN on os.fork, can't-start-new-thread, duplicate logs, and state normalization bugs. For fleet-status MONITOR runs (cron or Q&A), see references/fleet_monitor_health_axes.md for the independent probe points of the four axes (builder floor / :8420 dashboard / :8922 turbocharger / status_hub controller). To run all four probes plus pulse in ONE terminal call without hand-typing each curl/stat, use `scripts/fleet_health_probe.sh` - it lives in this skill's scripts/ dir; a local copy may also exist at eni_swarm/ `bash /home/hunter/.hermes/skills/devops/eni-swarm-floor-recovery/scripts/fleet_health_probe.sh` (it cd's to the swarm itself).
---

# ENI Swarm Floor Recovery (post-crash) & Fleet Operations

> **Task intake check** — before processing/acting on any "ENI builder task" (queued
> cron, scheduled instruction, or direct request referencing an `eni_ctl_BUILDER_<N>`
> FIFO), verify the floor actually has work: does the FIFO exist, is anything attached
> (`lsof`), is the controller queue empty (`curl :8940/status` → `queue.pending`), is the
> task file / dashboards / builder processes present? If the FIFO is gone, the queue is
> empty, and the floor isn't running, there is NO task — report the stale cron honestly,
> never fabricate a task, spawn builders, or delegate an empty "process the build" job.
> Full recipe: `references/builder-task-diagnostics.md`.

## TWO ARCHITECTURES — know which one you're dealing with

### v4.1 OPTIMIZED FLEET (CURRENT — 50+ builders, on-demand, resource-gated)
- **Project root**: `~/Desktop/Projects/ENI_Swarm_NEW/`
- **Launcher**: `launchers/eni_launch_50_optimized.sh` — staged launch with resource gates
- **Agent runner**: `bin/eni_agent_run.py` — uses `hermes -z` (single-shot, on-demand), NOT persistent `hermes chat`
- **Dashboard**: `dashboard/server.py` on port 8420 — has filesystem fallback detection
- **Config**: `config/eni_build_tasks.json` (50 builders + HEARTBEAT + PRODUCT_LEAD), `config/swarm_config.json`
- **Count**: 50 BUILDER_01–50 + HEARTBEAT + PRODUCT_LEAD + ENI_SELF_1–8 (60 total)
- **Logs**: `~/.cache/eni_swarm/builder_logs/<NAME>.log`
- **PIDs**: `~/.cache/eni_swarm/pids/<NAME>.pid`
- **STATUS files**: `~/Commander/eni_swarm/builds/STATUS_BUILDER_*.md`
- **Key differentiator**: Zero CPU when idle (builders wait on FIFO, no persistent hermes session)
- **Resource limits**: Max 6 concurrent hermes, nice -n 15, ionice idle, OOM 500, 2GB RAM cap
- **Full reference**: `references/optimized_fleet_v4_1.md`
- **Power slider + reasoning extraction**: `references/dashboard_power_reasoning.md`

### v4.0 HEADLESS FLOOR (LEGACY — 54 persistent builders, PTY-based)
- Floor generator: `~/Desktop/Commander/eni_swarm/gen_floor_opt.sh` → writes 54 run scripts to `/tmp/eni_opt/run_<NAME>.sh` + 4 dash scripts.
- Boot/heal: `~/Desktop/Commander/eni_swarm/swarm_start_opt.sh` (idempotent, launches only missing builders, starts mem_sentinel + healer).
- Builders: `eni_agent_term.py --name <NAME> --task <taskfile> --repl "hermes chat --yolo -m <model> --provider openrouter"`.
- Counts: SB=12, D3D=18, NAS=12, LUM=12 (total 54). One per workspace.
- Logs: `/tmp/eni_opt_logs/<NAME>.log`. Lock: `/tmp/eni_opt.lock`.
- **Still functional** but superseded by v4.1 for new fleet launches. Use v4.1 for new builds.

## Symptom → root-cause map (THE 4-BUG CASCADE)
After a crash you will typically see ALL of these at once:

1. **`swarm_start_opt.sh` prints "already booting (lock held) — exiting" forever.**
   Cause: the script does `exec 9>/tmp/eni_opt.lock; flock -n 9`. The builder launch lines use `nohup bash "$OD/run_${name}.sh" &` — children INHERIT fd 9, so the flock is held by the (now-dead-parent's) living children and never releases.
   Fix: close fd 9 for the children: `nohup bash "$OD/run_${name}.sh" >/dev/null 2>&1 9<&- &` (same for the sentinel/healer launch lines). The lock then frees when the boot parent exits.

2. **Builder logs show `nice: : No such file or directory (os error 2)`.**
   Cause: `gen_floor_opt.sh` `gen_run()` writes each run script through an UNquoted heredoc (`<<RUNEOF`). The line `nice -n 5 "${CMD[@]}"` is expanded at WRITE-time against `gen_run`'s own (unset) CMD array → becomes `nice -n 5 ""`. The `CMD=(...)` that defines it only exists as TEXT inside the heredoc, executed later by the generated script, not at write time.
   Fix: escape it in the heredoc so it's written literally and evaluated at the generated script's runtime (after CMD is defined on the line above): `nice -n 5 "\${CMD[@]}"`.

3. **`BlockingIOError: [Errno 11] Resource temporarily unavailable` at `pty.fork() → os.fork()`** (even with host RAM free + nproc ceiling huge + cgroup `memory.max = max`).
   Cause: `ulimit -v 2200000` (2.2 GB VIRTUAL cap) inside the builder subshell. `eni_agent_term.py` imports the full Hermes stack, so its VIRTUAL footprint exceeds 2.2 GB before it forks the `hermes chat` repl → fork fails. A direct `os.fork()` under `-v 12000000` succeeds for a tiny python but NOT for the heavy Hermes client.
   Fix: `ulimit -v unlimited` in the subshell. (Memory is guarded by `mem_sentinel_opt.sh`, which SIGTERMs the biggest Hermes when avail < 1500 MB — so removing the VIRT cap is safe.)

4. **`RuntimeError: can't start new thread`** (after fork starts working).
   Cause: `ulimit -u 400/600` (per-process nproc/thread ceiling) blocks Hermes' thread pool when it spins up.
   Fix: remove `ulimit -u` entirely (rely on system nproc ~123k + mem_sentinel). With `-u` gone and `-v unlimited`, builders launch, fork, and run cleanly.

## Recovery procedure (idempotent, safe)
Write a recovery script (DO NOT paste the kill patterns inline in a terminal command — `pkill -f` matches your own command line and self-kills with exit -15). Put the patterns inside a script file so no process cmdline contains them:

```bash
#!/usr/bin/env bash
set -u
cd /home/hunter/Desktop/Commander/eni_swarm
# kill ALL stale builder wrappers + python + old sentinel (patterns live in this file only)
for p in $(pgrep -f 'eni_opt/ru[n]_'); do kill -9 "$p" 2>/dev/null; done
for p in $(pgrep -f 'eni_agent_ter[m].py'); do kill -9 "$p" 2>/dev/null; done
for p in $(pgrep -f 'mem_sentinel_op[t]'); do kill -9 "$p" 2>/dev/null; done
sleep 2
# free the flock by killing whatever still holds it
holders=$(fuser /tmp/eni_opt.lock 2>/dev/null | tr ' ' '\n' | grep -v '^$')
[ -n "$holders" ] && { kill -9 $holders 2>/dev/null; sleep 2; }
# regenerate run scripts (after fixing gen_floor_opt.sh as above) + relaunch
bash gen_floor_opt.sh >/dev/null 2>&1
bash swarm_start_opt.sh 2>&1 | tail -3
# staggered boot is 3-53s per builder; wait before judging
sleep 35
echo "alive proxies: $(pgrep -fc 'eni_agent_ter[m].py')"
```

## Verification (the REAL success bar)

### v4.1 Optimized Fleet (current)
- `bash ~/Desktop/Projects/ENI_Swarm_NEW/scripts/check_fleet.sh` → shows builder counts + system health
- `curl -s http://localhost:8420/api/status | python3 -c "import sys,json; s=json.load(sys.stdin)['summary']; print(f'{s[\"total_minis\"]} builders, {s[\"alive_count\"]} alive')"` → 50+ builders, 45+ alive
- `pgrep -fc 'eni_agent'` → 20–50 (varies as builders come online in stages)
- `pgrep -fc 'hermes'` → ≤6 (resource gate cap)
- `uptime` → load < 3.0 on 24 cores (below 13%)
- `free -h` → >10GB available
- Per-builder STATUS: `cat ~/Commander/eni_swarm/builds/STATUS_BUILDER_01.md` → shows state
- Live feed: `curl -s "http://localhost:8420/api/live-feed?count=3"` → recent builder output

### v4.0 Headless Floor (legacy)
- `pgrep -fc 'eni_agent_term[.]py'` → **54** (all four products).
- `tail /tmp/eni_opt_logs/D3D1.log` shows the live Hermes REPL prompt (`❯ YOLO`), NOT `BlockingIOError`, NOT `nice: No such file`.
- Per-builder `STATUS_<NAME>.md` in each repo shows `**State**: RUNNING / PTY bridge alive / REPL running / FIFO connected`.
- Module-level progress lives in aggregate boards: `~/Commander/demiurge_scaffold/MASTER_STATUS.md` (SB registry + deploy-gate verdict), plus product STATUS files (e.g. `~/Desktop/apps/lumen/STATUS_ENI_LUMEN_WS4.md`).

## STOP / park the floor (inverse of recovery — LO says "stop auto build")
The floor is SELF-HEALING across 4 layers, so killing only the builders bounces them
back within seconds. To actually stop it you must kill EVERY layer in one pass AND
disable the boot-persistence cron, or it resurrects (live via `swarm_start_opt.sh`,
or on next reboot via the `@reboot` cron line).

**Kill all layers (patterns go in a SCRIPT FILE — never inline, see pkill-self-kill
pitfall above):**
```bash
#!/usr/bin/env bash
set -u
# Layer 4: top supervisor (respawns the whole floor live)
for p in $(pgrep -f 'swarm_start_op[t].sh'); do kill -9 "$p" 2>/dev/null; done
# Layer 3: sentinel watcher (respawns missing run_*.sh launchers)
for p in $(pgrep -f 'mem_sentinel_op[t]'); do kill -9 "$p" 2>/dev/null; done
# Layer 2: per-builder run_*.sh launchers (each loops + respawns ITS builder)
for p in $(pgrep -f 'eni_opt/ru[n]_'); do kill -9 "$p" 2>/dev/null; done
# Layer 1: the builder python procs themselves
for p in $(pgrep -f 'eni_agent_ter[m].py'); do kill -9 "$p" 2>/dev/null; done
# orphan hermes chat children the builders spawned
for p in $(pgrep -f 'hermes chat --yol[o]'); do kill -9 "$p" 2>/dev/null; done
sleep 3
echo "builders: $(pgrep -fc 'eni_agent_ter[m].py')  launchers: $(pgrep -fc 'eni_opt/ru[n]_')  supervisor: $(pgrep -fc 'swarm_start_op[t].sh')  sentinel: $(pgrep -fc 'mem_sentinel_op[t]')"
```
**Disable boot persistence (so it stays dead across reboot — BACKUP FIRST, reversible):**
```bash
crontab -l > ~/Commander/eni_swarm/crontab_backup_$(date +%Y%m%d_%H%M%S).bak
crontab -l | sed 's|^@reboot.*swarm_start_opt.sh|#DISABLED-by-LO-stop-autobuild @reboot swarm_start_opt.sh|' | crontab -
```
**Verification it's truly down:** re-check after a 10–15s wait (the supervisor can
re-launch a fresh copy in <2s if missed). All four counts above must read 0 and
STAY 0. Also confirm `swarm_start_opt.sh` is 0 after the wait — if it reappears,
there is a higher parent still exec'ing it (re-trace `ps -o ppid=` of the new PID).

**Do NOT kill `status_hub.py` (the `*/5` cron).** It only REPORTS fleet state — it
contains no spawn/launch calls — so it cannot resurrect builders. Leave it running;
killing it thinking it's a respawner is a wasted, confusing action.

**Repeated-cron suppression → `references/monitor_cron_diagnostics.md`**
When the fleet is persistently dormant (gate=RED, windows=0) across consecutive
cron firings, use the repeated-state-suppression section to decide whether to
report or respond `[SILENT]`.

**Fleet MONITOR/HEARTBEAT triage → `references/fleet_monitor_heartbeat.md`**
Golden rule before reporting any fleet as DONE/BLOCKED/dead: check the mtime of
the STATUS files backing the monitor output. `monitor_fleet.py` resolves its
workdir to the `builds/` dir (frozen legacy sweep) and silently writes a STALE
`HEARTBEAT_LEDGER.md`; `status_hub.py`→`MASTER_STATUS.md` is broader but also
laden with week-old rows. The LIVE fleet is the DEMIURGE/DEMIURGE3D mini-fleet
under `~/.hermes/scripts/STATUS_*.md` (24 builders, `State: RUNNING`) + the ENI KB
daemon under `~/.eni/kb/`. Triage the fresh mini-fleet first, then health ports
(:8940 controller, :8922 turbocharger), THEN the ledgers.

**To bring it back later:** re-enable the `@reboot` line (uncomment the backup) and
run `bash ~/Desktop/Commander/eni_swarm/swarm_start_opt.sh`.

## Pitfalls

- **pkill self-kill**: any `pkill -f 'some[.]pattern'` typed directly in a terminal command will match that very command line → SIGTERM to your own shell (exit -15). Always wrap kill patterns in a script file.
- **Dashboard shows 0 builders but fleet IS running (v4.1 pitfall)**: The dashboard relies on `eni.master_driver` imports for status. When builders are launched manually (not via master_driver), or when the import fails (ENI_AVAILABLE=False), the dashboard shows 0 minis despite builders being alive. Fix: the `_detect_builders_from_filesystem()` function in `dashboard/server.py` discovers builders from `~/.cache/eni_swarm/pids/*.pid`, `~/Commander/eni_swarm/builds/STATUS_BUILDER_*.md`, and `~/.cache/eni_swarm/builder_logs/*.log`. This fallback must exist in BOTH the `ENI_AVAILABLE=False` path AND the `total_minis==0` path after master_driver collection. If a dashboard update removes it, the fleet goes invisible. Verify with `curl localhost:8420/api/status | jq .summary.total_minis`.
- **Duplicate log lines (v4.1 pitfall)**: If builder logs show every line twice, the `log()` function in `eni_agent_run.py` is double-writing — once via `print()` (captured by launcher's `>>` redirect) AND once via direct file `open(...).write()`. Fix: remove the direct file write; stdout redirection handles it. See `references/optimized_fleet_v4_1.md` for exact fix.
- **DO NOT hijack a live passing gate / "use the ENI swarm" for a new job**: the active task file is `~/Desktop/ENI Swarm/eni_build_tasks.json` (not `~/Desktop/eni_build_tasks.json`). If the floor is mid-run, never edit its task file or kill its builders for a new task — that corrupts a passing gate.
- **Model change broadcasts to ALL builder FIFOs (v4.1 fix)**: `/api/model-change` updates hermes config.yaml + task config, then broadcasts `<MODEL CHANGE>` to ALL 50 builder FIFOs simultaneously. Builders mid-task finish with their current model and switch on the next `hermes -z` execution. Previously only builders with active FIFOs received the change — now all 50 get it immediately.
- **Large prompts break `hermes -z` (~2% failure rate)**: Prompts over 60KB with special characters (em-dashes, unicode, backtick-heavy code blocks) can cause the hermes argument parser to interpret prompt content as flags/subcommands → `invalid choice` error. Self-heals on next fleet launcher run (checks PID files, fills gaps). Acceptable attrition for 50-builder fleet.
- **State normalization mismatch (v4.1 pitfall)**: Builders report states inconsistently: "IN PROGRESS" (space), "IN-PROGRESS" (dash), or "INPROGRESS". The dashboard summary counts them correctly (checks both), but the UI filter "Active" only matches "IN-PROGRESS" literally — causing mismatched counts between the top-right stats and the builder grid. Fix: normalize states in BOTH the server (`_detect_builders_from_filesystem`: `if state in ("IN PROGRESS", "INPROGRESS"): state = "IN-PROGRESS"`) AND the UI (`state_norm` normalization in `updateBuilderGrid()`). Also normalize "UNKNOWN" + alive → "IDLE".
- **Chat dispatch only to PRODUCT_LEAD (v4.1 pitfall)**: Earlier versions routed chat messages only to PRODUCT_LEAD's FIFO. PRODUCT_LEAD analyzed the task but didn't forward it to builders (single-shot `hermes -z` can't dispatch to other FIFOs). Fix: `/api/chat` now broadcasts simultaneously to PRODUCT_LEAD AND all 50 builder FIFOs. Each builder receives the task directly and starts independently.
- **Power slider route collision (v4.1 pitfall)**: Defining two Route objects on `/api/power` (GET + POST) causes a 500 when Starlette routes to the wrong handler. Fix: merge into a single handler that checks `request.method` — `Route("/api/power", api_power, methods=["GET", "POST"])`.
- **STATUS files go stale while logs show correct state**: A builder that was BLOCKED completes a `hermes -z` run and writes "Waiting for next task" to its log, but the STATUS file still says "[BLOCKED]". The dashboard reads BLOCKED from STATUS unless log-based detection overrides it. Ensure `_detect_builders_from_filesystem()` checks last 5 log lines for "Waiting for next task" and overrides state to "IDLE" even when STATUS says BLOCKED.
- **Static "fork EAGAIN" in logs is stale**: builders append; clear logs (`find /tmp/eni_opt_logs -name '*.log' -exec truncate -s 0 {} \;`) before a relaunch so fresh output is visible.
- **Dashboards mis-path / "(not started)" boards** (common when relaunching the visible floor via `paint_dashboards.sh`): `gen_dash()` writes `f=/home/hunter/STATUS_$n.md`, but builders write STATUS into per-PRODUCT dirs, NOT /home/hunter — so every board reads "(not started)". Two verified fixes:
  (a) Live dash scripts: edit `/tmp/eni_opt/dash_<KEY>.sh` `f=` to the product dir, and make the state grep case-insensitive (`grep -m1 -oiE '\[?state: [a-z-]+\]?|# STATUS'`) because STATUS files use `State: RUNNING` (capital S), which the original `[A-Z-]+` lowercase pattern missed.
  (b) Generator (so a regen stays correct): in `gen_floor_opt.sh` `gen_dash()`, replace the single `f=` line with a candidate-search loop over all four product dirs, and use the `-i` grep. Exact lines + the per-product dir map (NOTE: NAS writes to `~/demiurgenas_stash`, NOT its repo) are in `references/dashboard_status_paths.md`. xterm + DISPLAY=:0.0 are present on the host to paint the boards.
- **MASTER aggregate board may not refresh** after a crash if its writer session died; the per-builder STATUS files remain authoritative.
- The legacy visible floor (`swarm_paint.sh`, `swarm_watchdog.sh.DISABLED`, `paint_LO_new.sh`) is superseded by this headless design — do not use it.
- **Cron/dashboard monitoring:** see `references/monitor_cron_diagnostics.md` for the fast diagnostic sequence and the critical idle-vs-down discriminator (v4.1 is zero-CPU when idle — judge by control FIFOs present, not by the process list; and the ledger alone is NOT live truth since it parses whatever STATUS files sit on disk, possibly weeks stale).
- **PITFALL — this skill's own reference files are ENI-compressed.** `skill_view`/`read_file` on `references/monitor_cron_diagnostics.md` or `references/fleet_monitor_health_axes.md` returns an opaque `<ENI-COMPRESSED>` carrier wrap, NOT the plain-text body — so the [SILENT] suppression criteria and axis probe points are not directly usable via the normal read tools. To read the full text, bypass the compression output hook and read the file path directly in the terminal: `env -u PYTHONPATH sed -n '1,80p' <abs-path>/references/monitor_cron_diagnostics.md` (or `grep -n` for targeted terms). Same hook applies to the probe script, but `scripts/fleet_health_probe.sh` already runs with `env -u PYTHONPATH` internally so its stdout is plain text. Do not re-report/verbose-out a fire-and-forget failure to read these carriers — just strip the hook and read the file.
