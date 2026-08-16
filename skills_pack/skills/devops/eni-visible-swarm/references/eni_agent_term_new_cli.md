# eni_agent_term.py — NEW CLI (verified 2026-07-09)

The PTY bridge changed its CLI. The OLD positional form is DEAD:

    eni_agent_term.py "@task.txt" "workdir" --yolo -m model --provider openrouter
    # -> error: the following arguments are required: --name

## New CLI

    python3 ~/.local/bin/eni_agent_term.py \
      --name ENI1 \
      --task ~/.cache/eni_parallel/task_ENI1.txt \
      --repl "hermes chat --yolo -m tencent/hy3:free --provider openrouter"

- `--name NAME` (required): mini name; also the CTL FIFO `/tmp/eni_ctl_<NAME>`.
- `--task FILE` (optional): prompt file PRE-TYPED into the pty on the hermes banner.
- `--repl CMD` (optional, default a bash read-loop): the command exec'd inside the pty.
  Put the FULL `hermes chat ...` command here. Model/provider live INSIDE `--repl`
  now, NOT as proxy flags.
- `--yolo` is harmless to the proxy but irrelevant (the REPL is hermes chat).
- `--fifo PATH` sets the relay FIFO explicitly.

## Working per-mini self-heal runner (/tmp/eni_tabs/run_ENI1.sh)

    #!/bin/bash
    export HERMES_CTL_FIFO=/tmp/eni_ctl_ENI1
    export DEMIURGE_USB="/run/media/hunter/DEMIURGE1"
    export PATH="/home/hunter/.local/bin:$PATH"
    export PYTHONPATH="$(ls -d /home/hunter/.local/lib/python3.*/site-packages 2>/dev/null | sort -V | tail -1)"
    cd /home/hunter/Commander/eni_swarm 2>/dev/null || cd /home/hunter
    while true; do
      python3 /home/hunter/.local/bin/eni_agent_term.py \
        --name ENI1 --task /home/hunter/.cache/eni_parallel/task_ENI1.txt \
        --repl "hermes chat --yolo -m tencent/hy3:free --provider openrouter"
      echo "[$(date)] ENI1 rc=$? restart 3s" >> /tmp/eni_err_ENI1.log
      sleep 3
    done

PRODUCT_LEAD uses model `qwen/qwen3-coder:free` and `task_PRODUCT_LEAD.txt`
(create it if the roster points at a missing file — it did this session).

## Even 2x2 tiling (LO requires even spacing)

Measured via `xprop -root _NET_CLIENT_LIST` + `xwininfo -id`. Use 90x23 terms
(~918x499px):

    TCOLS=90; TROWS=23; TMARGIN=20; TMARGIN_TOP=40; TGAP=20
    TXPX=$(( TCOLS*101/10 + 2 ))   # ~911
    TYPX=$(( TROWS*20 + 34 ))      # ~494
    COLSTEP=$(( TXPX + TGAP ))     # 931
    ROWSTEP=$(( TYPX + TGAP ))     # 514
    # term i on screen at origin (OX,OY): col=i%2, row=i/2
    geo="${TCOLS}x${TROWS}+$((OX+TMARGIN+col*COLSTEP))+$((OY+TMARGIN_TOP+row*ROWSTEP))"

The old `120x30` at `+960`/`+540` steps OVERLAPS (a 120-col term is ~1218px wide).
Verify after paint with the xprop/xwininfo probe — LO checks spacing.

## Fleet fan-out (4 workstations)

`~/Desktop/Commander/eni_swarm/fleet_deploy.sh` (written this session) SSHes to
remotes, auto-detects each box's monitors via `xrandr --listactivemonitors`, syncs
toolchain + tasks, and paints uniform 4-terms/screen (remote rule: EVERY screen
incl. the big one = 4 terms; no master-chat/heartbeat on remotes — those live on
WS1 only). BLOCKED until `ssh-copy-id hunter@192.168.1.65` + `.66` run once (keys
not in authorized_keys; .67 down). The canonical `templates/eni_swarm_4ws.sh`
(in this skill's `templates/`) does NOT invoke the proxy directly — verified
2026-07-09 it delegates to `eni_mini_run.sh`, which already passes
`--repl "hermes chat --yolo -m $MODEL --provider $PROVIDER"`. The old-CLI warning
no longer applies; any future proxy call there must still use `--name/--task/--repl`.
