# Master-class Masking & Tokenization Engine (stdlib-only, real crypto)

Verified while rebuilding `modules/privacy_data/masking.py` in the Enterprise repo.
Real HMAC-based masking/tokenization, no fake crypto. Two layered systems with
deliberately different security properties:

## The two-layer mental model (get this right first)
- **MASKING** = IRREVERSIBLE obfuscation. No vault, no reversal, ever. Three
  invariants to enforce BY CONSTRUCTION and assert in tests:
  * deterministic   — same input -> same masked output
  * idempotent      — masking an already-masked value is a no-op (returns itself)
  * format-preserving — digits stay digits, letters stay letters, separators
    (dash/space/@/dot/paren) kept verbatim so downstream systems keep working.
- **TOKENIZATION** = REVERSIBLE but ONLY through a guarded vault. Token is derived
  from `HMAC-SHA256(secret, value)` so it is deterministic PER VALUE (no random
  uuid), format-preserving-ish shape, and the plaintext is recoverable ONLY by a
  vault lookup. Without the vault the token is one-way (HMAC is not invertible).
  The vault is the single choke-point that makes reversal possible.

## Class layout that worked (stdlib only: hmac/hashlib/re/sqlite3/secrets/threading)
- `MaskType(str, Enum)` — email, phone, ssn, name, credit_card, generic.
- `Masker` base with `mask()` that early-returns None, coerces non-str, and
  short-circuits `_is_already_masked()` for idempotency; subclasses implement `_mask()`.
- Concrete maskers: EmailMasker (keep domain, mask local part keeping 1+1),
  PhoneMasker (keep last 4), SsnMasker (XXX-XX-####), CreditCardMasker (keep last 4,
  preserve grouping), NameMasker (keep first-char init of first/last words, mask rest),
  GenericMasker (mask alnum, keep punctuation).
- `MaskingPolicy` — declarative dict `{field: MaskType|str|Masker}` plus optional
  `default` masker; apply() recurses into nested dict/list/tuple, applies to str
  fields only so non-string types (int/bool/float) are preserved untouched.
- `TokenizationEngine` — `tokenize()`/`detokenize()`/`reverse()`/`tokenize_record()`,
  `_build_token()` via `_format_preserve_token()`.
- `Vault` abstract + `InMemoryVault` (dict, thread-locked) + `SQLiteVault`
  (durable, per-thread connection pool keyed on `threading.local()`, `INSERT OR
  REPLACE` keyed on token). SQLite is what gives cross-process persistence/reopen.
- `DataMasker` facade — holds a policy, `apply(record)` delegates to
  policy.apply. Expose via an ALIAS (e.g. `PolicyDataMasker`) when an existing
  `security.DataMasker` already occupies the name in `__init__.__all__`, to avoid
  clobbering pre-existing exports.

## Format-preserving token algorithm
Walk the plaintext char by char; for each char pull the next HMAC digest byte:
- digit -> `str(b % 10)`
- alpha -> `chr(ord('a') + (b % 26))`, uppercase it if the source was uppercase
- other (punctuation/whitespace) -> kept VERBATIM (this is the shape-preservation lever)
If the resulting token has no alpha chars left (all-digit input), prefix `tok_`
so it isn't a bare run of digits.

## Export/__all__ registration
New classes must be added to BOTH the `__all__` list and the convenience `from .masking import (...)` block in `__init__.py`. Keep the object's own
`masking.DataMasker` accessible via `from . import masking` + `PolicyDataMasker = masking.DataMasker`.

## Test suite targets (40 tests here -> module went 222 green total)
masker formats per type; policy field-level application; string-vs-dict rule
coercion; unknown-field left untouched; non-string type preservation; nested
dict/list structure preservation; default masker; facade instance + static apply;
unknown-policy error; tokenization deterministic + distinct-values-distinct;
reversible-via-vault; format-preserving shape; detokenize-unknown raises;
SQLite persistence across reopen (same db file, same secret -> same token +
reversible); in-memory vault lifecycle (+ contains/len/reverse); tokenize_record;
short secret rejected; reverse lookup; tokenize None raises; registry has all
types; unknown mask type raises.

## PITFALLS (both cost real debugging this session)
1. **Falsy empty vault clobbers passed-in vault.** `InMemoryVault` defines `__len__`,
   so an empty vault is falsy, and `self._vault = vault or InMemoryVault()` silently
   DROPS a caller-provided vault and creates a fresh one -> tokens land in a vault
   nobody holds. Always use an explicit None check:
   `self._vault = vault if vault is not None else InMemoryVault()`.
   (General rule: any object that defines `__len__` or `__bool__` is falsy-when-empty;
   don't use `or default()` for object injection.)
2. **Format-preserve punctuation bug.** Masking the punctuation byte with the digest
   byte can emit stray chars (e.g. a literal `|` where a space was). Keep
   punctuation VERBATIM; only rewrite digits and letters. Don't derive punctuation
   from the digest.

## Read-side compression gotcha (recap)
The Enterprise repo files come back as `<ENI-COMPRESSED ... carrier=...png>` when
read in big chunks (paid-model session). Work around by small bounded reads:
`read_file(offset, limit=~60)` or `terminal sed -n 'A,Bp'`. See
references/integrity-ledger-and-eni-file-read.md and the eni-omega-compress-paid
read-side-compression reference for the full pattern.
