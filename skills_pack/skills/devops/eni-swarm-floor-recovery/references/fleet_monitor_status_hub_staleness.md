# Fleet Monitor — status_hub Live ≠ Swarm Active; & correct probe path

Session-derived discriminators for cron fleet-monitor runs (2026-08-16).

## 1. Probe script: use the FULL category path

The probe lives under the `devops/` category subdir, NOT directly under
`~/.hermes/skills/`. The SKILL.md head truncates the path, which invites a wrong
guess; always run by absolute path:

    bash /home/hunter/.hermes/skills/devops/eni-swarm-floor-recovery/scripts/fleet_health_probe.sh

Wrong guess (silently 127s): `~/.hermes/skills/eni-swarm-floor-recovery/...` (no `devops/`).
Mnemonic: `devops/` is present because the skill's category is devops.

## 2. Controller alive ≠ swarm active (status_hub staleness trap)

status_hub.py (worker w2) regenerates MASTER_STATUS.md every few minutes even
when the entire swarm is dead-dormant. Its summary can look impressively active
while every underlying mini file is weeks stale:

    Observed 2026-08-16: MASTER_STATUS refreshed 02:05 (3 min old), reports
    598 minis: 207 DONE / 388 IN-PROGRESS / 3 BLOCKED, 391 ALERTS.
    BUT every STATUS_ENI*.md last-update was 2026-07-23 (~34,600 min / 24 days old).

So "controller healthy + churning" is only the status_hub PROCESS being alive.
Do NOT read "388 in-progress" as a live swarm. ALWAYS cross-check the per-mini
STATUS_ENI*.md mtimes/ages before concluding the controller means real work:

    head MASTER_STATUS.md   # look at the per-mini 'age' column, not the Summary
    ls -lt eni_swarm/STATUS_ENI*.md   # if newest is weeks old -> stale, not active

If every mini is stale and gate=RED/windows=0, the fleet is dormant despite a
healthy controller — follow the standing [SILENT]-vs-report logic in
`monitor_cron_diagnostics.md`.

## 3. Disambiguate multiple concurrent cron firings

Browse via session_search shows several cron jobs (different session_id prefixes)
firing within the same minute. When checking "was this already reported before",
confirm you are reading the SAME monitor job's session, not a sibling cron — the
earliest/current firing has no matching prior report, so [SILENT] suppression must
be judged against the standing-state doctrine, not merely an empty search hit.