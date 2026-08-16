# Builder idle-pass — canonical script invocation (verified BUILDER_37, Aug 2026)

The idle check for a dispatched builder is NOT at the path the skill's own
`skill_view` linked-files listing suggests. `skill_view` shows `scripts/check_builder_idle.sh`
but the real on-disk install lives under a `devops/` subdirectory. The module also
compresses its SKILL.md / references into carriers, so the path is not obvious from
`skill_view` output — locate or invoke it directly.

## Canonical paths

- Idle-check script:
  `$HOME/.hermes/skills/devops/eni-mini-protocol/scripts/check_builder_idle.sh`
- Other scripts in the same dir: `eni_pl_relay.sh`, `eni_resume.sh`.
- Do NOT rely on a stray `/tmp/check_builder_idle.sh` copy (stale/transient).

## Verified invocation

```bash
bash "$HOME/.hermes/skills/devops/eni-mini-protocol/scripts/check_builder_idle.sh" BUILDER_37
```

Requires `<BUILDER_NAME>` as arg 1 (e.g. `BUILDER_37`).
Exit codes:
- `0`  → FIFO absent AND all found STATUS mirrors agree on [IDLE] → emit bare `[SILENT]`.
- `1`  → mirrors not fully reconciled (missing, or not all IDLE) → reconcile all five, re-run.
- `3`/`4` → FIFO present (a pipe = directive pending; regular file = stale) → NOT idle, do real work.

## What it scans (all 5 mirror paths)

1. `$HOME/Commander/eni_swarm/builds/STATUS_<NAME>.md`
2. `$HOME/.cache/eni_swarm/builder_logs/<NAME>_STATUS.md`  ← INI format, uses the ALTERNATE
   naming + `status=[IDLE]` token (easy to miss; the script tokenizes BOTH markdown H1
   and this INI block).
3. `$HOME/Desktop/Enterprise Builder/ENI_Swarm_NEW/tasks/status/STATUS_<NAME>.md`
4. `$HOME/Desktop/Enterprise Builder/ENI_Swarm_NEW/STATUS_<NAME>.md`
5. `$HOME/STATUS_<NAME>.md`

Empirical confirmation (BUILDER_37, Sun Aug 09 2026): all 5 present, all `[IDLE]`,
all with matching recent mtime (same cycle) → `Found=5/5 Idle=5/5`, exit 0 → bare `[SILENT]`.

## Pitfall
Trying to `cd ~/.hermes/skills/eni-mini-protocol/scripts` (no `devops/`) fails and runs
nothing. Always invoke by the full canonical path above, or `find / -name check_builder_idle.sh`
if unsure.
