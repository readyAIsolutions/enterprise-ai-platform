# 4-Program Parallel-Build Swarm (one program per X11 workspace)

## Pattern
Assign each program its OWN X11 workspace; paint 12 builders + 1 heartbeat + 1 PL/master
per workspace across the 4 monitors.

  WS0 STOCKBOT    -> 12 builders (B01..B12) + heartbeat + PL/master
  WS1 DEMIURGE3D   -> 12 builders + heartbeat + PL/master
  WS2 DEMIURGE      -> 12 builders + heartbeat + PL/master
  WS3 LUMEN         -> 12 builders + heartbeat + PL/master

This is the PRODUCT-swarm variant of the 4-workspace layout. Unlike the ENI-herself
swarm (ENI1_wsN per workspace), here each WORKSPACE = ONE PROGRAM (12 builders of that
program), so 4 programs fill 4 workspaces. Known-good skeleton: `templates/paint_4programs.sh`.

## CRITICAL mechanics (all proven 2026-07-11)
- **`wmctrl -i -r <WINID> -t <ws>` for placement, NOT `wmctrl -s`.** `wmctrl -s N` switches
  the viewport but new xfce4-terminal windows still land on the launcher's current desktop
  -> clustering (all 4 programs pile on ws0/ws1, other workspaces empty). Launch each window,
  capture its WINID from `wmctrl -l` (`awk '{print $1}'`), then `wmctrl -i -r $WINID -t $WS`.
- **Zero-pad builder indices (B01..B12).** `grep -F "ENI:STOCKBOT_B1"` ALSO matches
  `..._B10`, so a title-substring placement moves the wrong window. Zero-pad so B01 != B10,
  and use `grep -F` (fixed-string) not regex.
- **OANDA/secret: bake the LITERAL value, don't `$(grep …)` it.** A generated run-script line
  `export TOK="$(grep '^TOK=' "$HOME/.env" | head -1 | cut -d= -f2-)"` nests a double-quote
  inside a double-quoted string -> bash `syntax error near unexpected token ')'` aborts the
  WHOLE launch loop (0 proxies, no error seen). Instead either (a) write the literal secret into
  the painter and `export OANDA_TOKEN="<LITERAL>"` so xfce4-terminal children INHERIT it through
  the process chain (run-scripts need not set it), or (b) write the literal into each run-script.
  NEVER use `$(...)` with nested quotes for a secret. NOTE: `write_file` mangles a `$VAR` ref in
  a generated script to a literal `***`, so the literal-value approach is the reliable one.
- **1s stagger between builder launches** softens the OpenRouter free-model 429 storm (48 builders
  hammering 4 free slugs). Without it most windows 429 and write nothing.
- **No `eni_agent_term.py --fifo`** -- that flag does not exist; passing it kills the proxy
  (0 proxies). Use `--name/--task/--repl` only.

## The painter is a LAUNCH SCRIPT -- it is NOT the swarm
`paint_4programs.sh` fires off the proxies + xfce4-terminals, prints "PAINT DONE", and EXITS.
The live swarm lives in INDEPENDENT processes: the `eni_agent_term.py` proxies and the
`xfce4-terminal` windows. Killing the launch script (or a stray re-run of it) does NOT kill the
swarm by itself -- UNLESS the script's own cleanup `pkill -f '/tmp/eni4p_tabs/[rm]'` runs and
pkills the run-script processes (the proxies are spawned under them). The proxies
(`eni_agent_term.py`) are launched with `nohup … &` and survive the run-script pkill, but a
second painter run that pkills + relaunches CAN clobber a healthy floor.

### Hardening (make re-runs safe)
- Wrap the whole painter in `flock -n /tmp/paint_4programs.lock` so two painters can't run
  concurrently (a stray delegated subagent re-running the script can't stomp the live floor).
- Make launch IDEMPOTENT: before launching a program's builders, check `wmctrl -l` for their
  titles; if they already exist, SKIP (don't pkill + relaunch). A re-run then tops up dead
  windows instead of nuking live ones. Provide a `FORCE=1` env to bypass and do a full relaunch.
- Keep TABDIR unique per swarm (`/tmp/eni4p_tabs`) so its pkill pattern never touches the
  ENI-herself swarm (`/tmp/eni_tabs`).

## Liveness counting -- DON'T use the `eni4p` grep artifact
`pgrep -c -f 'eni_agent_term.py'` is the true proxy count. A naive
`pgrep -af 'eni_agent_term.py' | grep -c 'eni4p'` returns a bogus number because the proxy
command lines reference `/tmp/eni_parallel/` (underscore), NOT the string "eni4p" -- so the
count collapses to ~2 even when 54 proxies are alive. Always count the proxy binary itself:

  pgrep -c -f 'eni_agent_term.py'   # true proxy count
  wmctrl -l | grep -c 'ENI:'        # true window count
  pgrep -c -f 'hermes chat'         # hermes sessions

## Stray delegated-subagent interference
A sibling subagent (delegated earlier) can independently edit `paint_4programs.sh` on disk and
run its OWN painter, producing "PAINT DONE" / "exit -15" background-completion alerts that look
alarming but are just leftover launch scripts finishing. They cannot harm the live swarm (proxies
are independent). Mitigation: flock + idempotent launch (above) + verify the on-disk script is the
known-good version (literal key, no `$(grep)`) after any such alert before trusting a relaunch.
A broken sibling run on an already-seated floor becomes a no-op with idempotency + flock.
