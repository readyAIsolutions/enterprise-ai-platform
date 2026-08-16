# Reconciling HEARTBEAT_LEDGER entries against disk files

## The zero-padded filename pitfall (verified 2026-08-11)
Builder status files are **zero-padded**: BUILDER_05 lives at
`builds/STATUS_BUILDER_05.md`, NOT `STATUS_BUILDER_5.md`. The full set runs
`BUILDER_01`..`BUILDER_50`.

### Why this bites
`monitor_fleet.py` extracts the builder number with
`re.search(r"STATUS_BUILDER_(\d+)\.md", basename)`, which parses `05` → `5`
correctly, so the ledger reads `[IN-PROGRESS] BUILDER_5`. But any glob/grep you
hand-run against disk with the *unpadded* form silently misses it:

- `ls builds/STATUS_BUILDER_5.md` → "No such file"  (wrong — file is `_05`)
- `ls builds/ | grep -E "BUILDER_5"` → only matches `STATUS_BUILDER_50.md`
- `find . -iname "STATUS_BUILDER_5*.md"` → only `STATUS_BUILDER_50.md`

Result: a ledger line (`BUILDER_5`) with no visible backing file, which looks
like corruption/staleness when it's just padding. Cost several dead-end lookups.

### Correct reconciliation approach
Match against the **parsed integer**, or match the padded form with an
optional leading zero:
- Python: `int(re.search(r"STATUS_BUILDER_(\d+)\.md", basename).group(1))`,
  then test `n == target` (handles both `05` and `5`).
- Glob with prefix + optional zero: `STATUS_BUILDER_0?<N>.md`, or just list all
  `STATUS_BUILDER_*.md` and extract numbers (like `monitor_fleet.py` itself does).
- Never trust `STATUS_BUILDER_<N>.md` as an exact path without checking padding.

### Empty-file crash guard (companion fact)
`BUILDER_20`'s file was 0 bytes this run. `monitor_fleet.py` skips
empty/blank files (`if not lines or not any(l.strip() for l in lines)`), so a
builder that crashed before writing content drops OUT of the ledger entirely —
the ledger having 49 entries when 50 `STATUS_BUILDER_*.md` files exist is
normal, not a parsing bug. Cross-check counts before calling it a miss.