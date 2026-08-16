# BUILDER STATUS mirror paths (empirically confirmed, BUILDER_37 Aug 2026)

A builder's STATUS card is mirrored at MULTIPLE on-disk paths that must ALL be
reconciled to the same state + current timestamp each pass. Discover them
EMPIRICALLY with a filesystem search, not just from this list — the fleet may
add/remove mirrors.

Confirmed concrete enumeration for BUILDER_37 (Sat Aug 08 2026): FIVE mirrors,
FOUR header-form + ONE native-form.

## Four header-form mirrors
Header form uses the `# STATUS_BUILDER_<N> — <STATE> — <TS>` markdown header line.
All four carry IDENTICAL bytes (state + timestamp must match exactly across them):
1. `<HOME>/Desktop/Enterprise Builder/ENI_Swarm_NEW/STATUS_BUILDER_<N>.md`
2. `<HOME>/Desktop/Enterprise Builder/ENI_Swarm_NEW/tasks/status/STATUS_BUILDER_<N>.md`
3. `<HOME>/STATUS_BUILDER_<N>.md`
4. `<HOME>/Commander/eni_swarm/builds/STATUS_BUILDER_<N>.md`

## One native-form mirror
Distinct `[STATUS]` INI-style key=value format (NOT a markdown header). Same
state + timestamp, different layout:
`<HOME>/.cache/eni_swarm/builder_logs/BUILDER_<N>_STATUS.md`

Example native-form body:
```
[STATUS]
status=[IDLE]
verified=Control FIFO ... does not exist (re-verified 2026-08-09T06:01:27Z ...)
blocker=none
next=await LO's directive via /tmp/eni_ctl_<NAME> FIFO creation
```

### Native-form timestamp format differs from header-form (empirically confirmed Aug 09 2026)
The native mirror's `verified=` timestamp is ISO-8601 **UTC**, generated with
`date -u '+%Y-%m-%dT%H:%M:%SZ'` (e.g. `2026-08-09T06:01:27Z`). It does NOT use the
local human-readable `%a %b %d %H:%M %Y` form of the header-form mirrors. Because the
native mirror often also uses shorthand like "await LOs directive" (no apostrophe),
do NOT byte-match it against the header-form mirrors — only verify it contains the
`[IDLE]` state and a fresh UTC timestamp.

## Reconcile-and-verify loop (run each pass)
1. `find <HOME> -name "*STATUS_BUILDER_<N>*"` and `find <HOME> -path "*BUILDER_<N>*" -name "*.md"`
   to enumerate ALL current mirrors (incl. any under `.cache/eni_swarm/builder_logs/`).
2. For each mirror, write the same state + current `date` timestamp
   (`date '+%a %b %d %H:%M %Y'` gives the header-form stamp format — use the
   locale-independent `%a` day field, NOT a hardcoded literal like `Sat`, which
   corrupts once the day-of-week changes mid-week).
3. After writing all, re-verify each HEAD with one quick loop (e.g. `head -3 <mirror>`)
   to confirm state + timestamp landed.
4. Stronger final check (empirically used Aug 2026): run `md5sum` ACROSS the four
   header-form mirrors — they MUST all produce identical checksums. This deterministically
   proves state AND timestamp are byte-for-byte identical across all mirrors in one
   command, catching drift that a `head -3` human glance could miss. Confirm count == 4
   identical hashes. (The native-form mirror is the intentional exception — different
   layout, same state+timestamp, so it is NOT part of the md5 set.)

## Pitfalls
- `write_file` on a mirror that a sibling builder/process also writes can emit a
  sibling-modification warning. Do NOT abort or merge — the reconcile is idempotent
  (same state + same timestamp), parallel writers converge to the same bytes. Proceed.
- WARNING SRC IDs MAY DIFFER ACROSS MIRRORS (observed BUILDER_37 Aug 09 2026): during
  one reconcile pass the four markdown-form mirrors reported sibling-modification
  warnings from one subagent ID while the cache mirror reported a DIFFERENT subagent ID.
  That is expected — a sibling cron pass writes ALL the mirrors, and each path's warning
  can be attributed to a different concurrent writer. Do NOT treat differing warning IDs
  as a conflict or partial failure; the reconcile is still idempotent. The single
  authoritative proof of convergence is the 4-way md5sum below (all four markdown
  mirrors MUST share one hash); write all five, then VERIFY with md5sum, don't dwell on
  warning provenance.
- If recon a SIBLING cron pass already wrote the same `[IDLE]` + a slightly older
  timestamp this session, rewrite all mirrors to the CURRENT timestamp so they match.
- The four header-form mirrors must be byte-identical; the native-form mirror is the
  intentional exception with its own layout.
- Reading references via skill_view/read_file on this environment returns ENI-compressed
  carriers (truncated head/tail). Recover full text by `cat`-ing the raw file path under
  `~/.hermes/skills/.../references/` — the compression wrapper does not block terminal cat.