#!/usr/bin/env bash
# eni_master_herself.sh — run the contextual MASTER driver against the ENI-herself swarm.
# Honors ENI_TASKS_JSON so the driver targets ENI1..ENI12 (not the separate product swarm).
# MUST run on the SAME machine as the launcher (talk-FIFOs live in that host's /tmp).
export ENI_TASKS_JSON="${ENI_TASKS_JSON:-$HOME/Desktop/eni_herself_tasks.json}"
export PATH="$HOME/.local/bin:$HOME/bin:$PATH"
exec python3 "$HOME/Desktop/eni_master_driver.py"
