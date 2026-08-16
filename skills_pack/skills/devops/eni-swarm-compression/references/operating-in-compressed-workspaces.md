# Operating inside ENI-compressed workspaces (read + write)

Practical playbook for working on source files that live in an
ENI-compressed environment. The on-disk `.py` files are REAL, plain UTF-8
text — only the *tool I/O framing* (read_file / cat / sed output) gets
compressed into a head+tail view with the middle truncated. Two distinct
rules, one for reading and one for writing.

## Reading: chunk it small enough to pass through uncompressed
- Tool output (read_file, `cat`, large `sed` ranges) is ENI-compressed once
  it exceeds a size/line threshold. Results come back as
  `{"head": first ~30 lines, "tail": last ~12 lines}` and the middle is
  LOST from your context.
- Pass-through threshold observed this session: chunks of ~90 lines or less
  came back uncompressed; ~120-180 line chunks got compressed. Sweet spot:
  `sed -n 'a,bp' file` with (b-a) <= ~90, iterating down the file.
- Keep a mental map of each file with `grep -n "def \|class \|async def "`
  first, then `sed` the windows you actually need.

## Writing: ASCII-ONLY, or write_file silently corrupts the file
- `write_file` in this environment ESCAPES non-ASCII characters. Em-dashes
  (`—`), arrows (`→`), and curly/smart quotes in the content get mangled:
  quote characters become `\"`, newlines in strings become literal
  backslash-`n`. Result: the file fails to parse with
  `SyntaxError: unterminated string literal` even though `read_file` shows
  it looking normal.
- FIX: author every new file with pure ASCII (plain `-`, `->`, straight
  quotes `'`/`"`, no unicode punctuation). Triple-quoted docstrings with an
  apostrophe inside are fine — it is specifically NON-ASCII unicode glyphs
  that trigger the corruption.
- Always verify immediately after a write: `python3 -m py_compile <file>`.
  If it fails while reading back "fine", inspect raw bytes with
  `sed -n '<line>p' file | xxd` to see the escaped `\"`/`\n` sequences.
- The lint status on `write_file` output is a good first signal: a SyntaxError
  reported at write time means re-write ASCII-only.

## Decode key (recovering carrier payloads)
Carrier PNGs hide data as `PXPI`:
- 4 bytes magic `PXPI` + 4 bytes big-endian payload length + payload bytes
  + 4 bytes crc32, all embedded in the LSBs of RGB pixels
  (`r&1, g&1, b&1` per pixel, row-major; then 8 LSBs per byte).
- Payload is PAQ8-compressed (fallback zlib when the paq8 binary was absent
  at compress time). Decode = extract LSB bitstream -> parse header ->
  `zlib.decompress(payload)`, falling back to paq8 `-d` on failure.
- CAVEAT: on some boxes the carriers are 1x1 placeholder PNGs with no real
  pixel capacity — the actual source is the on-disk `.py` file, not the
  PNG. Check `file carrier.png` / dimensions before trusting pixels.
- A working manual decoder lives at
  `~/Desktop/Projects/ENI_Swarm/Compression/tools/decode_carrier.py`.
