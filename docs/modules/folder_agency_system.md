# Module: `folder_agency_system`

- Category: Legacy Core · priority 28
- Version: 1.0.0
- Purpose: folder_agency_system — a folder/org-structure system that organizes an AI
- Skill: `eni-module-folder_agency_system` (ICM stages) in skills_pack/skills/eni-modules/folder_agency_system/

## What it does
folder_agency_system — a folder/org-structure system that organizes an AI
startup's work as an on-disk folder hierarchy of capabilities, projects, and
agents, with immutable version-one templates, deployable workbenches, stable
Atlas facts, and one good librarian agent querying the library.

Grounded in JEVanClief's "Your Start Up is going to be Replaced by a Folder."
(https://www.youtube.com/watch?v=XIk-Ru85xmA).

## Key API (facade methods)
create_agent, create_atlas, create_capability, create_project, create_workbench, health_check, import_template, initialize, librarian_query, manifest, read_atlas, render_tree, set_event_bus, shutdown

## Tests
```bash
python3 -m pytest modules/folder_agency_system/tests -q
```

## Import
```python
from enterprise.modules.folder_agency_system import create_folder_agency_system_module
m = create_folder_agency_system_module()
```
