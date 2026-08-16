# Builder-Slot Provisioning Diagnostics

When a dispatch (cron or otherwise) references a builder slot as `eni_ctl_BUILDER_<N>`
or `ENI_BUILDER_<N>`, DO NOT assume the slot is live. Control files are **named pipes
(FIFOs)**, not regular files — their absence, not just empty content, means the slot
was never provisioned or was torn down. Verify before processing.

## Canonical verification sequence

1. **Target control FIFO:** `ls -la /tmp/eni_ctl_BUILDER_<N>` / `read_file`.
   FIFOs show as `p` in the mode column (`prw-r--r--`). A missing file = slot not provisioned.
2. **Status file:** `cat <project>/STATUS_BUILDER_<N>.md`. Live slots have a status file.
   Example project root: `/home/hunter/Desktop/Projects/ENI_Swarm_NEW/`.
   NOTE: this legacy project root has gone stale as of Aug 2026. The ACTIVE ENI platform
   root is `/home/hunter/Desktop/Enterprise Builder/enterprise/`, with operable CLI at
   `scripts/eni_cli.py` (`/tmp/eni-cli` wraps it; note the space in the path — quote the
   cd, don't run the wrapper with the space unquoted). If the roster/status files aren't
   under the legacy root, check the active enterprise dir or grep it before concluding.
3. **Live watcher process:** `ps aux | grep -i "builder_.*watcher"` — a provisioned slot
   that is actually running has a watcher process. Absence means not running.
4. **Task roster:** `config/eni_build_tasks.json` in the project root. If the roster
   file is missing/empty, no work is assigned via the Master Driver, so there is
   nothing to consume regardless of the FIFO.
5. **Enumerate what IS live** before concluding: `ls -la /tmp/eni_ctl_*` and
   `ls <project>/STATUS_BUILDER_*`. This shows you the real active slot range.

## Distinguishing active vs stale/legacy floor state

- Control FIFOs and status files from an earlier build-floor run persist in `/tmp` and
  the project dir. Judge liveness by **timestamp + matching watcher process + matching
  status file**, not by presence.
- Observed example: a floor that previously ran `eni_ctl_DEMIURGE_B01–B12` and
  `eni_ctl_DEMIURGE3D_B01–B12` (all one old timestamp, no watchers) had scaled down to
  a single active `eni_ctl_BUILDER_50` slot with its own watcher script
  (`~/.hermes/scripts/builder_50_watcher.sh`). The other FIFOs were stale.

## Controller liveness is a SEPARATE axis from slot liveness

Even when no builder slot is provisioned and there is no work to consume, the platform
itself may be healthy — the controller server runs independently of any particular slot.
`ps aux | grep "eni_controller.controller serve"` finds the daemon (default port **8940**).
Confirm it is actually serving via the health JSON, not just the process existing:

```
curl -s http://localhost:8940/health
```

A healthy reply reports per-component checks (`airllm`, `free_router`, `secrets`,
`enterprise` + module count, `hermes_runner`). Use this to separate "dispatcher slot is
stale/cold" from "the whole ENI controller is down" — they need different remediation (re-provision
the slot vs restart the controller). Report both findings when you conclude a no-op
dispatch: the absent slot AND the controller health, so the reader knows the platform
backing isn't silently broken.

## Watcher mechanics (what a provisioned slot's FIFO does)

The reference watcher (`builder_50_watcher.sh`) pattern:
- Opens the FIFO read-write (`exec 3<>FIFO`) so `open()` never blocks on a missing writer.
- Reads with a bound: `read -t 1 -r line <&3`.
- Writes `[IN-PROGRESS] <line>` vs `[IDLE] ...` to the STATUS file, and echoes a
  verified timestamp to `/tmp/builder_verified`.

## Extracting a single builder's roster entry (3.7MB roster)

`config/eni_build_tasks.json` holds all ~50 builders' full ENI persona prompts and is ~3.7MB —
do NOT read/file it whole. Pull just the target entry with a one-liner:

```bash
cd "<project_root>/ENI_Swarm_NEW" && python3 -c "
import json
d=json.load(open('config/eni_build_tasks.json'))
for t in d['tasks']:
    if t['name']=='BUILDER_37':
        for k,v in t.items(): print(f'--- {k} ---'); print(str(v)[:800])
        break
else: print('NO <NAME> ENTRY')
"
```
Key fields to inspect: `workdir` (often still points at the stale legacy root
`/home/hunter/Desktop/Projects/ENI_Swarm_NEW` even after the platform moved active) and
`status_file`. An entry existing in the roster does NOT mean the slot is provisioned — the
FIFO + watcher + IDLE status file are what actually gate execution.

## Duplicate status files across swarm dirs

There can be multiple `STATUS_BUILDER_<N>.md` (e.g. one under `ENI_Swarm_NEW/`, one under
`ENI_Swarm_NEW/tasks/status/`, and a stale one under the legacy `Desktop/Projects/` root).
Read the one under the ACTIVE root (`/home/hunter/Desktop/Enterprise Builder/ENI_Swarm_NEW/`)
for the real liveness signal; confirm it is truly IDLE by cross-checking that no watcher
process and no matching FIFO exist. A status file present ≠ slot running.

## Dispatch outcome convention

For a no-op (slot genuinely not provisioned / no task line to consume), the appropriate
deliverable is a concise report of the discrepancy, not a fabricated task result.
Do not delegate subtasks that read a nonexistent file, and do not invent task-processing
work for an empty roster.