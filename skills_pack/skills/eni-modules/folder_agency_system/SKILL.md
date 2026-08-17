---
name: eni-module-folder_agency_system
description: Operate the ENI Enterprise `folder_agency_system` module (Legacy Core) — folder_agency_system — a folder/org-structure system that organizes an AI Use when working with folder_agency_system in the Enterprise Platform.
---

# Module skill: folder_agency_system

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: folder_agency_system — a folder/org-structure system that organizes an AI

## What it does
folder_agency_system — a folder/org-structure system that organizes an AI
startup's work as an on-disk folder hierarchy of capabilities, projects, and
agents, with immutable version-one templates, deployable workbenches, stable
Atlas facts, and one good librarian agent querying the library.

Grounded in JEVanClief's "Your Start Up is going to be Replaced by a Folder."
(https://www.youtube.com/watch?v=XIk-Ru85xmA).

## Key API (facade methods on the @module class)
- create_agent\n- create_atlas\n- create_capability\n- create_project\n- create_workbench\n- health_check\n- import_template\n- initialize\n- librarian_query\n- manifest\n- read_atlas\n- render_tree\n- set_event_bus\n- shutdown

## Use
Import via:
```python
from enterprise.modules.folder_agency_system import create_folder_agency_system_module
m = create_folder_agency_system_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/folder_agency_system/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
