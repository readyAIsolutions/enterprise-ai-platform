# Module: `prompt_context`

- Category: Legacy Core · priority 49
- Version: 1.0.0
- Purpose: Prompt & Context Management OS Module
- Skill: `eni-module-prompt_context` (ICM stages) in skills_pack/skills/eni-modules/prompt_context/

## What it does
Prompt & Context Management OS Module
======================================

Enterprise-grade module for prompt lifecycle management, context orchestration,
optimization, token budgeting, evaluation, and quality gating.

Modules:
- prompt_registry: Prompt definition, versioning, lifecycle, rollback
- context_manager: Hierarchical context blocks with priorities and TTLs
- optimizer: Deduplication, compression, conflict detection, summarization
- token_budget: Token allocation, truncation, caching, model routing
- evaluator: Multi-metric evaluation, hallucination detection, grading
- quality_gates: Pre-execution checks to block/warn on quality issues

## Key API (facade methods)
health_check, initialize, shutdown

## Tests
```bash
python3 -m pytest modules/prompt_context/tests -q
```

## Import
```python
from enterprise.modules.prompt_context import create_prompt_context_module
m = create_prompt_context_module()
```
