# Module: `knowledge_graph`

- Category: Legacy Core · priority 30
- Version: 1.0.0
- Purpose: Knowledge Graph OS Module
- Skill: `eni-module-knowledge_graph` (ICM stages) in skills_pack/skills/eni-modules/knowledge_graph/

## What it does
Knowledge Graph OS Module

Enterprise-grade knowledge graph for mapping and managing organizational
knowledge: entities, relationships, provenance, resolution, contradiction
management, and secure retrieval.

Version: 1.0.0

## Key API (facade methods)
health_check, initialize, shutdown

## Tests
```bash
python3 -m pytest modules/knowledge_graph/tests -q
```

## Import
```python
from enterprise.modules.knowledge_graph import create_knowledge_graph_module
m = create_knowledge_graph_module()
```
