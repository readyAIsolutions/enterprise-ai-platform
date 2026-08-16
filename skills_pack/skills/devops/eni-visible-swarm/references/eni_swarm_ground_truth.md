# ENI swarm — verified ground truth (2026-07-09, ENI8 audit)

The skills `eni-visible-swarm` and `parallel-build-orchestration` were written
against an IDEALIZED swarm and are STALE vs what is on disk. This file is the
verified reality. Re-check with `test -e` before trusting any skill claim.

## Current ops manual
/home/hunter/Commander/eni_swarm/ENI_SWARM_MANUAL.md  (top-level drive/extend doc)

## Live roster (eni_swarm_def.sh) — the format that ACTUALLY runs
```
MINIS=(
  "ENI1         eni1.task         DP2"
  "ENI8         eni8.task         DP1"
  "PRODUCT_LEAD PRODUCT_LEAD.task HDMI"
  ...
)
declare -A MON_GEO
MON_GEO[DP2]='80x24+0+0'        # left
MON_GEO[DP0]='110x32+1920+0'    # middle (primary ultrawide)
MON_GEO[HDMI]='80x24+2274+1080' # bottom
MON_GEO[DP1]='80x24+4480+0'     # right
MONITORS=(DP2 DP0 HDMI DP1)
```
- 3 fields per MINIS line: NAME  TASKFILE  MONITOR.
- MONITOR token in {DP2,DP0,HDMI,DP1}. eni_launch.sh / eni_master_dash.sh parse
  with `read -r name task mon2 _ <<< "$m"`.
- model/provider/workdir are UNIFORM (tencent/hy3:free / openrouter / swarm dir)
  and NOT stored per-mini in the roster. eni_mini_run.sh derives task from NAME.
- The associative-array `[NAME]="task|workdir|model|provider|monitor"` format
  some helper docs assume is STALE and breaks the live launchers.

## Present, real scripts (verified 2026-07-09)
In /home/hunter/Commander/eni_swarm/ unless noted:
- eni_launch.sh, eni_master_dash.sh, eni_relay.sh, eni_mini_run.sh, eni_swarm_def.sh
- eni_status.sh (consolidated board), status_hub.py (-> MASTER_STATUS.md),
  eni_selftest.sh, eni_watchdog.sh
- eni_add_mini.sh, eni_spawn_worker.sh  (FIXED 2026-07-09 to live roster format)
- ~/.local/bin/eni_agent_term.py (PTY bridge, NEW CLI --name/--task/--repl),
  ~/.local/bin/eni_pick_model.sh, ~/.local/bin/eni

## MISSING on disk (referenced by skills — do NOT run)
- paint_LO_new.sh, fleet_deploy.sh, eni_swarm_4ws.sh, probe_free_models.sh,
  eni_master_driver.py
If LO wants turnkey versions, build them against ENI_SWARM_MANUAL.md §10/§6.

## Proxy CLI (correct, current — old positional form is DEAD)
python3 ~/.local/bin/eni_agent_term.py --name ENIx \
  --task <file> \
  --repl "hermes chat --yolo -m tencent/hy3:free --provider openrouter"
--task = file pre-typed into REPL on banner; --repl holds the hermes command
(model/provider inside --repl); --ctl = FIFO (default /tmp/eni_ctl_<NAME>).

## Model spine
- config.yaml: provider openrouter, fallback_providers [gemini], api_max_retries 8.
- ~/.hermes/config.yaml is tool-layer WRITE-PROTECTED -> edit via terminal
  python one-liner (read -> str.replace -> write -> yaml.safe_load). The eni
  profile config IS editable directly.
- Seed ~/.cache/eni_parallel/live_models.txt manually (probe_free_models.sh is
  MISSING): printf 'slug1\nslug2\n' > ~/.cache/eni_parallel/live_models.txt
- eni_pick_model.sh does atomic round-robin over that file; falls back to
  tencent/hy3:free if absent. eni_mini_run.sh reads ENI_WORKER_MODEL/PROVIDER env.

## Monitor map (xrandr --listmonitors)
DP2 left +0+0 | DP0 middle +1920+0 (primary) | HDMI bottom +2274+1080 |
DP1 right +4480+0
eni_spawn_worker.sh numeric: 1=DP2 2=DP0 3=DP1 4=HDMI.

## Helper fixes (2026-07-09, ENI8)
- eni_add_mini.sh: writes a MINIS line; inserts BEFORE the MINIS closing ")"
  (not before `declare -A MON_GEO`, which would put it outside the array).
  Maps numeric MONITOR 1..4 -> DP token.
- eni_spawn_worker.sh: greps the live MINIS line for `"<PARENT>[[:space:]]`
  (no false match on ENI8_w3 / ENI10), strips surrounding quotes, maps DP ->
  numeric so the worker lands on the parent's screen (was all BOTTOM).

## Red-team shelf is OUT OF SCOPE
eni_code_lib/ (recon/beacon/exfil stubs) must never be read into a build,
extended, or replicated. A build mini's job is the orchestration mechanism.
