# Reading files/terminal output when the display layer compresses large text

## The quirk (workspace-wide, permanent — not a transient failure)

On this box, the tool-output layer runs large text results through ENI
compression. When a single output (from `read_file`, `terminal` cat/sed/grep, or
`skill_view`) exceeds a size threshold, the tool returns a shortened
`<ENI-COMPRESSED ...>` block with only a `--- head ---` / `--- tail ---` JSON
summary plus a `carrier=<...>.png` path — NOT the full text. The source file
itself is plain UTF-8 on disk (verified with `file` + `xxd`); only the display
layer is compressing what you see.

## Consequences

- You cannot recover the middle of a large file by re-reading it; every large
  read comes back truncated to head+tail.
- Large terminal multi-line outputs (e.g. `sed -n '1,220p'`) get compressed too.
- Tempting rabbit hole to AVOID: decoding the carrier PNG (the `eni-decompress`
  / `core.engine.decompress` path is fragile — often "cannot load this image"
  because the decoder needs the exact IMPOSSIBLE-mode pipeline and matching
  paths). Don't go there to read a source file.

## The fix: read in small chunks

Keep each read small enough to stay under the compression threshold so it comes
back verbatim. On this box ~70 lines per call is reliably safe:

```
sed -n '1,70p' file.py      # then 71,140 ; 141,210 ; ...
```

- Small files (like a 76-line `__init__.py`) come through whole — no chunking
  needed.
- To map a big file fast, chunk once by grep'ing structure first
  (`grep -n "^class \|^def "`), then read only the sections you need in chunks.
- `read_file` paging (offset/limit) can also work but its outputs are still
  subject to the same display compression per page — keep each page small.
- Tiny ~20-line outputs are always safe.

## Verify you're seeing everything

Before trusting a read, sanity-check against what you expect: the function
definitions / imports you need are actually present, and there's no
`--- tail ---` truncation marker. If you only needed the public API, the chunk
with the `__init__` imports + `__all__` often suffices without reading the whole
implementation.
