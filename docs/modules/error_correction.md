# Module: `error_correction`

- Category: Legacy Core · priority 26
- Version: 1.0.0
- Purpose: error_correction — Hamming error-correcting code as an enterprise module.
- Skill: `eni-module-error_correction` (ICM stages) in skills_pack/skills/eni-modules/error_correction/

## What it does
error_correction — Hamming error-correcting code as an enterprise module.

Grounded in the 3blue1brown transcript *"Hamming codes part 2: The one-line
implementation"* (https://www.youtube.com/watch?v=b3NxrZOu_CE): the parity-check
results read as bits spell the position of a flipped bit, so a Hamming code
collapses to a tiny XOR/reduce computation. This module exposes that technique as
a pure-stdlib, network-free capability with a Platform Kernel lifecycle.

The deterministic core lives in
:mod:`enterprise.modules.error_correction.error_correction` (``HammingCode``,
``reduce_xor``, ``parity_positions``); this package registers it as a module with
an initialize / health_check / shutdown lifecycle and a thin facade.

## Key API (facade methods)
correct, decode, dimensions, encode, health_check, initialize, set_event_bus, shutdown, stats, syndrome

## Tests
```bash
python3 -m pytest modules/error_correction/tests -q
```

## Import
```python
from enterprise.modules.error_correction import create_error_correction_module
m = create_error_correction_module()
```
