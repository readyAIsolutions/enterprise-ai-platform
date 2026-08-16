# STATUS-file parsing across the DEMIURGE swarm

Reusable technique for any mini that must **READ / AGGREGATE** sibling
`STATUS_*.md` files — a board builder (`report_builder.py`), MASTER's
contextual reader, or a gate reporter. Authored from the DEMIURGE_B09
`report_builder.py` build (2026-07-11). Pure stdlib `re`, no pandas/sklearn
(so it runs in the lean AppImage venv).

## Why it is non-trivial
The swarm's STATUS files do **NOT** use one uniform state declaration. Across
the real scaffold, state is declared in at least six spellings. A naive
`[state: X]` parser mislabeled ~17/44 modules as UNKNOWN. After handling all
six, UNKNOWN dropped to 9 and the actionable BLOCKS list went from 20+ noise
items to 5.

## State-declaration spellings observed (handle ALL)
1. `[state: DONE]`              — line 1 (the canonical contract from the protocol)
2. `[DONE] ...`                 — bare bracket, no `state:` prefix (paragraph opener)
3. `# STATUS: IN-PROGRESS`      — hash + `STATUS:` + known-state word
4. `STATUS: **DONE (note)**`    — inline, optional `**` bold, optional parenthetical
                                  note, with OR without a leading `#`
5. `> Status: DONE (...)`       — markdown blockquote-prefixed (`>` then `Status:`)
6. `## VERDICT: [DONE]`         — a `VERDICT:` heading whose word is
                                  DONE/VALIDATED/COMPLETE

Distinct from build state — the **deploy-gate verdict**:
- `**VERDICT: RED — ...**` / `**VERDICT: GREEN — ...**` => gate verdict
  (GREEN/RED), carried SEPARATELY from the builder's build state.

## Regex recipe (stdlib `re`)
```python
import re
BARE_BRACKET = re.compile(
    r"^\s*\[\s*(DONE|IN-PROGRESS|IN_PROGRESS|BLOCKED|BLOCKER|RED|GREEN|"
    r"VALIDATED|COMPLETE)\s*\]", re.I | re.M)          # re.M: bracket is rarely line 1
INLINE_STATUS = re.compile(
    r"(?:^|#\s*)(?:>\s*)?STATUS\s*[:—–-]\s*\*{0,2}\s*"
    r"(DONE|IN-PROGRESS|IN_PROGRESS|BLOCKED|BLOCKER|RED|GREEN|"
    r"VALIDATED|COMPLETE|MISSING|IN_FLIGHT)\b", re.I | re.M)
VERDICT_ANY = re.compile(r"verdict:\s*\[?(\w+)\]?", re.I)
```
Dispatch priority (first match wins):
1. `STATE_BRACKET` `^\[state:\s*(\w+)\]` on line 1
2. `BARE_BRACKET.search(txt)`                         (re.M — searches every line)
3. `STATE_HASH` `#\s*STATUS\s*[:—–-]\s*(\S+)` where token in KNOWN_STATE
4. `INLINE_STATUS.search(txt)`
5. `VERDICT_ANY.search(txt)` -> DONE/VALIDATED/COMPLETE => build-state DONE;
   GREEN/RED => gate verdict (NOT build state)
6. last-resort inline `state:` word

Normalize tokens: VALIDATED/COMPLETE/ACTIVE/LIVE => DONE; IN_PROGRESS/INFLIGHT =>
IN_PROGRESS; BLOCKER/HALTED => BLOCKED.

## CRITICAL nuance — a RED-verdict QUOTE must not re-flag a DONE module
A module that declares `[state: DONE]` and merely *quotes* another module's
`VERDICT: RED` (the project-wide "no broker until gate green" rule) is BUILT.
Do NOT treat its quoted RED verdict as "this module needs attention."
Rule: a RED gate verdict hard-flags attention ONLY when the module has NO
declared build state (state == UNKNOWN/""). If a build state is known
(DONE/IN_PROGRESS/BLOCKED), the RED verdict is a project-level fact, not this
module's backlog.
Likewise DONE/GREEN modules carrying FAIL/BLOCKER/UNVALIDATED cells in their
evidence board (real-data-pending notes) must NOT flood the attention list —
only IN_PROGRESS modules with failing cells, and hard BLOCKED/RED/MISSING
states, do.

## Duplicate STATUS files — dedupe by module stem
`glob('**/STATUS*.md')` returns the SAME module from `root/`, `status/`,
`swarm/*/`, AND `build/AppDir/usr/share/demiurge/**` (stale packaging copies).
Collapse by stem (strip `STATUS_` prefix) keeping the RICHEST record. Rank:
`(known_state?1:0, verdict_cell_count, preferred_root/status > swarm > build,
-path_len)`. `build/` copies are stale => lowest preference. Without dedupe the
board shows duplicate module rows.

## Python pitfall — `@property` fields vanish from `dataclasses.asdict()`
If your record class carries a computed `@property` (e.g. `needs_attention`)
used in logic, `asdict(rec)` DROPS it (only real fields survive). Debugging
`board["modules"]` via the dict will `KeyError` on the property. Iterate the
OBJECTS (`for r in records: r.needs_attention`) when testing computed props;
serialize only real fields to JSON.

## Verdict-cell counting (PASS/FAIL board numbers)
Count verdict words in markdown tables AND inline prose. A cell that is exactly
`PASS`/`FAIL`/`BLOCKER`/`WARN`/`UNVALIDATED`/`RED`/`GREEN` counts directly;
otherwise run an inline `re` with look-arounds `(?<![\w/])...(?![\w/])` so
`PASS/FAIL` section HEADINGS and words like `FAILURE` don't inflate counts.
`**PASS**` and `FAIL (horizon)` both count; `VALIDATED` (in `VERDICT:
[VALIDATED]`) is a distinct token from `UNVALIDATED`.
