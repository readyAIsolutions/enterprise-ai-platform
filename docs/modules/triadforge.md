# Module: `triadforge`

- Category: Legacy Core · priority 66
- Version: 1.0.0
- Purpose: ENI TRIAD FORGE Module — White/Grey/Black Box security testing, as a kernel module.
- Skill: `eni-module-triadforge` (ICM stages) in skills_pack/skills/eni-modules/triadforge/

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
remains functional, HEALTHY, and fully testable even when TriadForge is absent.

Version: 1.0.0

## Key API (facade methods)
add_adversary_target, add_source_target, add_web_target, export_sarif, fix_snippet, health_check, initialize, list_findings, run_scan, scan_llm, scan_source, scan_web, set_event_bus, shutdown

## Tests
```bash
python3 -m pytest modules/triadforge/tests -q
```

## Import
```python
from enterprise.modules.triadforge import create_triadforge_module
m = create_triadforge_module()
```
