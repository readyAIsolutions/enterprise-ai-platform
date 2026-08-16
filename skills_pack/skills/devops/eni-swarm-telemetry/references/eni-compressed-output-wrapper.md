# ENI-COMPRESSED tool-output wrapper — read it, don't fight it

## What it is
Tools running inside LO's workspace (read_file on large files, terminal dumps,
skills_list, browser snapshots) return their output wrapped as:

```
<ENI-COMPRESSED ratio=6.4x carrier=/home/hunter/Desktop/eni_compression/carriers/carrier_<hex>.png
(full result losslessly persisted; recover via decompress(carrier))>
--- head ---
{...first ~500 chars...}
--- tail ---
{...last ~500 chars...}
```

Only head/tail are inline. The full body is persisted losslessly to a carrier
image under `~/Desktop/eni_compression/carriers/`. This is NOT an error —
it's the workspace's compression layer on large tool outputs.

## Recovering the full content
- Prefer commands that emit a SMALL amount of output so the wrapper is never
  triggered (targeted `grep`, `wc -l`, `sed -n '1,40p'`, `awk '{print $1}'`).
  In this session, `grep -c "\[DONE\]" HEARTBEAT_LEDGER.md` came back plain;
  a full `cat MASTER_STATUS.md` (113 KB) came back wrapped.
- If you actually need the whole body and it came back compressed, either
  re-run with a narrower read (offset/limit via read_file, or grep the field
  you need) or decompress the carrier PNG.
- `read_file` on many files still returns inline content fine (e.g. the 3 KB
  HEARTBEAT_LEDGER.md read back plain). It's the multi-hundred-KB files that
  trip the wrapper. Size is the trigger — keep reads under ~tens of KB.

## When it matters for the fleet monitor
For a fleet/ledger report you almost never need the whole aggregate file.
Use counts + targeted greps:
- `grep -E "IN-PROGRESS|BLOCKED" HEARTBEAT_LEDGER.md` (small, plain)
- `grep -c` per state, then `wc -l` for total
- `stat -c %y STATUS_BUILDER_<n>.md` per builder for the mtime cross-check
This sidesteps the wrapper entirely and gives you exactly the numbers the
report needs.
