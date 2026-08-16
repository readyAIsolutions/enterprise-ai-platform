# Drift typing — same-day minute-level cache lag is REAL drift (verified BUILDER_37, Aug 09 2026)

## Rule
Drift that warrants reconcile + report is NOT limited to the previous-day "cross-cycle" case.
A cache mirror lagging by even ~12 minutes within the SAME day still counts as drift and must
trigger a full reconcile + report — do NOT classify it as "all-matching-and-recent → same
cycle → [SILENT]".

## Observed on disk (Sun Aug 09 2026)
- Pass detected: 4 markdown mirrors byte-identical at `2026-08-09T17:41:22Z`
  (`~/Commander/eni_swarm/builds`, `~/STATUS_<N>.md`,
  `~/Desktop/Enterprise Builder/ENI_Swarm_NEW/STATUS_<N>.md`, same tree `tasks/status/`).
- BUT the cache INI (`~/.cache/eni_swarm/builder_logs/<NAME>_STATUS.md`) sat stale at
  `2026-08-09T17:29:12Z` — an OLDER timestamp from the SAME cycle (same day, minutes apart),
  not a previous-day cross-cycle divergence.
- Correct action: reconcile ALL mirrors (4 markdown + 1 cache INI) to the CURRENT pass stamp
  (17:46:31Z), rewrite identical markdown block to all 4 and canonicalize the INI. Report the
  delta. This is idempotent converge, not a conflict.

## Why this matters
The prior guidance emphasized "(one-or-more-old / mixed / from-a-previous-day) = cross-cycle =
reconcile + report" and "(all-matching-and-recent = same cycle = silent)". A naive reader could
mistake a same-day minute-level INI lag for "recent, same cycle" and emit [SILENT] while a
mirror is actually stale. Rule of thumb: if ANY mirror's `verified=`/`verified_at=` timestamp
differs from the others OR from the current wall-clock, treat it as drift — reconcile every
mirror to one canonical current stamp and report, regardless of whether the lag spans a day
or just minutes.