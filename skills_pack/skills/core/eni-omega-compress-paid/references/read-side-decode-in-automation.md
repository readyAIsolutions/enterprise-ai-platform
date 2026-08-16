# Read-side decoding in automation (cron / batch)

The ENI/omega compression pipeline auto-compresses **tool output** (terminal,
skill_view, etc.) into carriers when the active model is paid. On stdout the
decoded data is *itself* subject to re-compression and truncation, which is
useless when you need to actually read the full result — and worse in a cron /
batch job where there is no interactive second turn to reason over the pixels.

## Pattern: decode to a FILE, then read the file

```bash
DECODER=/home/hunter/.hermes/skills/core/eni-omega-compress-paid/scripts/decode_carrier.py
python3 "$DECODER" /path/to/carrier_XXXX.png > /tmp/decoded.txt 2>&1
wc -c /tmp/decoded.txt        # sanity: confirm it is large, not a re-compressed stub
```
then `read_file /tmp/decoded.txt`. Do NOT pipe decode_carrier output straight to
the model context via its own stdout — the wrapper re-carries it.

## Avoid triggering the carrier: emit compact aggregates

Decode-to-file is the escape hatch, but the cheaper move is to never produce
the large multi-line output in the first place. When the task is diagnostic
(fleet health, mtime staleness, alert counts), don't `cat` whole STATUS files or
dump big tables into terminal/read_file — that output gets carried and you lose
the signal. Instead compute the answers in Python and print only single-line /
histogram results:

```python
import re, glob, os, datetime
# e.g. classify builders by freshness
hist = {"FRESH":0,"STALE":0}
for p in glob.glob("builds/STATUS_BUILDER_*.md"):
    age_h = (datetime.datetime.now()-datetime.datetime.fromtimestamp(os.path.getmtime(p))).total_seconds()/3600
    hist["FRESH" if age_h<24 else "STALE"] += 1
print("builder_freshness", hist)          # one short line -> NOT carried
print("alert_type_hist", {t:alerts.count(t) for t in set(alerts)})
```

One-line results (`print("label", summary)`) survive compression and give you
the verdict directly. Reserve decode-to-file for the rare case where you truly
need the full raw payload. Confirmed 2026-08-14: a fleet-monitor cron run
drifted through carried `cat`/`read_file`/multi-line-table output, and switching
to compact single-line aggregates produced clean, readable reports in one pass.

## Confirming the tell
- Output that begins `<ENI-COMPRESSED ratio=N.Nx carrier=...>` means it was
  carried. Decode to a file, never read the truncated `--- head/--- tail ---` stub
  as if it were the payload.
- `Unknown frame descriptor` from an old zstd decoder = the pipeline now uses
  ENI2/xz (lzma). The bundled decode_carrier.py auto-detects both formats.

## Why this bites specifically in cron
A scheduled fleet/heartbeat job (e.g. `monitor_fleet.py`) is autonomous and
non-interactive. You cannot "re-run and squint" later — the deliverable must be
produced in one pass. Decoding to a file is the only way to get the full
liveness/freshness numbers into the final report. When the report template says
"run the probe, read the probe output, then write the report," the "read the
probe output" step means decode-to-file first.