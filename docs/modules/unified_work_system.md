# Module: `unified_work_system`

- Category: Legacy Core · priority 68
- Version: 1.0.0
- Purpose: ENI Unified Work System Module
- Skill: `eni-module-unified_work_system` (ICM stages) in skills_pack/skills/eni-modules/unified_work_system/

## What it does
ENI Unified Work System Module

Enterprise-grade module that runs creative, technical/software, and business
work as ONE system — grounded in the JEVanClief one-system thesis.

At the heart of the module is a :class:`WorkSystem` that centers on a single
*artifact* and renders it through multiple *lenses* (creative, technical,
business).  Each lens derives structured facts from the same artifact, and a
lens-consistency check verifies that the lenses are actually telling the same
story (flagging disagreements).  The module also implements the transcript's
memory model: an external AI :class:`MemoryStore` with position/link/content
addressing plus an explicit :class:`HumanMemory` that stays in the loop.

Exports:
  UnifiedWorkSystemModule  — @module-decorated Module subclass
  WorkSystem               — artifact-centered multi-lens core
  Artifact, Lens           — shared model
  CreativeLens, TechnicalLens, BusinessLens
  MemoryStore, MemoryItem, HumanMemory, ContextResolver
  create_unified_work_system_module

Version: 1.0.0
Python: 3.10+

## Key API (facade methods)
check_consistency, health_check, initialize, render, set_event_bus, shutdown, store_memory, work_system

## Tests
```bash
python3 -m pytest modules/unified_work_system/tests -q
```

## Import
```python
from enterprise.modules.unified_work_system import create_unified_work_system_module
m = create_unified_work_system_module()
```
