# Confirming Prior Firing Before [SILENT] — session_search Phrasing Pitfall

The repeated-state suppression rule (monitor_cron_diagnostics.md) requires confirming the
fleet state is truly unchanged from the PRIOR cron firing via `session_search` before
emitting `[SILENT]`. This reference records a real pitfall hit Aug 16 2026.

## The trap
`session_search` uses FTS5 with **AND as the default** between terms. A multi-word query
like `"fleet health probe gate=RED windows=0 idle"` or `"repeat-state suppression SILENT
fleet idle dormant"` can return **0 results** even when dozens of prior `[SILENT]` cron
sessions exist on disk. All terms must match somewhere in the message text across the
same message — a query that combines tokens spread across different messages, or uses
too many distinct concepts, filters everything out.

A naive agent reading "0 results" could conclude "this may be the first firing with no
prior report" and wrongly emit a full report (desensitizing LO) instead of suppressing.

## The fix — broaden or simplify
- Drop to a small number of SHARED, high-signal tokens, e.g. `gate RED` or
  `builder floor idle` or `fleet monitor SILENT`. These appear verbatim in prior reports.
- Or use explicit OR / a single quoted phrase that matches one line of a prior
  report exactly (e.g. `"gate=RED"`).
- Prefer `sort:"newest"` + `limit:5` and scan the returned `bookend_end` — the prior
  firing's final answer (`[SILENT]` or a full report) is the comparison target.
- The prior firings are all `source:"cron"` sessions; the most recent one is the baseline.

## Decision rule (unchanged)
Only `[SILENT]` when: gate=RED + windows=0 + stalls=none + no new alerts/heartbeat
changes, AND session_search confirms the immediate prior firing reported the identical
state. If search returns 0 (likely phrasing, not truly-no-prior), broaden the query and
retry before concluding it's the first firing.