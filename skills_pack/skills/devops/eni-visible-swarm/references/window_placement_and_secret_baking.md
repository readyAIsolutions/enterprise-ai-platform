# Window placement on X11 workspaces + baking secrets into generated scripts

## Placing xfce4-terminal windows on a specific workspace
`wmctrl -s N` (switch viewport) is UNRELIABLE for placing NEW windows — they land on the
launcher's current desktop, so a 4-workspace paint clusters everything on ws0/ws1.
RELIABLE: launch, then MOVE the existing window:

```bash
place() {
  local ws=$1 title=$2; shift 2
  "$TERM" "$@" </dev/null >/dev/null 2>&1 & disown   # launch detached
  local w=""
  for i in 1 2 3 4 5 6 7 8; do
    w=$(wmctrl -l 2>/dev/null | grep -F "$title" | awk '{print $1}' | tail -1)
    [ -n "$w" ] && break
    sleep 0.25
  done
  [ -n "$w" ] && wmctrl -i -r "$w" -t "$ws" 2>/dev/null
}
```
Verified on LO's box: `wmctrl -i -r <WINID> -t 2` moved a window ws0 -> ws2.

### Title must be UNIQUE + collision-proof
- `grep -F "MASTER:STOCKBOT_B1"` ALSO matches `MASTER:STOCKBOT_B10` (substring).
  Fix: zero-pad indices (B01..B12) so B01 != B10, OR match exactly with
  `awk -v t="$title" '$NF==t{print $1}'` (for no-space titles; for titles with spaces like
  "ENI HEARTBEAT (WS1)" grep the unique substring — WS1 is distinct from WS2..WS4).
- `wmctrl -l` reports the ACTIVE tab's title. At launch the FIRST tab is active,
  so grep the first-tab title (e.g. "MASTER:..."), not the second-tab title.

## Baking a secret (token/key) into generated shell scripts — two silent killers
Generated run-scripts (`cat > run_X.sh <<EOF ... EOF`) that need a secret:

KILLER 1 — nested double-quote syntax error:
  export TOK="$(grep '^TOK=' "$HOME/.env" | head -1 | cut -d= -f2-)"   # WRONG
  The `$(...)` sits inside a double-quoted string that itself contains `"$HOME/..."`.
  bash closes the OUTER double-quote at the inner `"`, so the rest parses as garbage ->
  "syntax error near unexpected token `)`" aborts the ENTIRE launch loop -> 0 proxies, no error seen.

KILLER 2 — `$VAR` ref corrupts to literal `***`:
  Writing `export TOK="$NEWKEY"` into a file via the agent's write_file tool
  mangles the `$NEWKEY` reference to a literal `***` in some contexts. Children inherit "***".

FIX (either):
  (a) Write the LITERAL secret value into the generated script
      (export TOK="<literal-value>") — literal strings survive write_file intact.
  (b) OR export it in the PAINTER's own environment; xfce4-terminal children INHERIT
      exported vars through the process chain, so the run-scripts need not set it at all.
  Either way: never use `$(...)` substitution with nested quotes, and never rely on a
  `$VAR` reference surviving a file write when the value is a secret.
