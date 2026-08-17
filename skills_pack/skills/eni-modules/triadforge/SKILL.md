---
name: eni-module-triadforge
description: Operate the ENI Enterprise `triadforge` module (Legacy Core) — ENI TRIAD FORGE Module — White/Grey/Black Box security testing, as a kernel module. Use when working with triadforge in the Enterprise Platform.
---

# Module skill: triadforge

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: ENI TRIAD FORGE Module — White/Grey/Black Box security testing, as a kernel module.

## What it does
ENI TRIAD FORGE Module — White/Grey/Black Box security testing, as a kernel module.

Wraps the standalone TRIAD FORGE hacker box (~/Desktop/TriadForge) into the ENI
Enterprise Platform so it boots HEALTHY, is discoverable by the kernel, and exposes a
facade for running security scans on LO's OWN targets and funneling findings back.

This module is a thin kernel service around the TriadForge engines. It reuses the
verified TriadForge package (web/source/llm engines + SARIF remediation) whenever it
is importable. If the standalone package is NOT available, the module falls back to a
built-in, stdlib-only ``ScanCore`` engine that provides real scan orchestration
(run a scan against a config, aggregate findings, SARIF-style output) — so the module
remains functional, HEALTHY, and fully testabl

## Key API (facade methods on the @module class)
- add_adversary_target\n- add_source_target\n- add_web_target\n- export_sarif\n- fix_snippet\n- health_check\n- initialize\n- list_findings\n- run_scan\n- scan_llm\n- scan_source\n- scan_web\n- set_event_bus\n- shutdown

## Use
Import via:
```python
from enterprise.modules.triadforge import create_triadforge_module
m = create_triadforge_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/triadforge/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
