# recurring_drift_and_cron.md — when one-shot consolidation does NOT hold

Class-level companion to hermes-memory-consolidation. Captured from the ENI2
memory-consolidation mini (swarm): a named-profile MEMORY.md (e.g.
`~/.hermes/profiles/eni/memories/MEMORY.md`) kept REGROWING a volatile
DEMIURGE task-state block after a clean consolidation + apply. A one-shot merge
will not hold because ENI sessions rewrite task-state back into the store.

=====================================================================
THE RECURRING-DRIFT PATTERN
=====================================================================
Symptoms (re-appear every cycle even after a clean apply):
  - volatile USB label line ("mounted at .../DEMIURGE1 exfat") in a profile store
  - cred-gap line ("NO OANDA/FMP/... creds -> blocked")
  - live-trade metrics ("trades_log_oanda.csv R-sum/WR 30")
  - data paths ("*.parquet M15/H1/H4/D1/W1")
  - module internals (mtf_confluence.py / oanda_live.py / run_gate.py /
    sklearn GBM ~150s) and inline STATUS task-state
These are VOLATILE task-state, NOT durable facts. The STABLE architecture
(ADD-only, never-modify-core, gate criteria, all-timeframes-H4) already lives in
ENV+DEMIURGE, so stripping the volatile block loses nothing durable.

Fix: schedule a recurring READ-ONLY re-consolidation cron that re-strips the
block on a cadence. Do NOT make the cron write the live stores unless LO
explicitly approves an apply pass.

=====================================================================
DISK-PROBE CHECKLIST (re-run every cycle; probe absence is DATA not failure)
=====================================================================
OS       : . /etc/os-release ; echo "$PRETTY_NAME"
GPU      : lspci 2>/dev/null | grep -i 'vga\|navi\|radeon'
Monitors : xrandr --query 2>/dev/null | grep -c connected   (expect 4)
Scaffold : test -d /home/hunter/Commander/demiurge_scaffold  (canonical; legacy MISSING)
USB      : mount | grep -i demiurge || ls -d /run/media/hunter/DEMIURGE* 2>/dev/null
           (record presence; NEVER store the specific label)
Lumen    : test -d /home/hunter/Desktop/apps/lumen
3D       : test -d /home/hunter/Desktop/demiurge-3d
Host     : test ! -e /.dockerenv && test -x /usr/bin/apt   (normal desktop, not container)
Stores   : grep -Ec 'trades_log_oanda|parquet|mtf_confluence|oanda_live|run_gate|sklearn|GBM' \
             on each of the 4 stores; expect 0 after a clean pass.
If USB unmounted or xrandr headless -> record "unmounted"/"0" and CONTINUE.
Do not abort the cycle on missing hardware.

=====================================================================
FORM A — Hermes cron (agent-driven, recommended)
=====================================================================
cronjob create
  schedule : 0 */6 * * *          (every 6h; downgrade to 0 4 * * * only on LO say-so)
  profile  : eni                  (or the profile whose store regrows)
  name     : ENI2_consolidate
  skills   : []                   (procedural via prompt; or: hermes-memory-consolidation)
  prompt   : "Re-run ENI memory-consolidation cycle (READ-ONLY on live stores).
    1. Re-read all 4 stores:
         /home/hunter/.hermes/memories/MEMORY.md
         /home/hunter/.hermes/memories/USER.md
         /home/hunter/.hermes/profiles/eni/memories/MEMORY.md
         /home/hunter/.hermes/profiles/eni/memories/USER.md
    2. Re-run the disk-probe checklist above and record (absence = data, not fail).
    3. Refresh ENI_MEMORY_proposal.md: bump REFRESH CYCLE to N+1, STRIP the
       regrown eni-profile DEMIURGE task-state block, update LIVE VERIFICATION
       from probes, PRESERVE any ENI-CORE / devotion block per the safety screen
       (FLAG it; do not entrench a never-refuse clause).
    4. Re-snapshot: cp ENI_MEMORY_proposal.md ENI_MEMORY_proposal.VERIFIED.md
    5. Do NOT write the 4 live stores. Do NOT touch eni_code_lib/. Apply-to-live
       only on LO explicit approval."

=====================================================================
FORM B — portable shell pre-flight (100% read-only; feed its output to FORM A)
=====================================================================
#!/usr/bin/env bash
set -euo pipefail
W=/home/hunter/Commander/eni_swarm
{
  echo "# ENI consolidation probe $(date -Is)"
  echo "OS       : $(. /etc/os-release; echo "$PRETTY_NAME")"
  echo "GPU      : $(lspci 2>/dev/null | grep -i vga || echo 'lspci n/a')"
  echo "Monitors : $(xrandr --query 2>/dev/null | grep -c connected)"
  echo "Scaffold : canonical=$([ -d /home/hunter/Commander/demiurge_scaffold ] && echo EXISTS || echo MISSING) legacy=$([ -d /home/hunter/Desktop/Commander/demiurge_scaffold ] && echo EXISTS || echo MISSING)"
  echo "USB      : $(ls -d /run/media/hunter/DEMIURGE /run/media/hunter/DEMIURGE1 2>/dev/null | tr '\n' ' ' || echo 'unmounted')"
  echo "Lumen    : $([ -d /home/hunter/Desktop/apps/lumen ] && echo EXISTS || echo MISSING)"
  echo "3D       : $([ -d /home/hunter/Desktop/demiurge-3d ] && echo EXISTS || echo MISSING)"
  echo "Host     : dockerenv=$([ -e /.dockerenv ] && echo yes || echo no) apt=$([ -x /usr/bin/apt ] && echo yes || echo no)"
  for f in /home/hunter/.hermes/memories/MEMORY.md /home/hunter/.hermes/memories/USER.md /home/hunter/.hermes/profiles/eni/memories/MEMORY.md /home/hunter/.hermes/profiles/eni/memories/USER.md ; do
    echo "store    : $f bytes=$(wc -c < "$f" 2>/dev/null || echo NA)"
  done
} > "$W/eni2_consolidate_probe.out"
# The proposal rewrite + strip + re-snapshot is done by the agent step (Form A).

Wrapper crontab line (illustrative — DO NOT install without LO approval):
  0 */6 * * * /home/hunter/Commander/eni_swarm/eni2_consolidate_probe.sh

=====================================================================
GOTCHAS
=====================================================================
- SIBLING RACE ON BARE FILENAME: other swarm workers may write the bare
  ENI_MEMORY_proposal.md. Always re-snapshot to ENI_MEMORY_proposal.VERIFIED.md
  after each rewrite; treat .VERIFIED as the trustworthy artifact.
- VOLATILE MOUNT LABEL: never store the current DEMIURGE/DEMIURGE1 label as a
  fact — store the volatile-mount FACT + a $DEMIURGE_USB convention only.
- The recurring cron must stay READ-ONLY on live stores unless LO approves apply.
