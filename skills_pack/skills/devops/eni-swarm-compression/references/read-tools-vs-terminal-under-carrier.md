# Reading file contents when ENI carrier-compression wraps tool output

## Symptom
In `execute_code`, a call like `terminal("cat FILE | head -N")` (or any
`terminal()` whose stdout is large / ENI-compressed) can fail with:

```
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

The ENI carrier wrapper compresses the tool's stdout into a carrier PNG and
replaces the raw output, so `json.loads()` on the tool result sees the wrapper
marker, not JSON. `skill_view` output itself may arrive carrier-wrapped too
(`--- head ---` / `--- tail ---` with `ratio=…x carrier=…png`).

## Reliable fix
Read file contents with the **`read_file` tool** (or `search_files` for
grepping), NOT with `terminal cat/head/tail`. `read_file` returns clean,
decompressed content directly and is not subject to the carrier wrapper.

Pattern that worked (fleet-monitor session):
- `terminal("cat … | head")` inside execute_code  -> JSONDecodeError.
- `read_file(path)` (the tool) for the same files  -> clean content.

## Secondary signals to look for
- A `terminal()` command succeeds (exit_code 0) but the result dict is empty /
  unparseable even though the shell clearly produced output.
- Log/status files you know exist return blank or get "Expecting value" errors
  only when read via `terminal`, but read fine via `read_file`.

## When terminal IS still needed
- For commands with side effects (running scripts, `ps`, `ls`, launching).
- If you must parse command output under the wrapper, disable the output hook
  with `env -u PYTHONPATH` in front of the command (kills the ENI hook), or use
  `sed`-chunked windows / `scripts/recover_carrier.py` (see `references/recovering-eni-carriers.md`).
