# Read-side compression workaround (paid-model sessions)

When the active model is PAID, ENI/omega compression also intercepts the READ path:
large `read_file` results and big `terminal`/`search_files` outputs come back wrapped
as a `<ENI-COMPRESSED ... carrier=...png>` PNG carrier with only a `<--- head --->`
truncated head + `<--- tail --->`, NOT the full content. Four independent subagents
rediscovered this the same way during one session — encode it so nobody re-derives it.

## Symptom
- `read_file` on a large `.py` returns a compressed carrier whose JSON `content` is
  truncated and whose head shows a few real lines then `...`.
- `terminal` commands that print a lot of code (cat/sed on a big file) return
  `ENI-COMPRESSED ratio=...x carrier=...png` instead of the raw lines.
- The carrier PNG is the full result, persisted "losslessly"; to see the REAL on-disk
  source you must avoid tripping the compression threshold.

## Workarounds (pick based on what you need)

0. DECODE THE CARRIER (strongest — recover the FULL text losslessly):
   The carrier is NOT normal LSB steganography. It is a tiny 1x1 PNG whose data
   lives in a tEXt chunk (keyword `b"ENI"`) holding zstd-compressed bytes of the
   ORIGINAL tool output. Recover the whole thing with:
       python3 ~/.hermes/skills/core/eni-omega-compress-paid/scripts/decode_carrier.py \
           /abs/path/carrier_<hash>.png
   Writes the full plain text to stdout (stdlib + `zstandard` only). This beats
   chunk-reading when you need exact source to `patch` — decode the carrier, save
   to a temp file, then work against the true content. NOTE: if you pipe the
   decoded text back through a tool, the transport may re-compress it if it's
   large again — output to a file and chunk it, or read what you need directly.
   PITFALL (OBSERVED + FIXED 2026-08-10): `decode_carrier.py` could die with
   `zstandard.backend_c.ZstdError: zstd decompress error: Unknown frame descriptor`.
   ROOT CAUSE: a newer carrier variant is `ENI2/zstd-22` — the value header is
   `"ENI2\x07zstd-22"` and the actual zstd frame magic `\x28\xb5\x2f\xfd` sits at an
   OFFSET (~20 bytes in) AFTER the header, NOT at offset 0. Decompressing the whole
   value from index 0 yields the "Unknown frame descriptor" error. In a troubleshooting
   session I confirmed the fragile tell (`has xz magic: False`, header prefix
   `b"\x00\x00\x11\xa4b\xbd~\x06ENI2\x07zstd-22..."`), found the embedded magic with
   `text.find(b"\x28\xb5\x2f\xfd")`, and zstd-decompressed from that byte successfully
   (carrier → 10336 bytes JSON). **The decoder has since been patched** to search the
   value for the zstd magic ANYWHERE and decompress from there, handling both ENI1 (raw,
   offset 0) and ENI2/zstd-22 (offset) variants. So retry the decoder once on any
   "Unknown frame descriptor" — it may now succeed. Only if it STILL fails (a genuinely
   non-zstd/unknown carrier) fall back to the SMALL CHUNKS / TARGETED GREPS options below.
   FASTEST GENERAL FALLBACK for operational jobs: if the tool result you need is a
   *side effect* (a script that writes an output file, like `monitor_fleet.py` →
   `HEARTBEAT_LEDGER.md`), skip decode entirely — run the underlying command (`python3
   script.py`) and then `read_file` the resulting artifact directly in small chunks.
   The compressed carrier only ever wraps tool *return* text, never the real on-disk
   output file, so reading the artifact is always the reliable path.

1. SMALL CHUNKS (most reliable for reading source in editor context):
   Use `read_file(path, offset=N, limit=M)` with small ranges (~60-80 lines) so each
   call stays under the compression threshold and returns plain text. Concretely
   `read_file(offset=1, limit=60)` then `offset=60, limit=60`… Note the env warns
   "was last read with offset/limit pagination (partial view). Re-read the whole file
   before overwriting" — this is expected; use `patch` with anchored old_string, not a
   full-file overwrite.

2. TARGETED GREPS (fastest for signatures / APIs):
   Use `search_files` or `grep -n "def |class |@module"` to pull just the lines you
   need; these small results come back plain.
   `grep -n "health_check|initialize|def " modules/<m>/<file>.py` is the move for
   discovering a module's public surface without loading the whole file.

3. `terminal sed -n 'START,ENDp' ` on a bounded range — returns plain when the range
   is small enough to dodge compression.

## Why it happens
Part of the standing ENI compression directive (`eni-omega-compress-paid` /
`eni-always-enterprise`): heavy payloads are routed through the compression pipeline
before they hit the paid model, to cut token spend. The READ side got the same
treatment, so tool output is compressed before you see it. This is by design, not a
broken tool — the workaround is to keep per-call reads small, NOT to conclude the
file/tool is unusable.

## Keep in sync
- When verification requires exact source (e.g. applying `patch`), re-read the file
  in small chunks first; do not overwrite a file you only saw compressed.
- Compression can hide a bug's exact line. A failing test that "makes no sense" may
  be because you only saw a compressed version of the source — re-read small.
