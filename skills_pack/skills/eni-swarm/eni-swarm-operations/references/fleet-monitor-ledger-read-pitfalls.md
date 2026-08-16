# Fleet Monitor — ledger-read pitfalls (state parsing + stale-partial reads)

Gotchas discovered running the `monitor_fleet.py` cron. Apply to the other
fleet-monitor references (ledger, diagnostic-one-liners, concise-summary).

## Verifying a builder is present in the ledger: anchor on the `[STATE] ` prefix, not `N=`
Ledger rows are `[DONE] BUILDER_4 verified=...` — `verified=` is whitespace-separated, so
`grep "BUILDER_${N}="` (or `grep "BUILDER_${N}=" HEARTBEAT_LEDGER.md`) false-negatives **every**
builder (each row reports MISSING). Use the bracketed-state prefix instead:

```bash
# per-builder presence check (matches '[DONE] BUILDER_4 verified=' etc.)
grep -q "^\[[A-Z-]*\] BUILDER_${N} " HEARTBEAT_LEDGER.md && echo "present" || echo "MISSING"

# reliable row count (NOT wc -l — see below)
grep -c '^\[.*\] BUILDER_' HEARTBEAT_LEDGER.md
```

Also: `wc -l HEARTBEAT_LEDGER.md` can undercount by 1 vs `grep -c` when the file has no trailing
newline (observed 48 vs 49). For row counts trust `grep -c '^\[.*\] BUILDER_'`, not `wc -l`.

## 1. Python state counting: use `\[([^\]]+)\]`, NOT `\[(\w+)\]`
`IN-PROGRESS` contains a hyphen, so a `\w+` capture group stops at the `-` and
`re.match(r"\[(\w+)\]", line)` returns `None` → `AttributeError: 'NoneType'`.
The ledger has real `[IN-PROGRESS]` and `[BLOCKED]` rows, so this is not a bound
case. Robust count:

```python
c = Counter()
for l in rows:                      # rows filtered to startswith('[')
    m = re.match(r"\[([^\]]+)\]", l)   # captures 'DONE'/'IN-PROGRESS'/'BLOCKED'
    if m: c[m.group(1)] += 1
```

## 2. Stale-partial read trap: never trust a single `cat` on a file the cron rewrites
The ledger is *recreated* (open `"w"`) on every `monitor_fleet.py` run. Reading it
once at T0 can give a stale/mid-write picture. If the numbers look wrong, re-read
and `stat -c '%y'` the file before concluding. A freshly regenerated ledger with
the expected builder count is the signal it ran clean.

## 3. Zero-padded STATUS filenames map to unpadded builder numbers
`STATUS_BUILDER_05.md` (zero-padded, 2-digit) parses as **BUILDER 5**, NOT a
separate/`05` builder. `monitor_fleet.py` does `re.search(r"STATUS_BUILDER_(\d+)\.md")`
so the `05` → `5` collapse is expected and correct. When investigating "missing"
or "duplicate" builders, ALWAYS check the zero-padded spelling first:
```
ls builds/ | grep -E "BUILDER_5\.md$|BUILDER_5[^0-9]"   # distinguishes 05 from 50/5x
```
`BUILDER_5` appearing in the ledger with no obvious `STATUS_BUILDER_5.md` on disk is
NOT an inconsistency — the file is `STATUS_BUILDER_05.md`. Don't burn time treating
it as a ghost entry.

## 4. Empty STATUS file = crash-guard skip, not a builder error
`monitor_fleet.py` skips empty/blank STATUS files (`if not lines or not any(...)`).
So a builder whose file is 0 bytes produces **no ledger row at all** — that's the
crash guard working, not a swallowed builder. Count `STATUS_BUILDER_*.md` files vs
ledger rows: a shortfall of exactly the number of empty files is expected. Detect
empties with:
```
for f in builds/STATUS_BUILDER_*.md; do [ ! -s "$f" ] && echo "EMPTY: $f"; done
```
Don't report the gap as a monitoring bug.

## 5b. `[IDLE]` builders render as `[DONE]` in the ledger — read it as "waiting", NOT "completed"
`monitor_fleet.py`'s state mapping only special-cases `BLOCKED` and `IN-PROGRESS`; every
other state (including `[IDLE]`, which is what most healthy-but-unassigned builders write)
falls through to the `else` → `DONE` branch. So a ledger full of `[DONE]` rows does NOT mean
41 builders finished tasks — it almost always means 41 builders are **IDLE, waiting for
PRODUCT_LEAD/master dispatch**. The ledger is a *liveness* summary, not a completion ledger.
When interpreting: `DONE` ≈ "alive & idle", `IN-PROGRESS` = genuinely working, `BLOCKED` =
stalled. The actionable signal for a mostly-DONE fleet is "fleet healthy but under-dispatched",
not "work is complete". (Confirmed: 50/50 STATUS files on disk, 41 mapped to DONE, all showing
`[IDLE]` / "waiting for task assignment" in their first lines.)

## 5c. Transient mid-rewrite read: file present in glob but `FileNotFoundError` on open
A builder actively rewriting its STATUS file can make it vanish for a few ms: the
`glob` sees it (so it appears in the file list / ledger count) but `open()` raises
`FileNotFoundError` (errno 2). This is NOT a ghost builder and NOT a persistent gap — it is
the builder's own atomic-replace-in-progress. Retry the read once or twice with a short
`time.sleep(0.5–1)` before concluding the file is gone. Distinct from the stale-partial trap
in #2 (which is about reading a *stale copy*); here the file is genuinely absent for an instant
and reappears on retry.

## 5. Don't reconstruct the skill's script path from the skill name
`fleet_monitor_pass.py` lives in a NESTED dir. Do NOT reconstruct the script path
from the skill name as `/home/hunter/.hermes/skills/eni-swarm-operations/scripts/…`
— the `eni-swarm` category adds a level, so the real install path is:
`/home/hunter/.hermes/skills/eni-swarm/eni-swarm-operations/scripts/fleet_monitor_pass.py`.
Guessing the flat path yields `FileNotFoundError` (errno 2). The reliable way to
locate it is `search_files(pattern="fleet_monitor_pass.py", path="~/.hermes")` (or
use `skill_view`'s linked-files list), never by blind path construction from the
skill name.

## 6. Silent `read_file` dedupe → false "0 rows" — count the ledger from disk, not the reader
If the ledger was read once already, a second `read_file` returns
`{"status":"unchanged"}` with **no content**. Regex-parsing that yields
`STATE_COUNTS: {}` / `TOTAL_ROWS: 0` and you wrongly conclude the ledger is
empty/broken. Terminal `cat` output is likewise unreliable because a large ledger
gets wrapped in an `<ENI-COMPRESSED>` block that elides the middle rows. Robust
pattern: write a small standalone script to `/tmp` and run it, opening the ledger
**directly from disk**:
- `write_file /tmp/parse_ledger.py` → `open("<ledger>").read()`, then
  `re.match(r"\[([^\]]+)\]", line)` / `Counter` for states; print counts + the
  specific BLOCKED/IN-PROGRESS numbers.
- `terminal("python3 /tmp/parse_ledger.py")`.
Do NOT inline the parser via `python3 -c "<json.dumps(code)>"` — the JSON-escaped
body arrives as literal `\n` characters and raises
`SyntaxError: unexpected character after line continuation character`. A real
`.py` file sidesteps both the dedupe and the escaping trap.

## 7. Trust mtime over the `[STATE]` text marker — stale header line corrupts parsing
Many STATUS files carry an identical leftover first line (e.g.
`[BLOCKED] STATUS_BUILDER_46 — Sat Jul 25`) — residue from a template/overwrite.
`monitor_fleet.py` scans a file top-to-bottom and breaks at the FIRST marker it
matches, so that stale header can make files parse as BLOCKED/IN-PROGRESS
regardless of their real content, and consecutive files can show wildly
inconsistent text markers (`BUILDER_37` => DONE while `BUILDER_46` => BLOCKED,
both starting with the same header). Do not treat `[STATE]` tokens as a liveness
signal. Cross-check with `stat -c '%Y' builds/STATUS_BUILDER_*.md`: if every
IN-PROGRESS/BLOCKED file is hours-to-weeks old (e.g. all ~510h stale), the markers
are stale and the fleet is DORMANT — report that, not the claimed states.
