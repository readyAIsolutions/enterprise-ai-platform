---
name: hermes-visible-terminals
description: Use when the user expects to SEE live terminal windows (e.g. "open a Hermes terminal", "make these into terminals", "run it in a terminal I can watch", "where are the terminals?", "separate gnome terms black and white"). The Hermes CLI container SHARES the host X display and CAN paint real windows via a direct X client (xterm). gnome-terminal fails from the sandbox (D-Bus proxy), so use xterm. Also covers parallel delegate_task being invisible and tencent/hy3:free timing out big builds.
---

# Hermes visible terminals from inside the container

## Core finding (CORRECTED — do not repeat the old mistake)
The Hermes CLI container shares the host X display. It CAN paint real, visible
windows on the user's desktop. DO NOT conclude "the container can't paint X"
just because gnome-terminal didn't appear — that earlier conclusion was WRONG
and cost several wasted turns.

## Reality check — `hermes terminal` / `hermes container` are NOT subcommands
When the user says "open a Hermes terminal" or "another hermes terminal", that is PROSE
for a visible xterm window (below), NOT a `hermes terminal` CLI command. There is no such
subcommand — `hermes terminal --help` returns "invalid choice" (verified 2026-07-09).
The REAL way to get a visible, living Hermes agent window is the PTY bridge
`eni_agent_term.py` (a proxy that forks `hermes -p eni chat` inside a real PTY and
pre-types the task), or a plain `xterm` running `hermes chat` (see Working launch
pattern). Verified subcommand reality: real subs are `chat, profile, config, curator,
cron, skills, status, ...` (full list via `hermes --help`); the fake ones (`agent`,
`run`, `container`, `terminal`, `errors`) are invalid choices. Do NOT invent
`hermes agent run` / `hermes terminal` — they error out. (See devops/parallel-build
-orchestration and devops/eni-visible-swarm for the full REAL/FAKE table.)

What actually happens:
- `DISPLAY=:0.0` and `/tmp/.X11-unix/X0` exist; `xdpyinfo` reaches the X server.
- `gnome-terminal` launched from the container FAILS SILENTLY: modern gnome-terminal
  is a D-Bus client that sends a request to a running `gnome-terminal-server`.
  No server is reachable from the sandbox, so no window appears and the parent
  exits 0 — looking like success but showing nothing.
- `xterm` (and `uxterm`) is a DIRECT X client with no D-Bus dependency. It paints
  immediately. Use xterm for visible terminals.

## Diagnostic recipe (run BEFORE concluding X is unreachable)
See `references/x_visibility_recipe.md` for the exact commands. In short:
```bash
ls /tmp/.X11-unix/          # X0 socket present?
xauth list                  # MIT-MAGIC-COOKIE present?
xdpyinfo | head -3          # "name of display: :0.0" => X IS REACHABLE
```
If `xdpyinfo` prints the display name, the container can open windows. Verify
the windows actually mapped with `xwininfo -root -tree | grep -i <title>`
(NOT `xdotool search --class XTerm`, which often returns 0 even when mapped).

## Working launch pattern (xterm, black & white)
Use terminal(background=true) so the window persists after the tool call returns.
xterm stays open with `-hold`; end the command with `exec bash` so the user gets
a shell after the build finishes.
```bash
xterm -bg black -fg white -geometry 95x30+X+Y \
  -T "TITLE" -hold -e bash -c 'cd <dir> && <cmd>; echo DONE; exec bash'
```
- `-bg black -fg white` => black & white terminal (satisfies the B&W ask).
- `-geometry WxH+X+Y` => absolute X screen coords. Left monitor is x=0; the
  primary middle ultrawide is usually x=1920. Pick coordinates for the monitor
  you want (a 2x2 grid: +5+56, +765+56, +5+499, +765+499 works on a 3-mon setup).
- For a build that needs sudo (GPU tuning, driver install): the password prompt
  appears INSIDE the xterm window — the user types it there on the host.

## Parallel builds across programs
Launch N xterm windows, each running one program's build, in ONE message (batch
the terminal(background=true) calls). Each is independent and the user watches
all of them live. Combined with a `build_parallel.sh` that fires the program's
own self-tests concurrently, this gives a live pass/fail board per program.

## Fallback: gnome-terminal B&W profile look
If the user specifically wants the gnome-terminal saved BLACK & WHITE PROFILE
(not xterm), the container can't do it (D-Bus). Write a host-side launcher
`~/Desktop/launch_*.sh` using `gnome-terminal --profile=<id> ...` and tell the
user to run it from a REAL host terminal. Profile id for this box:
`b1dcc9dd-5262-4d8d-a863-c897e6d979b9` (#000 bg / #fff fg). This is the ONLY
case where the host-launcher approach is needed.

## xfce4-terminal paints from the container too (2026-07-09 correction)
Earlier this skill implied ONLY `xterm` paints from the container. That is now
KNOWN INCOMPLETE: `xfce4-terminal` ALSO paints to `:0.0` from the container (bare
`xfce4-terminal` and `dbus-launch xfce4-terminal` both work — the old "D-Bus
blocker" belief was FALSE, proven in `devops/eni-visible-swarm`). Since LO prefers
his black-and-white xfce4-terminal, prefer it over xterm when you want his exact
look:
  - ALWAYS pass `--disable-server` (xfce4-terminal is single-instance; without it
    every tab/launch merges into the first window and per-screen geometry is lost).
  - ALWAYS pass explicit `--geometry COLSxROWS+OX+OY` (`--maximize` is IGNORED by
    LO's host WM from the container, so windows come up tiny otherwise).
  - Launch DETACHED: `xfce4-terminal ... </dev/null >/dev/null 2>&1 & disown`.
  - Kill scope: `pkill -f 'eni_agent_term'` and `pkill -f '/tmp/eni_tabs/'` ONLY —
    never broad-`pkill xfce4-terminal` (spares LO's host terminal).
Keep `xterm` as the fallback for paint-testing (direct X client, no D-Bus), but it
is no longer the ONLY option. (See `devops/eni-visible-swarm` for the full recipe.)

## Other constraints (unchanged)
- `delegate_task` runs workers INVISIBLY and returns only a summary — it does NOT
  create visible windows. Max 3 concurrent children.
- On `tencent/hy3:free`, subagents TIME OUT (~600s / ~11 API calls) on big builds.
  Split the task or do it directly with file writes + terminal smokes.
- Foreground terminal commands may NOT use shell-level background wrappers
  (nohup/disown/setsid &). Use terminal(background=true) — this also keeps the
  xterm alive after the call returns.
- The container has NO root: sudo-only work (GPU driver/OD tuning) must happen in
  the xterm window on the host, where the user can authenticate.

## Pattern (this user)
Families (2x2 grid of xterm B&W windows): GPU tune+check (sudo), Lumen wallpaper,
DEMIURGE stock-bot (build_parallel.sh + run_walk_forward.sh), DEMIURGE-3D
estimator. Files: ~/Desktop/launch_demiurge_terminals.sh (gnome-terminal fallback),
~/Commander/demiurge_scaffold/{build_parallel.sh, run_walk_forward.sh}.
