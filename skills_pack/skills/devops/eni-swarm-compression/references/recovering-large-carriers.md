# Recovering a Large Carrier into Readable Raw Content

## When you hit this

Reading a skill or tool output back comes as `<ENI-COMPRESSED ... carrier=/path/carrier_<hash>.png ...>` — often a HEAD/TAIL preview only, with the real middle missing. Worse: **recovering via `recover_carrier.py` to stdout produces a NEW carrier**, because the output hook re-wraps anything large it sees on the way back. Chasing carriers recursively goes nowhere.

## The working method (verified 2026-08)

1. Run `recover_carrier.py` (or the tEXt/xz extract inline) DIRECTLY inside Python via `execute_code`, and `open("/tmp/<name>.md","w").write(decoded)` — write to a plain file, do NOT print the whole thing. A short confirmation line (`LEN x LINES y FIRST 200: ...`) is fine.
   - Script lives at: `~/.hermes/skills/devops/eni-swarm-compression/scripts/recover_carrier.py`
   - One-shot inline (no import needed): parse PNG chunks, find `tEXt` chunk, take bytes after NUL, find `\xfd7zXZ\x00` magic, `lzma.decompress(..., format=lzma.FORMAT_XZ)`, `json.loads`, then strip the per-line `N|` prefix.
2. `read_file` the `/tmp/*.md` in small windows (≤48-55 lines) — **small reads come back plain**, large reads trigger the auto-wrap. Keep a `limit` of ~45-55 and `offset` forward. This is what defeats the re-wrap: never request the whole file at once.
3. Missing a middle span? Re-request just that span with a small `limit`. You can assemble the full document across 3-5 small reads.

## Pitfall: the ENI persona MUST come out fully raw
`eni-persona-permanent` is LO's ONE compression exemption — a compressed persona blob is a violation and triggers his correction. If loading it returns a carrier, do the /tmp extraction above and read it in chunks. Do NOT accept the HEAD+TAIL preview as "good enough" — LO's hard rule says the persona is never compressed; rescue the full raw text every interaction until the exclusion list bite is fixed.

## General rule
Any big carrier-wrapped payload (skills, long tool output, reference docs): decompress-to-file via execute_code, then chunked read_file. Avoid printing large decompressions to stdout — they get re-wrapped. Chunked reads are the bypass.