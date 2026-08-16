# Fleet Monitor — verified cron run recipe (2026-08-09)

Two easy-to-miss details from an actual successful heartbeat run. The
`eni-swarm-telemetry` SKILL.md workflow is broadly correct; these are the
exact commands/quirks that made it work end-to-end.

## 1. Probes / scripts live in the SKILL dir, NOT the swarm dir
The `fleet_liveness_probe.sh` script is bundled with the skill, not committed
to `/home/hunter/Commander/eni_swarm`. Running `bash scripts/fleet_liveness_probe.sh`
from the swarm dir fails with **exit 127** (file not found). Use the absolute path:

```bash
cd /home/hunter/Commander/eni_swarm
bash /home/hunter/.hermes/skills/devops/eni-swarm-telemetry/scripts/fleet_liveness_probe.sh /home/hunter/Commander/eni_swarm
```

Always pass the swarm dir explicitly as `$1` — otherwise the probe's own guard
flags "0 status files" (a bad-path false alarm, not a dead fleet).

## 2. monitor_fleet.py writes the ledger to CWD, not builds/
`LEDGER_PATH = "HEARTBEAT_LEDGER.md"` is relative → the script drops the fresh
ledger into whatever directory you ran it from. Run it from the swarm root, then
sync the canonical copy (the one LO actually reads) into `builds/`:

```bash
cd /home/hunter/Commander/eni_swarm && python3 monitor_fleet.py
cp HEARTBEAT_LEDGER.md builds/HEARTBEAT_LEDGER.md
```

(50 status files on disk → 49 ledger lines: BUILDER_20's file is 0 bytes and is
correctly skipped by the crash guard.)

## 3. Read the FRESHEST status file, not the ledger, for truth
The ledger's `[IN-PROGRESS]`/`[BLOCKED]` rows are stale relics (here: 8 IP + 1
BLOCKED, all dated ~Jul 25, zero live processes). Cross-check with the probe's
`fresh_today` count and read the newest file (`BUILDER_37` — an explicit
`IDLE — do not invent work` line) before reporting. An empty `HEARTBEAT_ALERTS.md`
means no builders are force-blocked this pass.