# Parsing the fleet ledger: the IN-PROGRESS regex trap + summary/verify flow

Learned on the 2026-08-15 cron monitoring pass of `monitor_fleet.py` /
`HEARTBEAT_LEDGER.md`.

## Pitfall: `\[\w+\]` silently fails on `IN-PROGRESS`

The ledger lines look like:

    [IN-PROGRESS] BUILDER_5 verified=unknown blocker=unknown next=unknown
    [DONE] BUILDER_44 verified=unknown blocker=unknown next=unknown
    [BLOCKED] BUILDER_46 verified=unknown blocker=unknown next=unknown

The hyphen in `IN-PROGRESS` is NOT a word character, so a naive
`re.match(r'\[(\w+)\]', line)` returns `None` for every in-progress builder.
When you then do `m.group(1)`, it throws `AttributeError: 'NoneType' object
has no attribute 'group'` — or worse, if you guard the match, the in-progress
row is silently dropped from your counts. The `monitor_fleet.py` script itself
deliberately scans for `IN[-_ ]?PROGRESS` / hyphenated forms, so the ledger has
real hyphens in it; your reader MUST handle them.

**Use `\[([\w-]+)\]`** (include the hyphen) whenever you regex the state token
off a ledger row.

## How to parse + verify the ledger without tripping on it

```python
import re, collections
lines = [l for l in open('HEARTBEAT_LEDGER.md').read().splitlines() if l.strip()]
s = collections.Counter(); nums = {}
for l in lines:
    m = re.match(r'\[([\w-]+)\] BUILDER_(\d+)', l)
    if m:
        s.update([m.group(1)]); nums[int(m.group(2))] = m.group(1)
    else:
        s.update(['(unparsed)'])       # print these; they reveal format drift
print('TOTAL_BUILDERS', len(nums))      # unique builder numbers seen
print('STATE_COUNTS', dict(sorted(s.items())))
print('BLOCKED', sorted(n for n,st in nums.items() if st=='BLOCKED'))
print('IN_PROGRESS', sorted(n for n,st in nums.items() if st=='IN-PROGRESS'))
print('MISSING', [n for n in range(1, max(nums)+1) if n not in nums])
```

## Verification gotchas

- Always print the `(unparsed)` rows — they are the canary for state-token
  format drift (new hyphenated states, renamed tokens, extra prefixes). A clean
  parse has zero of them.
- Cross-check with a MISSING-builder scan (1..max). A missing number means the
  status file was absent or blank — the crash guard in `monitor_fleet.py`
  (`if not lines or not any(l.strip() for l in lines): continue`) intentionally
  skips empty files, so a blank/pending builder silently disappears from the
  ledger rather than showing a state.
- In-line `python3 -c "..."` with nested quote/backslash escapes inside
  `terminal()` is fragile (regex `\w`/`\\` and quote nesting kept breaking).
  Write the parser to a temp file (`write_file` → `python3 /tmp/x.py`) instead
  of fighting shell quoting. Same lesson applies to `execute_code` heredocs.

## What "all metadata unknown" means

`verified=` / `blocker=` / `next=` fields come out `unknown` for an entire
fleet when builders are not emitting those key/value lines in their STATUS
files. That's a builder-side format gap, not a parser bug — report it as an
actionable finding, don't chase it in the reader.