#!/usr/bin/env bash
# ============================================================================
# Host-side terminal launcher  —  RUN FROM A REAL HOST TERMINAL
# (The Hermes CLI container cannot paint X windows; this script must run on
#  the user's actual desktop to show visible gnome-terminals.)
#
#   bash ~/Desktop/<this_script>.sh
#
# Opens one visible gnome-terminal per program, each running a verify/build
# step and staying open (exec bash) so the user can read the output.
# Copy + edit the gnome-terminal lines for your own programs.
# ============================================================================
set -u

# 1) Example: GPU tune + check (needs sudo on the host)
gnome-terminal --title="1 GPU Tune + Check" -- bash -c \
  'sudo bash ~/amd-ultimate-tune.sh; echo; gpu-check; echo; exec bash' &

# 2) Example: run an app that needs X11
gnome-terminal --title="2 App (needs X)" -- bash -c \
  'cd ~/Desktop/apps/<app> && .venv/bin/python -m <app>; echo; exec bash' &

# 3) Example: run a smoke-test suite
gnome-terminal --title="3 Scaffold Smokes" -- bash -c \
  'cd ~/Commander/<scaffold> && for f in data backtest walk_forward; do echo "===== $f ====="; python3 "$f.py"; done; echo; exec bash' &

wait
echo "All terminals launched."
