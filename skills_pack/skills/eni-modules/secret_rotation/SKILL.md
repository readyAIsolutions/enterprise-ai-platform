---
name: eni-module-secret_rotation
description: Operate the ENI Enterprise `secret_rotation` module (Legacy Core) — ENI Enterprise Secret Rotation OS Module. Use when working with secret_rotation in the Enterprise Platform.
---

# Module skill: secret_rotation

- Category: Legacy Core (priority ?)
- Version: 1.1.0
- Purpose: ENI Enterprise Secret Rotation OS Module.

## What it does
ENI Enterprise Secret Rotation OS Module.

Credential hygiene for the ENI Enterprise AI Platform: rotation policies,
expiry tracking, rotation scheduling, and breach revocation. All secrets are
stored as SHA-256 value hashes only --- raw credentials are never retained.

The module exposes a ``@module``-registered kernel Module
(:class:`SecretRotationModule`) alongside a plain convenience facade
(:class:`SecretRotationFacade`) for direct, dependency-free use.

All components are stdlib-only with zero external dependencies.

## Key API (facade methods on the @module class)
(module-level API)

## Use
Import via:
```python
from enterprise.modules.secret_rotation import create_secret_rotation_module
m = create_secret_rotation_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/secret_rotation/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
