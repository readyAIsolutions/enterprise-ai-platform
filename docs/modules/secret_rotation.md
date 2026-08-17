# Module: `secret_rotation`

- Category: Legacy Core · priority 50
- Version: 1.1.0
- Purpose: ENI Enterprise Secret Rotation OS Module.
- Skill: `eni-module-secret_rotation` (ICM stages) in skills_pack/skills/eni-modules/secret_rotation/

## What it does
ENI Enterprise Secret Rotation OS Module.

Credential hygiene for the ENI Enterprise AI Platform: rotation policies,
expiry tracking, rotation scheduling, and breach revocation. All secrets are
stored as SHA-256 value hashes only --- raw credentials are never retained.

The module exposes a ``@module``-registered kernel Module
(:class:`SecretRotationModule`) alongside a plain convenience facade
(:class:`SecretRotationFacade`) for direct, dependency-free use.

All components are stdlib-only with zero external dependencies.

## Key API (facade methods)
(module-level API)

## Tests
```bash
python3 -m pytest modules/secret_rotation/tests -q
```

## Import
```python
from enterprise.modules.secret_rotation import create_secret_rotation_module
m = create_secret_rotation_module()
```
