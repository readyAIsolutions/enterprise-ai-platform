---
name: eni-module-look_and_feel
description: Operate the ENI Enterprise `look_and_feel` module (Legacy Core) — Enterprise Platform — Look & Feel Registry Module v1.0.0 Use when working with look_and_feel in the Enterprise Platform.
---

# Module skill: look_and_feel

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: Enterprise Platform — Look & Feel Registry Module v1.0.0

## What it does
Enterprise Platform — Look & Feel Registry Module v1.0.0
=========================================================

Enterprise-grade visual design registry bridging into the Enterprise Platform
OS. Parses, persists, and applies UI look-and-feel rulesets so downstream
generators produce visually consistent, distinctive UI.

Provided by look_and_feel.py:
    LookAndFeelEntry    — data model for a single design module
    LookAndFeelParser   — parses the structured module format
    LookAndFeelRegistry — JSON-backed persistent store
    LookAndFeelCLI      — 'lookandfeel' command binding

Module facade (this file):
    LookAndFeelModule   — @module-registered Module with lifecycle + API
    create_look_and_feel_module — platform factory entrypoint

Architecture:
    __init__.py            — M

## Key API (facade methods on the @module class)
- get_module\n- health_check\n- initialize\n- list_modules\n- run_cli\n- search_by_tag\n- shutdown

## Use
Import via:
```python
from enterprise.modules.look_and_feel import create_look_and_feel_module
m = create_look_and_feel_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/look_and_feel/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
