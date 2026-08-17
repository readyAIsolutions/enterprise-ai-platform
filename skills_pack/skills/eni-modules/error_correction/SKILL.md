---
name: eni-module-error_correction
description: Operate the ENI Enterprise `error_correction` module (Legacy Core) — error_correction — Hamming error-correcting code as an enterprise module. Use when working with error_correction in the Enterprise Platform.
---

# Module skill: error_correction

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: error_correction — Hamming error-correcting code as an enterprise module.

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

## Key API (facade methods on the @module class)
- correct\n- decode\n- dimensions\n- encode\n- health_check\n- initialize\n- set_event_bus\n- shutdown\n- stats\n- syndrome

## Use
Import via:
```python
from enterprise.modules.error_correction import create_error_correction_module
m = create_error_correction_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/error_correction/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
