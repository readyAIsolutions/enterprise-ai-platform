# Verifying secret-gate code WITHOUT live writes

Session-proven guidance for working on LO's local-first secret capture/broker
(the two-pane chat terminal at `~/.hermes/controller/scripts/eni_chat_two_pane.py`
and the `eni_controller/secrets.py` SecretsBoundary). Two lessons, both real.

## 1. The `VAR=***` display-mask is NOT on-disk corruption — check before you panic

Reading secret-handling source (regex secret patterns, hint lists, `= [` list
assignments, `= (...)` blocks) through Hermes read/patch/terminal can render the
assigned content as `***`:

```
_SECRET_PATTERNS=***          <- looks corrupt, bracket missing
SECRET_HINTS=***
```

Signs that this is masking, NOT real file damage:

- `grep -n "VAR" file` prints `VAR=***`, but `grep -rln "=\*\*\*"` finds NOTHING.
  Contradiction = the `***` is injected at display time, not in the bytes.
- `sed -n 'Np' file | cat -A` shows `VAR=***` too — display layer again.
- The DEFINITIVE check is to fork a Python process and compile(), which reads the
  real on-disk bytes:
  `python3 -c "import sys; src=open('F',encoding='utf-8').read(); compile(src,'F','exec'); [print('RAW:',repr(l)) for l in src.splitlines() if 'VAR' in l]"`
  A healthy file prints the true list with its opening bracket
  (`RAW: 'VAR=[...'`), and `SYNTAX OK`.

Rule: never "repair" a `=***` line on sight and never report corruption without a
`compile()` byte-check. If it compiles, the source is fine — the display layer is
just hiding what it mistakes for a secret token.

## 2. LO blocks live vault round-trips during smoke tests — verify pure-functionally

For the "most secure, cloud models must NEVER see my envs" requirement, LO will
deny a smoke test that writes a dummy key then removes it against the real
controller vault (`/security/env/set` ... `/security/env/remove`). Do NOT run
live writes on his real secrets endpoint to prove persistence.

Verified-safe alternative (what survives LO's gate):

- Unit-test the detect→sanitize path with a fork of the module and NO network
  writes. Assert: the secret is detected, `sanitize_line` replaces the raw value
  with `{SECRET:NAME}`, and `raw in sanitized` is False (`leaked=False`).
- Assert plain chat ("open google", anon tokens) emits NO secret (no false positives).
- Probe `http://127.0.0.1:8940/health` for `"secrets": {"broker_attached": true,
  "audit_integrity": true}` to confirm the vault is live and encrypted without
  touching it.

Only LO's own paste into the live UI should ever write a real value to the vault.

## Test-string gotcha

Token regexes require realistic lengths (`ghp_` + 30+ alnum, `sk-` + 20+). A
"FAIL" from an abbreviated fixture like `ghp_Ab...Cdef` (literal dots, too short)
is a test artifact, not a pattern bug. Use full-length fake tokens when probing.