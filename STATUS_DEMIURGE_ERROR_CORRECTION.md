# STATUS_DEMIURGE_ERROR_CORRECTION

Hamming error-correcting code as an enterprise module. Grounded in the
3blue1brown transcript **"Hamming codes part 2: The one-line implementation"**
(`data/transcripts/3blue1brown/b3NxrZOu_CE.md`): the parity-check results, read as
1s and 0s, spell the binary position of the flipped bit — so a Hamming code
collapses to a tiny XOR/reduce computation.

## What this tick did (recovery of an unfinished build)

A prior tick built `modules/error_correction/` but never committed it. It was
BROKEN:
- `HammingCode.__init__` started `r = n.bit_length() - 1` and **decremented** in a
  while loop, so `HammingCode(7)` hit `ValueError: negative shift count` → module
  couldn't even import.
- `syndrome()` used `p.bit_length() - 1` as the bit shift, which collides for
  parity positions 1 and 3 (both → shift 1) → wrong error position, bin-exhaustive
  single-bit-flip correction failed.
- `_event_bus` was never initialized (`AttributeError` on first facade call).
- The test suite had a wrong hardcoded parity prefix (`[0,0,1]` vs the real
  `[0,1,1]`) and missed `await health_check()`.

## Fixes landed this tick
- `r = n.bit_length()` + increment (was `-1` + decrement).
- `syndrome` shift `((p + 1).bit_length() - 1)` (was `p.bit_length() - 1`).
- `self._event_bus = None` in `__init__`.
- Tests: corrected prefix assertion to `[0,1,1]`; awaited `health_check()`.
- Registered in `config.yaml` (`modules.error_correction`, n=7).
- Ledger: `data/build/manifest.json` → `error_correction` in `built_modules`,
  transcript `b3NxrZOu_CE` flips `evaluated-skip` → `built`.

## Real verification (independent, not self-report)
- `python3 -m pytest modules/error_correction/tests -q` → **27 passed**.
- Exhaustive roundtrip: ALL 16 (7,4) data words × every 7 single-bit flips
  decode-correct to the original (real assertions, no stubs).
- **Full suite: 5128 passed, 1 skipped**.
- Kernel registration: `'error_correction' in _MODULE_REGISTRY` → True.
- Direct boot: `create_error_correction_module({'n':7})` → `initialize()` →
  health `healthy`, dims `n/k/r = 7/4/3`, encode→flip→decode roundtrip OK.

## Module API
- `HammingCode(n)` — `encode`, `decode(fix)`, `correct`, `syndrome`, `encode_bytes`;
  `.n/.k/.r`, `.parity`, `.data_positions`, `.min_distance`.
- Module-level helpers: `encode`, `decode_correct`, `hamming_7_4`, `parity_positions`,
  `reduce_xor`.
- `ErrorCorrectionModule` (`@module("error_correction", 1.0.0)`): async
  `initialize` / `health_check` / `shutdown`, `set_event_bus`, facade
  `encode/decode/correct/syndrome`, `.dimensions`, `.stats()`.

## PASS / FAIL
| Check | Result |
|---|---|
| 27 module tests | PASS |
| Full suite 5128 | PASS |
| Kernel registration | PASS |
| Exhaustive bit-flip roundtrip | PASS |
| config.yaml + ledger registered | PASS |

## UNVALIDATED
- No live event-bus publish exercised end-to-end (only guard path); wiring asserted
  via `set_event_bus` presence, not a real kernel dispatch.
- CI on 3.11/3.12 not re-run this tick (module is pure stdlib, no typing-name
  annotation hazards) — verified on local 3.14.