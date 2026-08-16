# xfce4-terminal paints from the Hermes container (CORRECTED 2026-07-09)

Supersedes the stale "D-Bus blocker" belief in `visible_terminal_painting.md`.
xfce4-terminal DOES paint to DISPLAY :0.0 from the container — both bare and via
`dbus-launch xfce4-terminal`. The prior failure was misdiagnosed as a D-Bus problem;
it was actually WM + single-instance-server behavior. Verified empirically this session:
painted LEFT/RIGHT/BOTTOM as independent windows with 4 tabs each, MIDDLE clean, 13
hermes proxies live, LO's host xfce4-terminal untouched.

## The two real gotchas
- `--maximize` is SILENTLY IGNORED by LO's host WM when the terminal is launched from
  the container. Windows come up tiny (~618x138). Fix: explicit
  `--geometry COLSxROWS+OX+OY`. Verified COLS=200 for 1920-wide side screens, 260 for
  the 2560-wide MIDDLE, ROWS=54 fills each monitor.
- xfce4-terminal is a SINGLE-INSTANCE SERVER. Without `--disable-server`, every `--tab` /
  launch attaches to the FIRST open window and per-screen `--geometry` is ignored — you
  get all tabs merged into one window. Fix: ALWAYS pass `--disable-server` so each screen
  gets its own independent window with tabs inside.

## Proven per-screen command (one window + 4 tabs)
```
xfce4-terminal --disable-server \
  --title "ENI:ENI1" -e bash /tmp/eni_tabs/run_ENI1.sh \
  --tab --title "ENI:ENI2" -e bash /tmp/eni_tabs/run_ENI2.sh \
  --tab --title "ENI:ENI3" -e bash /tmp/eni_tabs/run_ENI3.sh \
  --tab --title "ENI:ENI4" -e bash /tmp/eni_tabs/run_ENI4.sh \
  --geometry 200x54+0+0
```
- MIDDLE / DisplayPort-0 (clean master, NO tabs): `--geometry 260x54+1920+0`, single
  window running a live heartbeat command.
- Side screens: `--geometry 200x54+OX+OY` with origins LEFT +0+0, RIGHT +4480+0,
  BOTTOM +2274+1080 (from `xrandr --listmonitors`).
- Each `run_ENIx.sh`:
  `cd wd; export PYTHONPATH="$(ls -d /home/hunter/.local/lib/python3.*/site-packages 2>/dev/null | sort -V | tail -1)"; export PATH="$HOME/.local/bin:$PATH"; while true; do python3 ~/.local/bin/eni_agent_term.py --name ENIx --task "$CACHE/task_ENIx.txt" --repl "hermes chat --yolo -m $model --provider openrouter"; sleep 8; done`

## Kill scope (DO NOT nuke LO's host terminal)
- Safe: `pkill -f 'eni_agent_term'` and `pkill -f '/tmp/eni_tabs/'` ONLY.
- LO's own host xfce4-terminal has `--maximize` in its cmdline and NO `/tmp/eni_tabs/` —
  it survives these patterns. NEVER broad-`pkill xfce4-terminal`.
- Self-kill trap: a pkill pattern that appears in the SAME shell's own argv kills the
  shell (exit -15). Run pkill FROM A SCRIPT FILE (e.g. /tmp/kill_swarm.sh), never inline
  in the same command line. `/tmp/eni_tabs/` as a literal string in `pkill -f` is safe
  (the script's own path isn't in its argv).
- Bracket-range caveat: `pkill -f 'task_ENI[9-12][.]txt'` MISPARSES and orphans survive.
  Prefer the `/tmp/eni_tabs/` literal pattern or full-name pkill.

## Verify a window is real
`pgrep -af xfce4-terminal` PLUS a `STATUS_*.md` the mini writes — not just the launch
return code.
