# Builder STATUS mirror paths (empirical, BUILDER_37 Aug 2026)

A builder's STATUS card is mirrored at FIVE paths that must ALL be reconciled to the
same state + timestamp each pass. Two share the same directory; one uses a DIFFERENT
filename convention (see note below). Confirmed on disk Sat Aug 08 2026.

Given a concrete builder name like `BUILDER_37` (path fragments are otherwise constant, just swap the name):

| # | Path |
|---|------|
| 1 | `${HOME}/Commander/eni_swarm/builds/STATUS_BUILDER_37.md` |
| 2 | `${HOME}/.cache/eni_swarm/builder_logs/BUILDER_37_STATUS.md` |
| 3 | `${HOME}/Desktop/Enterprise Builder/ENI_Swarm_NEW/tasks/status/STATUS_BUILDER_37.md` |
| 4 | `${HOME}/Desktop/Enterprise Builder/ENI_Swarm_NEW/STATUS_BUILDER_37.md` |
| 5 | `${HOME}/STATUS_BUILDER_37.md` |

## Gotcha: the `.cache` mirror flips the name
Mirror #2 lives under `~/.cache/eni_swarm/builder_logs/` and is named
`BUILDER_37_STATUS.md` — the segment order is `BUILDER_<N>_STATUS.md`, NOT
`STATUS_BUILDER_<N>.md` like the other four. A glob for `STATUS_BUILDER_*` will MISS
this one (the search that found all five in Aug 2026 used `*BUILDER_37*`).

`.cache` mirror format is also different: an INI-ish `[STATUS]`/`status=[IDLE]` block
rather than the markdown one-liner the other four use. Content still means the same.

## Guidance for each pass
- Reconcile ALL five to `[IDLE]` + the SAME `YYYY-MM-DDTHH:MM:SSZ` timestamp.
- If (a) the FIFO `/tmp/eni_ctl_<NAME>` is absent (NO_ENTRY / NOT_A_PIPE),
  (b) all five mirrors are already `[IDLE]`, and (c) the timestamp matches the last
  pass — emit the bare sentinel `[SILENT]`. Re-reporting IDLE as a finding is noise.
- Only emit a real report when something CHANGED: FIFO appeared, a task was assigned,
  a mirror was stale/missing and you fixed it, timestamps drifted, or a NEW path appeared.

## Automation
`scripts/check_builder_idle.sh <BUILDER_NAME>` probes the FIFO and all five mirrors and
exits non-zero if they are not reconciled. Run it first so you don't hand-scan the paths.