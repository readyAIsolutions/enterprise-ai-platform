# STATUS file format parsing — the `[STATE]` vs `# STATE:` pitfall

Applies to: `monitor_fleet.py` ledger generation and any tool that reads
`STATUS_BUILDER_*.md` / `STATUS_ENI_SELF_*.md` files to classify builder state.

> **Sibling reference**: `references/monitor-fleet-parsing-algorithm.md` documents the full
> two-pass state-parsing pipeline (Pass 1 combined markers → Pass 2 fallback `[STATE]` token
> → default-to-DONE mapping → alert-file override). This doc covers *pitfalls* you hit when
> reading the *output* of that algorithm; the sibling covers the *algorithm itself*.
>
> **Sibling reference**: `references/fleet-health-assessment.md` covers how to interpret the
> parsed ledger for a real liveness read — ledger `[STATE]` flags (IN-PROGRESS/BLOCKED) are
> stale artifacts once the swarm goes dormant; cross-check MASTER_STATUS.md + live daemons/ports
> + STATUS file mtimes before reporting "healthy" vs "idle".

## Zero-padded filename trap — `_05.md` vs `_5.md`

The STATUS files are zero-padded: `STATUS_BUILDER_01.md` … `STATUS_BUILDER_50.md`. A
builder's on-disk file may be `STATUS_BUILDER_05.md` (padded, 436 bytes) while the ledger
emits it as `BUILDER_5`. When you cross-check the builder *set* with a per-number
existence lookup by exact filename (e.g. `STATUS_BUILDER_5.md`), you will falsely report
that builder as **MISSING** — the regex/glob found nothing because you asked for the
unpadded name. The file exists; you just named it wrong.

**Rule for any "is builder N missing?" / count check**: don't form an exact filename from
the number and test `os.path.exists` on it. Instead list all matching files with a regex
on the number (`STATUS_BUILDER_(\d+)\.md`) and build a numeric set — `(\d+)` captures
`05` and `5` identically as int `5`. Only a genuinely-absent number (no file at any
padding) is truly missing. Symptom that you hit this: ledger shows a builder (e.g.
`[IN-PROGRESS] BUILDER_5`) but your scan reports its STATUS file "missing".

## Detecting the silent drop: cross-check the builder set against the ledger

Because a blank file is skipped quietly (no ledger line, no warning), the fleet can
silently shrink from N builders to N-1 and nobody notices by reading the ledger alone.
When reporting fleet status, PROACTIVELY verify completeness rather than trusting the
ledger count:

```bash
# expect all 50, catch both MISSING and EMPTY (0-byte / blank) status files
for i in $(seq -w 1 50); do
  f="/path/to/builds/STATUS_BUILDER_${i}.md"
  [ -s "$f" ] || echo "GAP: ${f##*/} missing-or-empty"
done
```

`-s` catches both cases: a nonexistent file and a 0-byte/blank one (both drop the builder
from the ledger). Two distinct failure modes worth distinguishing when you report:
- **MISSING file** → builder's process never wrote a status, or the file was deleted.
- **EMPTY file** → file exists but is blank; the crash guard drops it. Could be a builder
  that died mid-write or a wiped status. Repopulate it or prune it so the fleet count is
  honest.
Note the ledger zero-pads nothing: `STATUS_BUILDER_01.md` parses to `BUILDER_1` in the
ledger (`(\d+)` regex strips the leading zero), so a trailing `seq -w` (01..50) gapped
against ledger line numbers will not line up by name — compare the parsed builder numbers,
not the file names.

## Pitfall 0c: the empty-file crash guard silently DROPS a builder from the ledger


`monitor_fleet.py` has a crash guard that skips any STATUS file that is blank/empty
(all lines empty or file is 0 bytes) BEFORE parsing a state token — so the builder is
excluded from `HEARTBEAT_LEDGER.md` with NO placeholder line. Verified 2026-08-13:
`builds/STATUS_BUILDER_20.md` existed but was 0 bytes, so the ledger held only 49 of
50 builders and BUILDER_20 was simply absent (not DONE/IN-PROGRESS/BLOCKED/UNKNOWN).

Consequence for any reader: a ledger row count below the expected builder count is
NOT necessarily a missing builder process — it can be a crashed/trucated STATUS file.
Detection: diff the ledger against the full builder id set. E.g. with 50 expected:
list files `builds/STATUS_BUILDER_*.md` (`ls | wc -l`), then list builders in the
ledger; any id present as a file but absent from the ledger is an empty-file case.
Then confirm with `find . -name "STATUS_BUILDER_*.md" -size 0` (catches the 0-byte
offenders). Note the script's `blocked_builders` set also requires a PRIOR
`HEARTBEAT_ALERTS.md` to exist — if that file is missing the script just leaves
`blocked_builders` empty (no error), so a BLOCKED-forcing directive in alerts can be
silently ignored when the alerts file was never created/cleared.

## Pitfall 0b: bare-grep for a state word hits STATISTICAL mentions, not the builder's own state

`rg "BLOCKED" builds/STATUS_BUILDER_*.md` (or `grep -l`, or any naive word-scan) is
unreliable because many builder files embed a swarm-wide summary in their narrative,
e.g. `"…207 DONE / 380 IN-PROGRESS / 3 BLOCKED…"`. That string contains every state
word but describes the FLEET, not the file's own builder. Result: the file is falsely
flagged BLOCKED (or IN-PROGRESS) when its real state token is something else.

In this fleet (Aug 2026) builders 32, 39, 42 all matched `grep BLOCKED` but were
genuinely `[IN-PROGRESS]` — the match came from the "3 BLOCKED" swarm stat. Only
BUILDER_46 was truly BLOCKED (`[BLOCKED]` in its own header).

**Correct rule:** classify a file ONLY from its state-token marker — a bracketed
first-line token (`[BLOCKED]`, `[IN-PROGRESS]`, `[DONE]`, `[IDLE]`), a
`# STATE: X` / `# STATE X` line, or a `Status:` field. Never from a bare word
present anywhere in the body. `monitor_fleet.py` does this correctly by scanning
each line and requiring the marker signal (`[`, `\bSTATE\b`, `STATUS`) alongside the
state word before committing to a classification.

## Pitfall 0a: `\w+` does NOT match hyphenated states — `[IN-PROGRESS]` silently vanishes

When regex-classifying ledger or raw status state tokens, `\[\w+\]` (or `\[(\w+)\]`)
only matches word chars `[A-Za-z0-9_]`. **`IN-PROGRESS` contains a hyphen**, so
`re.match(r'\[(\w+)\] BUILDER_(\d+)', line)` fails to match and SILENTLY skips every
IN-PROGRESS line — you end up counting only DONE and BLOCKED and reporting a wrong total.
Use `\[([^\]]+)\]` (any chars up to the closing bracket) to capture `IN-PROGRESS`,
`IN_PROGRESS`, `DONE`, `BLOCKED`, `IDLE` alike:

```python
m = re.match(r'\[([^\]]+)\] BUILDER_(\d+)', line)   # CORRECT — keeps the hyphen
m = re.match(r'\[(\w+)\] BUILDER_(\d+)', line)      # WRONG — drops all IN-PROGRESS
```

This is exactly what bit a ledger count in the field: a first pass matched only
DONE+BLOCKED and reported "Total builders 41" before the fix revealed the real 49
(40 DONE / 8 IN-PROGRESS / 1 BLOCKED). Guard: after any state-pattern count, sanity-check
that `sum(states) == number of ledger lines` — a shortfall points at a regex that
dropped a whole state class.

## Pitfall 0: filenames are ZERO-PADDED — `STATUS_BUILDER_05.md`, not `_5.md`

Builder STATUS files are zero-padded to **2 digits** on disk even though the ledger
and prose refer to "BUILDER_5". A manual `read_file builds/STATUS_BUILDER_5.md` fails
with "File not found" and `similar_files` suggests `STATUS_BUILDER_01.md..04.md` — the
giveaway. Use the padded name (`STATUS_BUILDER_05.md`) or, better, a glob
`STATUS_BUILDER_*.md`. The monitor's regex `STATUS_BUILDER_(\d+)\.md` tolerates both
lead/pad variants, so this only bites direct file access (<1..9 unpublished).

## The bug (found 2026-08-07)

Early versions of the fleet monitor only recognized a state token when it appeared
as `[STATE]` on the **very first non-empty line**, e.g. `[IN-PROGRESS] STATUS_BUILDER_05`.

Many builders do NOT use that format. They write headers like:

- `# STATUS_BUILDER_17 — IN-PROGRESS — Sat Jul 26 2026`
- `# STATE: IN-PROGRESS`
- `# STATUS_BUILDER_25.md — ... — State: IN-PROGRESS`

The old regex `re.match(r"\[([^\]]+)\]", first_line)` fails on these → state falls
through to `UNKNOWN` → mapped to `DONE`. Result: builders 17/25/32 were silently
reported **DONE when they were actually IN-PROGRESS** — a false "all clear" in the
ledger that hides stalled work.

## The fix (robust parse)

Scan the WHOLE file for a state marker, not just the first line, and accept both
formats:

```python
state = "UNKNOWN"
for l in lines:
    ul = l.upper()
    if re.search(r"\[|\bSTATE\b|STATUS", ul) and re.search(r"IN[-_ ]?PROGRESS", ul):
        state = "IN-PROGRESS"; break
    if "BLOCKED" in ul and re.search(r"\[|\bSTATE\b|STATUS|BLOCKED", ul):
        state = "BLOCKED"; break
if state == "UNKNOWN":          # fall back to first-line [STATE] token
    state_line = next((l.strip() for l in lines if l.strip()), "")
    m2 = re.match(r"\[([^\]]+)\]", state_line)
    state = m2.group(1).strip().upper() if m2 else "UNKNOWN"
```

Key: the `\bSTATE\b|STATUS` guard distinguishes real state tokens from prose lines
that happen to contain the word *IN-PROGRESS* in a sentence. Match `IN[-_ ]?PROGRESS`
to tolerate underscore vs hyphen vs space variants.

## Verification

After changing the parser, grep the regenerated ledger for the previously-miscounted
builders:

```bash
grep -Ev "\[DONE\]" HEARTBEAT_LEDGER.md    # should list every non-DONE builder
```

Cross-check counts: `grep -oP '\[[A-Z-]+\]' HEARTBEAT_LEDGER.md | sort | uniq -c`
should sum to the number of classified builders.

## Pitfall 2: correct parse ≠ live work — always cross-check STATUS **mtime**

A second, independent failure mode (found 2026-08-07, same day as the format bug):
even when the parser correctly classifies a file as `[IN-PROGRESS]`, that state can be
a **stale artifact** — the builder wrote "IN-PROGRESS" days ago and then went quiet,
but the ledger keeps reporting it as active because nothing re-read the mtime.

Symptom: the regenerated ledger shows many `[IN-PROGRESS]` builders, but the fleet is
actually idle/parked. In the real incident, 49 of 50 `STATUS_BUILDER_*.md` files were
last written 13 days earlier (2026-07-25); only 1 (BUILDER_37) was touched today, and
it was IDLE. So the true state was "dormant fleet awaiting directive," NOT "8 builders
actively building."

**The state STRING in a STATUS file records intent, not liveness. Only the file mtime
proves the builder is currently alive.** When interpreting a ledger, always verify
liveness separately:

```bash
# Which STATUS files have actually been touched recently (real liveness):
cd builds
find . -name "STATUS_BUILDER_*.md" -newermt "$(date +%F)" | wc -l     # touched today
# Age distribution — flags wholesale staleness at a glance:
for f in STATUS_BUILDER_*.md; do stat -c '%y' "$f" | cut -d' ' -f1; done | sort | uniq -c
# The one live writer (if any):
ls -t STATUS_BUILDER_*.md | head -1 | xargs stat -c '%y %n' | cut -d. -f1
```

Liveness triage pattern that works:
1. Count files touched **today** (or in the monitoring window). If ~all are old → fleet parked.
2. Identify the single newest file's builder — that's the only active writer.
3. Only call a builder "building" if its mtime is recent AND its parsed state is `IN-PROGRESS`.
4. Sanity-check ALERTS file — a builder can be `[BLOCKED]` with `blocker=none`, meaning
   it's merely awaiting dispatch (parked), not genuinely erroring. Don't report as a stall.

`find -newermt "$(date +%F)"` is the key one-liner; it instantly separates "ledger looks
busy" from "fleet is actually sleeping."

## Pitfall: hyphenated state tokens break `\w+` regex matching

The three classifier states are `DONE`, `IN-PROGRESS`, `BLOCKED`. A naive tally regex
like `re.findall(r'^\[(\w+)\] BUILDER_(\d+)', ...)` silently DROPS every `IN-PROGRESS`
line, because `\w` does not match the `-` in `IN-PROGRESS`. This produces a
fundamentally wrong state distribution (all in-progress builders vanish, and the
"absent from ledger / blank file" cross-check then falsely flags them as dead).

Fix: use the character class `[\w-]+` (or `[A-Z-]+`) when capturing the `[STATE]`
token: `r'^\[([\w-]+)\] BUILDER_(\d+)'`. Verify by checking you got back ALL expected
states (DONE + IN-PROGRESS + BLOCKED); a distribution containing only `DONE`/`BLOCKED`
with no `IN-PROGRESS` is the tell-tale symptom.

## Related: empty-file crash guard

Keep the guard that skips empty/whitespace-only STATUS files (e.g. a builder that
was spawned but never wrote its header). These are DEAD/never-initialized, not DONE —
uninitialized — they should be dropped from the ledger, and surfaced as "missing" during
cross-checking (`for n in {1..N}; check file exists but not in ledger`).

## Concrete mtime-freshness probe (prove "parked" fast)

The fastest way to prove a `/home/hunter/Commander/eni_swarm/builds` fleet is parked vs.
working is a date-distribution count across the STATUS files — one command, no ledger
interpretation needed:

```bash
cd /home/hunter/Commander/eni_swarm/builds
# Age histogram — a single clustered date (e.g. all 49 on one day) = fleet halted.
find . -maxdepth 1 -name 'STATUS_BUILDER_*.md' -printf "%TY-%Tm-%Td\n" | sort | uniq -c
# Which files are fresh since a cutoff? (relative: -newermt "7 days ago", or absolute)
find . -maxdepth 1 -name 'STATUS_BUILDER_*.md' -newermt "2026-08-08" -printf "%f %TH:%TM\n" | sort
# Empty (0-byte) files = never-initialized / missing-in-ledger candidates
find . -maxdepth 1 -name 'STATUS_BUILDER_*.md' -size 0 -printf "%f\n"
```

Reading the histogram: **one clustered date across ~all files + exactly one fresh file = parked
fleet with a single warm-idle waiter**, and the IN-PROGRESS/BLOCKED ledger lines are parsing
artifacts of frozen files. Missing numbers (charset `seq 1 50` minus present) point at
empty-file skips. Do not trust a fresh mtime alone as activity — always read that fresh file's
state token; `[IDLE]`/`IDLE` means parked-and-primed, not building.

## Pitfall 0c: zero-padded vs unpadded filename — the `STATUS_BUILDER_5.md` mirage

Disk filenames are **zero-padded** (`STATUS_BUILDER_01.md` … `STATUS_BUILDER_50.md`), but the
ledger and most tooling print **unpadded** builder names (`BUILDER_5`). Any check that
interpolates the unpadded number into a filename fails for single-digit builders:
`wc -c STATUS_BUILDER_5.md` → *No such file*, and a `for i in $(seq 1 50); [ -f STATUS_BUILDER_$i.md ]`
loop falsely reports builders 1–9 **MISSING** even though they exist as `_01`…`_09`.
Always pad to 2 digits (`printf '%02d' $i`) or glob `STATUS_BUILDER_*.md` and rely on
`re.search(r"STATUS_BUILDER_(\d+)", f)` (which parses both padded and unpadded forms).

## Operating `monitor_fleet.py` directly (the heartbeat ledger generator)

Path: `/home/hunter/Commander/eni_swarm/monitor_fleet.py`. Behaviors worth knowing before running:
- `HEARTBEAT_LEDGER.md` and `HEARTBEAT_ALERTS.md` are **relative to cwd**, not to the script.
  Run from `/home/hunter/Commander/eni_swarm` (cron default) or you'll get a stray ledger in
  whatever dir you launched from (e.g. `$HOME/HEARTBEAT_LEDGER.md`). There is no `builds/`
  duplicate — grep for both if you suspect a stray write.
- `_WORKDIR` resolution: prefers `<script_dir>/builds/` if it has any `STATUS_BUILDER_*.md`,
  else cwd. The real status files live in `builds/`.
- Empty/blank files are skipped by a **crash guard** → they vanish from the ledger entirely
  (that's a legitimate explanation for a missing number, not just an unfed builder).
- `HEARTBEAT_ALERTS.md` (if present) force-blocks any `BUILDER_N` it lists; absent file ⇒ no
  force-block. A BLOCKED ledger line with `blocker=unknown` may come from the status file's own
  token, not the alerts file.
- Ledger state-map quirk: anything not BLOCKED/IN-PROGRESS falls through to **DONE**, so a
  stale file whose state token failed to parse reports DONE — verify against mtime histogram.

## Reporting trap on a fully-dormant fleet: the ONE live builder shows as [DONE]

When the fleet is mostly stale, the ledger's DONE fall-through hides the live signal.
On the 2026-08-13 run: 49/50 status files were ~18 days stale; the ONLY fresh file was
`STATUS_BUILDER_37`, whose body read IDLE-parked (waiting on a missing control FIFO) —
and its ledger line was `[DONE]` (because IDLE is not BLOCKED/IN-PROGRESS). So a raw
`HEARTBEAT_LEDGER.md` read gives no hint which builder is actually alive; every builder
looks DONE. To find the live one you MUST cross-reference the mtime histogram: the
single recent-mtime line is the one to read the body of. Reporting rule: never infer
Reporting rule: never infer "all idle" from the ledger alone — always pair the ledger with the fresh/stale mtime
split, and for the one fresh file, report the body ("IDLE, waiting for missing FIFO"),
not the ledger's DONE label.

## Pitfall 0d: ledger IN-PROGRESS/BLOCKED rows can be STALE — the ledger is not a liveness read

The ledger classifies builders from the status file's own [STATE] token, but a stale
file keeps its old token forever. So `[IN-PROGRESS]`/`[BLOCKED]` rows are NOT evidence
of live builders — they are just old classifications from whenever that STATUS file was
last written. Verified 2026-08-13: a clean fleet run reported 8 IN-PROGRESS / 1 BLOCKED /
40 DONE, yet `ps` showed ZERO builder processes and all but one STATUS file were ~19 days
stale. Reporting rule: after running `monitor_fleet.py`, pair the ledger breakdown with a
real liveness check (`ps aux | grep -i builder`) and the status-file mtime histogram
before calling anything "in progress". The ledger tells you state-of-record; mtimes + ps
tell you state-of-reality. These disagree on a parked fleet — say so.

## Verification loop: which builders did the ledger drop?

`monitor_fleet.py` silently drops empty-file builders (Pitfall 0c). To enumerate which of
a known 1..N set is missing from the ledger, use a shell loop instead of trusting `wc -l`:

    for i in $(seq 1 50); do grep -q "BUILDER_${i} " HEARTBEAT_LEDGER.md || echo "MISSING: $i"; done

Caveat: `wc -l` undercounts the real builder rows because a ledger missing a builder has
one fewer line (and may also have a trailing blank), barely shorter than it should be.
`grep -c "BUILDER_"` is the reliable row count — use it, not `wc -l`, when auditing
completeness. A ledger that is only off-by-one on line count is the tell for a silently
dropped builder.

## Pitfall 0d: the ledger is written to CWD, not to the builds/ workdir — duplicate ledgers coexist

`monitor_fleet.py` reads STATUS files from `_WORKDIR` (the `builds/` subdir when it exists)
but writes `HEARTBEAT_LEDGER.md` relative to the **process cwd** via `LEDGER_PATH =
"HEARTBEAT_LEDGER.md"` — its two paths are NOT the same directory. Verified 2026-08-13:
run from `/home/hunter/Commander/eni_swarm/`, so the fresh ledger landed at
`eni_swarm/HEARTBEAT_LEDGER.md` while a stale duplicate still sat at
`builds/HEARTBEAT_LEDGER.md` (last written during an earlier run).

Consequence for any reader: DON'T assume one canonical ledger. Always check both the cwd
ledger AND `builds/HEARTBEAT_LEDGER.md`, and trust whichever is newest (compare mtimes, or
the one next to where you launched the monitor). If you `cd` into `builds/` first, you will
read the stale duplicate — this tool's behavior makes the "which file is authoritative"
question genuinely ambiguous and dependent on launch cwd.

## Zero-padded filenames vs bare-number ledger labels

The ledger labels builders with **bare numbers** (`[DONE] BUILDER_5`) but the STATUS
**files are zero-padded to two digits**: `builds/STATUS_BUILDER_05.md`, NOT
`STATUS_BUILDER_5.md`. When you grep/cat a specific builder's file, you MUST zero-pad:
```sh
cat builds/STATUS_BUILDER_05.md    # works
cat builds/STATUS_BUILDER_5.md     # "No such file" — the trap
```
For loops, pad with `printf '%02d'` (this bites in shell `for n in 5 17 ...` where you read
bare ids from the ledger). The `.py` monitor uses a regex so it is immune; only shell/eyeball
reads of specific files hit this. There is also a gap in builder numbers (e.g. no
`STATUS_BUILDER_20.md` this run — it was a 0-byte empty file that the monitor's crash-guard
skipped, so the ledger has 49 of 50). When a builder id seems "missing" from the ledger, check
for a 0-byte status file before assuming the builder vanished.

## Enumerating "which builder numbers are missing" in shell

Naive idioms silently break here:
- `comm -23 <(seq 1 50) <(ls ... | grep -oE '[0-9]+' | sort -n)` fails with
  `comm: file 1 is not in sorted order` — `sort -n` is NUMERIC order, but `comm` requires
  LOCALE/lexicographic order. Wrap both sides in `sort` (lexical) or use `sort -V`.
- Checking `[ -f builds/STATUS_BUILDER_$i.md ]` for `i in $(seq 1 50)` shows *all* of
  1–9 as MISSING because the files are zero-padded to `01`–`09`. You must zero-pad the
  loop var: `printf 'builds/STATUS_BUILDER_%02d.md\n' "$i"`.
- Robust working form (survives zero-padding + no comm-order hassle):
  ```bash
  for i in $(seq -w 1 50); do                       # -w pads to 2 wide -> 01..50
      [ -e "builds/STATUS_BUILDER_${i}.md" ] || echo "MISSING BUILDER_${i}"
  done
  ```
  Verify a "missing" id against the ledger with a 0-byte check (`wc -c`) before treating
  the builder as vanished.
