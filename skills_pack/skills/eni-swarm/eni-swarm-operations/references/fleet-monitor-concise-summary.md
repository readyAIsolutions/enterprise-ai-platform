# Fleet Monitor — concise-summary technique (large-output SNAFU)

The `fleet-monitor-ledger.md` run pattern says to `cat`/`read_file` the full
ledger and all builder mtimes. On this box that BACKFIRES:

## The problem
Large terminal/execute_code outputs (full `HEARTBEAT_LEDGER.md`, `stat` of all
50 builder files, `cat` of several STATUS files at once) get auto-wrapped by the
environment into `<ENI-COMPRESSED>` blocks. The middle of the output is elided —
you see head + tail and LOSE the rows you need. Worse, `read_file` then dedupes:
a second read returns `{"status":"unchanged"}` instead of re-showing content, so
so you can't recover the truncated middle.

## Recovery path when output ALREADY arrives as an `<ENI-COMPRESSED>` carrier
The avoidance fix above stops *new* reads from being wrapped, but some tool calls
arrive **already compressed** regardless — most notably `skill_view` of OTHER
references (they go through the carrier pipeline because their content is long),
and multi-part `terminal` one-liners that batch several `cat`/`stat`/`ls` subcommands.
When you get the `<ENI-COMPRESSED ratio=…BNx carrier=…/carrier_<hex>.png …>` block,
you must DECODE the carrier — do not just work from head+tail (the body you need is elided) and do not re-run the same wrapped call (read_file may dedupe to `"unchanged"`).

Decode with the skill's script (auto-detects both carrier formats; see
`eni-omega-compress-paid` → `decompress(carrier)` as the in-repo alias):
```
python3 /home/hunter/.hermes/skills/core/eni-omega-compress-paid/scripts/decode_carrier.py \
    /home/hunter/Desktop/eni_compression/carriers/carrier_<hex>.png
```
The decoded JSON carries the original `content` key (head+tail are elided in the
preview line; the full body is inside `content`). Pattern: if the *output I need*
shows as an ENI carrier, decode it once and read the recovered `content` rather than
re-issuing the underlying command that produced it.
In a fleet-monitor `execute_code` pass, do NOT pipe every file through
`hermes_tools.read_file` — it caches and returns `{"status":"unchanged"}`
(which raises `KeyError: 'content'` in your script) on any SECOND read of a
file already seen this run. That burns a tool round and hides the data. Read
plain `.md`/ledger files straight in Python instead:
```python
with open(f"{BASE}/HEARTBEAT_LEDGER.md") as f:
    led = f.read()          # no dedupe, no KeyError, no compression wrapper
```
(`read_file` stays fine for source code and other non-repeat reads; the dedupe
is the trap for the fleet-monitor pattern where you touch the same file twice.)

## It also hits the skill's own support files
The same `<ENI-COMPRESSED>` elision applies when the cron session reads this
skill's REFERENCES/SCRIPTS via `skill_view` (or `read_file`, which then dedupes
to `{"status":"unchanged"}` on re-read). You get head+tail only and lose the rows
you need. Workaround that works reliably:
  1. Locate the true on-disk path, never assume it: `find /home/hunter -name
     "<support_file>"`. Note the skill lives under the category subdir
     `~/.hermes/skills/eni-swarm/eni-swarm-operations/`, NOT
     `~/.hermes/skills/eni-swarm-operations/`.
  2. For a re-runnable script, don't try to read/debug it — just RUN it directly:
     `python3 <on-disk path>/scripts/fleet_monitor_pass.py <workdir>`.
  3. For reference prose you must inspect, `find` the file then `read_file` the
     absolute on-disk path (bypasses skill_view's compression path).

## The fix — compute, don't dump
Don't try to print whole files. Parse inside `execute_code` and emit a tiny,
decided summary. Working pattern that survived the SNAFU:

- Count states: `re.match(r"\[([^\]]+)\]", line)` → `Counter`.
- Print ONLY non-DONE entries (other rows are noise).
- Freshness: `os.path.getmtime` every `STATUS_BUILDER_*.md`; bucket into
  live (mtime ≤ 2d) vs dormant; report oldest age in days. This catches
  "IN-PROGRESS" stubs that are actually 13-day-old orphans.
- Missing-file check via set difference:
  `ledger_ids = set(...) ; file_ids = set(...)` → `file_ids - ledger_ids`.
- `cd ... && cat <single file>` (one at a time) survives compression fine;
  it's the multi-file batch dumps that blow up.

## Pitfall — do NOT rely on `decode_carrier.py` to recover a compressed carrier
The `<ENI-COMPRESSED>` wrapper literally advertises "recover via
`decompress(carrier)`", but the bundled `scripts/decode_carrier.py` in
`eni-omega-compress-paid` is **not a reliable recovery path**. This session it
failed on the actual carrier with:
`zstandard.backend_c.ZstdError: zstd decompress error: Unknown frame descriptor`
The transport's compressor can be a different engine (paq8px / high-ratio)
than the zstd `.tEXt` chunk the script expects, so decoding blows up. Treat the
carrier as unrecoverable-read: the head+tail the wrapper DID show are your only
free visibility. Do not spend turns fighting the decode — pivot straight to the
compute-don't-dump strategy below (it's why we keep output tiny in the first
place).

## Prefer the terminal `awk`/`grep` one-liner variant
A second clean pattern that survives compression AND needs no execute_code:
run a single compact `terminal` command that composes `awk`/`grep`/`stat` into
a tiny decided summary. E.g. state counts via
`awk -F'[][]' '{c[$2]++} END{for(k in c) print k": "c[k]}' HEARTBEAT_LEDGER.md`,
then `grep -E 'IN-PROGRESS|BLOCKED'` for only the rows that matter, `wc -l` for
totals, and a `ps aux | grep -iE 'builder|swarm'` to see whether builders are
ACTUALLY alive versus just stale STATUS stubs. Because the output is tens of
lines, it stays unconpressed — same end goal as execute_code but greppable and
faster to write. Add `stat -c %Y <file>` age math (`age=$(( (NOW-mt)/60 ))`) for
the dormant-vs-live check batched across the handful of non-DONE builders only.

## Pitfall — parse the ledger via terminal `cat`, NOT `read_file`
Inside `execute_code`, do NOT feed `read_file` output into your state-parsing regex.
`read_file` returns each row with a `N|` line-number prefix, so `re.match(r"\[([^\]]+)\]", line)`
fails on every row and you get a bogus `{'?': 49}` counter. Worse, a second `read_file` of the
same file dedupes to `{"status":"unchanged"}`, so you can't recover. Use
`raw = terminal(f"cd <base> && cat HEARTBEAT_LEDGER.md")["output"]`, then strip any residual
`N|`/whitespace prefix with `l.strip().lstrip("0123456789| ").strip()` before `re.match`.
That yields clean `[STATE] BUILDER_n ...` rows for the `Counter`.

## Pitfall — write the execute_code import header cleanly; never inline-import
Use one top-of-script `import os, re, glob, time` (plus `from collections import Counter`,
`from hermes_tools import terminal`). Do NOT use `__import__("time")` inline inside the
loop/program — if you later reference the bare name `time` (e.g. `time.strftime(...)`) to
format an mtime, the inline `__import__` does NOT bind the module to the local name and you
get `NameError: name 'time' is not defined` mid-run, killing the whole parse. Reconstructed a
previous intact `time`/`os` binding partway through (e.g. `ages_day.append(os.path.getmtime(__import__("os")...))`)
but referencing it later is exactly how it breaks. Simplify: clean header, then read the
mtime once into a var and reuse that var. Also guard against `:)`-style zero-pad path bugs
by taking `n` from `re.search(r"STATUS_BUILDER_(\d+)\.md", os.path.basename(f)).group(1)`
inside the same loop where you read the file — never re-derive the filename by number.

## Pitfall — ledger count vs file count are NOT equal
`monitor_fleet.py` has a crash-guard that skips 0-byte/blank STATUS files, so the
ledger can have FEWER rows than `STATUS_BUILDER_*.md` files on disk. In this pass
BUILDER_20 was 0 bytes and correctly omitted — that is expected, NOT an anomaly.
When checking "is a builder missing?", verify the absent file is empty before
flagging it.

## Pitfall — ZERO-PADDED filenames: ALWAYS glob, never construct the path
STATUS files are named `STATUS_BUILDER_01.md` (single-digit IDs are zero-padded
with two digits) but `STATUS_BUILDER_46.md` (two digits are NOT padded). So if you
build the path by number — `f"STATUS_BUILDER_{n}.md"` — you get
`STATUS_BUILDER_5.md` → `FileNotFoundError` / `age=N/A` for every builder < 10.
This silently corrupts the age/freshness bucket. Fix: derive the real path from
the glob itself, never reconstruct it:
```python
for f in glob.glob(os.path.join(builds, "STATUS_BUILDER_*.md")):
    n = int(re.search(r"STATUS_BUILDER_(\d+)\.md", os.path.basename(f)).group(1))
```
(same zero-padding applies to the mtime cross-check — see fleet-monitor-ledger.md).
