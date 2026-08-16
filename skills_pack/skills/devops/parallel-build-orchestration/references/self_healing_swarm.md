# Self-Healing Swarm + Multi-Workstation Fan-Out

Companion to the `parallel-build-orchestration` skill. Patterns proven in
LO's 9-mini + MASTER DEMIURGE/Lumen swarm (2026-07).

## 1. The corpse-swarm problem
A swarm of `xfce4-terminal` windows can be OPEN while EVERY agent process has
EXITED. Symptom LO reports verbatim: *"where are all my parallel build terms
open"* / *"my terms are open but nothing's happening"*. The launcher reported
"success", FIFOs exist, but `hermes -p eni chat` procs are gone (free-model
429/timeout death). DIAGNOSE before assuming health:

    pgrep -fc 'hermes -p eni chat'        # real agent count; 0 == corpse swarm
    pgrep xfce4-terminal                  # window still alive? (corpse if agents=0)
    pgrep -fc 'eni_agent_term[.]py.*KEYWORD'   # per-agent liveness (PROXY argv)

## 2. Self-healing launcher loop (proactive, not reactive revival)
For free-model swarms, death is the DEFAULT outcome, not the exception. Embed a
restart loop per tab so a dead agent auto-revives. Drop-in skeleton:

    while true; do
      python3 ~/.local/bin/eni_agent_term.py \
        --name "${name}" \
        --task "$CACHE/task_${name}.txt" \
        --repl "hermes chat --yolo -m ${model} --provider openrouter"
      echo "[$(date)] agent ${name} exited (rc=$?) — restarting" >>/tmp/eni_selfheal.log
      sleep 2
    done

Caveat: a dead agent spinning in a tight loop CAN hammer the rate limit and
burn the daily free cap. Keep `sleep 2` (or back off to 10-30s after repeated
exits). The point is the swarm never stays dead — it self-revives when the cap
resets.

## 3. Per-window chunking across monitors (4-screen layout)
Open ONE `xfce4-terminal` window per monitor group, all agents in `--tab`s of
their window, MASTER as the FIRST `--tab` of the primary-monitor window. Window
geometry from `xrandr --listmonitors` origins. LO's box example (4 monitors):
DP-0 primary middle +1920+0, DP-1 left +0+0, DP-2 right +4480+0, HDMI +2274+1080.

    WINDOWS=("MASTER M0 M1 M2" "" "" "")   # index 0 = primary window (MASTER front)
    for w in 0 1 2 3; do
      read -r -a grp <<< "${WINDOWS[w]}"
      [ ${#grp[@]} -eq 0 ] && continue
      win=("xfce4-terminal" "--geometry=210x54+1920+0")   # per-window origin
      for name in "${grp[@]}"; do win+=("--tab" "--title=$name" "-e" "bash /tmp/eni_tab_$name.sh"); done
      "${win[@]}" &
    done

## 4. Multi-workstation fan-out (multiple PCs, not just 4 monitors)
LO says "use all 4 workstations" = SEPARATE physical PCs on the LAN, not 4
monitors on one box. This box = `demiurge-linux`; others reachable via LAN IP.

Prerequisite — passwordless SSH (ONE-TIME, needs his password):
    ssh-copy-id hunter@192.168.1.64
    ssh-copy-id hunter@192.168.1.65
    ssh-copy-id hunter@192.168.1.66

Probe topology without a password prompt:
    cat ~/.ssh/known_hosts                      # known IPs
    ssh -o BatchMode=yes -o ConnectTimeout=5 hunter@<ip> true   # tests auth
    # Permission denied (publickey)  => key NOT authorized; need ssh-copy-id
    # REMOTE HOST IDENTIFICATION HAS CHANGED => ssh-keygen -R <ip> then retry
    # Connection timed out => host down (e.g. a VM guest)

Benefit: spreading agents across 4 IPs dodges the per-IP / per-account free-model
rate limit that kills single-box swarms. Combine BOTH axes: spread across
MODELS (3 live free slugs) AND across IPs (4 workstations). After SSH is up,
the launcher can `ssh hunter@<ip> 'bash /tmp/eni_tab_<name>.sh'` per agent, or
push the tab scripts + run them remotely.

## 5. Real-data mount reality (DEMIURGE USB)
- The canonical `/run/media/hunter/DEMIURGE` was a PRE-EXISTING EMPTY root-owned
  dir; symlinking the real stick failed with Permission denied. The real project
  appeared at `/run/media/hunter/DEMIURGE1` after LO mounted it.
- The USB is a Tor THIN-CLIENT: `.demiurge/config.json` `server_url`
  `http://<hash>.onion:8420` (DiskStation NAS over Tor). USB is amnesic; real
  persistent data lives on the NAS. Local USB snapshot data (data_snapshot_*.tar.gz,
  dashboard/app.py, engine/, scripts/walk_forward.py) IS usable offline.
- Scaffold `walk_forward.py` (repo root) is a STANDALONE SYNTHETIC harness that
  generates its own data — zero OANDA wiring. Real-data integration is the actual
  blocked work minis should prep, not run inside the free-model mini.
- On LO's box, after he mounted the USB on the HOST, the container DID see
  `/run/media/hunter/DEMIURGE1` (home is bind-mounted). Don't assume mount
  isolation — `ls /run/media/hunter/<LABEL>` first.
