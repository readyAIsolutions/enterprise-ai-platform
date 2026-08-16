# Product-Aware Swarm Floor (canonical design, 2026-07-11)

Converts the single-workstream ENI swarm into **FOUR programs, ONE PER X11 WORKSPACE**,
each with its own master chat + a live BOOT/monitor terminal + N builder viewers.

## The registry — `swarm_products.cfg` (edit THIS, never the scripts)
Array index = workspace index (0..3). Keep keys SHORT + NON-PREFIXING
(one key must never be a prefix of another, or `builder_ws()` mis-routes):

```bash
PRODUCT_KEYS=(   SB    D3D    DEM    LUM   )
PRODUCT_LABEL=(  "STOCK BOT" "DEMIURGE 3D" "DEMIURGE" "LUMEN" )
PRODUCT_WS=(     0     1       2       3    )
PRODUCT_REPO=(   ~/Commander/demiurge_scaffold \
                 ~/Desktop/demiurge-3d \
                 ~/Commander/demiurge_scaffold \
                 ~/Desktop/apps/lumen )
PRODUCT_MODEL=(  "tencent/hy3:free" "qwen/qwen3-coder:free" "tencent/hy3:free" "qwen/qwen3-coder:free" )
PRODUCT_BUILDERS=( 3 3 3 3 )   # builders PER product (sum=12 here; raise if RAM allows)
PRODUCT_STATUS=( ~/Commander/demiurge_scaffold/STATUS_PL_STOCKBOT.md \
                 ~/Desktop/demiurge-3d/STATUS_DEMIURGE3D_PL.md \
                 ~/Commander/demiurge_scaffold/STATUS_PL_DEMIURGE.md \
                 ~/Desktop/apps/lumen/STATUS_LUMEN_PL.md )
PRODUCT_RUN=( "" "" "" "" )    # optional real boot cmd; "" = monitor-only (safe)
```

Builder names become `<KEY><i>` (SB1..SB3, D3D1.., DEM1.., LUM1..); each writes
`STATUS_<KEY><i>.md`. The 64 legacy `task_ENI*.txt` / `task_DEMIURGE*` files are NOT
booted by this design (new names only).

## Orchestrator skeleton (`swarm_watchdog.sh`)
1. `wait_for_x` (xrandr + wmctrl, 120x5s) — never race X.
2. `gen_run_scripts.sh` regenerates `/tmp/eni_tabs/*` (and `rm -f` stale
   `run_ENI*`/`heart_WS*`/`master_WS*` first — see pitfall below).
3. Paint ONCE: for each product, spawn (a) master+heartbeat overlay (top strip,
   `heart_<KEY>.sh`+`master_<KEY>.sh`), (b) BOOT/monitor window
   (`launch_<KEY>.sh` tails `PRODUCT_STATUS`), (c) N builder viewers via
   `spawn_window` (launch-then-`wmctrl -i -r <id> -t <ws>` to pin the workspace).
4. Self-heal every 30s by REAL PID (`kill -0` on tracked `VPID`/`MPID`/`LPID`) +
   `pgrep -f 'eni_agent_term.py --name <name> '` for headless builders.
   NEVER grep window titles (xfce4-terminal `--title` doesn't stick → runaway OOM).

## `builder_ws()` (prefix match — the trap)
```bash
builder_ws(){ local name="$1"
  for pi in "${!PRODUCT_KEYS[@]}"; do k=${PRODUCT_KEYS[pi]}
    [[ "$name" == "${k}"* ]] && { echo "${PRODUCT_WS[pi]}"; return; }; done
  echo 0; }
```
DEM ("DEMIURGE") is a prefix of D3D ("DEMIURGE3D") → would mis-route `DEMIURGE31` to DEM.
Use SB/D3D/DEM/LUM. Never make a key a prefix of another.

## Stale-script cleanup (silent ghost-builder bug)
The OLD design wrote `run_ENI*.sh` / `heart_WS*.sh` / `master_WS*.sh`. After a redesign
those filenames are NOT regenerated, so they linger and an old watchdog could boot
ghost ENI builders (OOM). `gen_run_scripts.sh` must `rm -f` them at the top.

## Verification recipe (no X needed — static checks)
```bash
cd ~/Desktop/Commander/eni_swarm
for f in swarm_products.cfg gen_run_scripts.sh swarm_lib.sh swarm_watchdog.sh; do
  bash -n "$f" || echo "SYNTAX FAIL $f"; done
bash gen_run_scripts.sh >/dev/null 2>&1
ls /tmp/eni_tabs | grep -E 'run_ENI|heart_WS|master_WS' && echo "STALE SCRIPTS PRESENT" || echo "clean"
source swarm_products.cfg
for pi in "${!PRODUCT_KEYS[@]}"; do key=${PRODUCT_KEYS[pi]}; nb=${PRODUCT_BUILDERS[pi]}
  for ((i=1;i<=nb;i++)); do printf '%s->ws%s ' "${key}${i}" "${PRODUCT_WS[pi]}"; done; done; echo
grep -c 'tail -f /tmp/eni_logs' swarm_watchdog.sh | grep -q '^0$' && echo "tail -F OK" || echo "tail -f STILL PRESENT"
```
A runnable version ships as `scripts/verify_swarm_floor.sh`.

## Boot (the only manual step is sudo autologin)
```
sudo bash ~/setup_autologin.sh      # LightDM autologin (without it X never starts)
reboot                              # autostart + @reboot cron fire the floor
# or, X already up:
pkill -f swarm_watchdog; sleep 1; setsid bash ~/Desktop/Commander/eni_swarm/swarm_start.sh
```

## LUMEN leash
Builders are CODE-ONLY. `launch_LUM.sh` only monitors `STATUS_PL_LUMEN.md`; it does NOT
start the app. After boot: `pgrep -af 'python -m lumen[^-.]'` must be empty.

## Support files added to this skill (2026-07-11)
- `templates/swarm_products.cfg` — known-good starter registry (copy to
  `~/Desktop/Commander/eni_swarm/swarm_products.cfg` and edit).
- `scripts/verify_swarm_floor.sh` — runnable static pre-boot check:
  `bash scripts/verify_swarm_floor.sh` → PASS/FAIL board with evidence.
  Run it after ANY edit to the registry or swarm scripts, BEFORE booting on X.
- This file (`references/swarm_products_floor.md`) — full design + orchestrator
  skeleton + boot/verify recipe.

## Correction to SKILL.md (could not be inlined — SKILL.md is at the 100k hard cap)
The 'FLOOR LAYOUT SPEC — FINAL' bullet in SKILL.md still describes the OLD
64-builder `ENI1–64` per-workspace mapping. That is **HISTORICAL** — superseded by
the **PRODUCT-AWARE REDESIGN** note: the current canonical floor = 12 builders
`SB / D3D / DEM / LUM` driven by `swarm_products.cfg`, NOT 64 `ENI1–64`. When the
curator next edits SKILL.md, that bullet should be deleted/redirected here.
Also: the entire Pitfalls wall (lines ~376–494) should be moved into `references/`
to bring SKILL.md under the 100k limit and match the class-level shape.
