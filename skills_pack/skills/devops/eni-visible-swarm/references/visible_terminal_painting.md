# Visible Terminal Painting: Container vs Host (CORRECTED 2026-07-09)

LO wants to SEE build terminals on his X11 monitors. The Hermes agent runs INSIDE a
container that shares `DISPLAY :0.0` with the host.

## The boundary (REVISED — xfce4-terminal DOES paint)
- `DISPLAY :0.0` is reachable from the container (`xdpyinfo -display :0.0` succeeds).
- `xfce4-terminal` DOES launch from the container and paint to :0.0 — both bare
  `xfce4-terminal` and `dbus-launch xfce4-terminal` were verified to paint this session.
  The old "D-Bus blocker kills it" belief was FALSE. The real failure modes are
  `--maximize` being ignored by the host WM (use `--geometry`) and the single-instance
  server merging tabs (use `--disable-server`). See `references/xfce4_terminal_x11.md`
  for the full recipe.
- `xterm` also paints on :0.0 from the container (direct X client, no D-Bus) but needs
  the host X auth cookie in the container's `~/.Xauthority` (see the X-PAINT FAILURE
  pitfall in SKILL.md).

## Rule
- To paint visible terminals FROM the agent (container): use `xfce4-terminal --disable-server
  --geometry ...` directly — no host-side handoff needed. Each screen = one window with tabs.
- For a styled look you can still hand LO a HOST-side xfce4-terminal launcher, but it is
  no longer REQUIRED to get xfce4-terminal glass from the container.

## Proof a window is real
1. Launch background=true, then poll `pgrep -af xfce4-terminal | grep -i <TITLE>`.
2. For a mini, confirm it booted: check the STATUS file it should write
   (`cat ~/Commander/eni_swarm/STATUS_HEARTBEAT.md`) — a real timestamped line means the
   chat came up (a free-model cold start can take 1-3 min before the first line).
3. Geometry: MIDDLE (DisplayPort-0, 2560x1080) `260x54+1920+0`; side screens (1920-wide)
   `200x54+OX+OY` with origins LEFT +0+0, RIGHT +4480+0, BOTTOM +2274+1080.

## Launching a chat window — the WRONG and RIGHT way
- WRONG: `xfce4-terminal ... -e 'hermes chat MASTER.md --yolo'` (positional prompt file
  is not a valid `hermes chat` arg; hermes exits and the terminal closes instantly). NOTE:
  `hermes errors` is NOT a subcommand — this means hermes errors out, not a `hermes errors` command.
- RIGHT: load prompts through the proxy (NEW required-named-arg CLI, 2026-07-09 —
  the old `@task workdir` positional form FAILS with "arguments are required: --name"):
  `python3 ~/.local/bin/eni_agent_term.py --name <NAME> --task <dir>/task_X.txt --repl "hermes chat --yolo -m <model> --provider openrouter"`
  (`--name` is required and becomes the CTL FIFO `/tmp/eni_ctl_<NAME>`; `--task` is the
  prompt file pre-typed into the pty on the banner; the FULL `hermes chat ...` command
  lives INSIDE `--repl` now, NOT as proxy flags.)
