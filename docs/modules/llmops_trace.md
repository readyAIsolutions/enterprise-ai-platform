# Module: `llmops_trace`

- Category: Legacy Core · priority 31
- Version: 1.1.0
- Purpose: ENI LLMOps Trace OS Module — local, offline LLM tracing & observability.
- Skill: `eni-module-llmops_trace` (ICM stages) in skills_pack/skills/eni-modules/llmops_trace/

## What it does
ENI LLMOps Trace OS Module — local, offline LLM tracing & observability.

A langfuse-style, fully-offline tracing/observability subsystem for LLM
applications. Mirrors the ``model_security`` / ``eval_gate`` philosophy: all
components are deterministic and stdlib-only.

An :class:`TraceCollector` stores traces and nested spans, supports querying,
span-tree reconstruction, JSON / JSONL export, an optional JSONL file backend,
and a size cap with FIFO eviction. :class:`SpanEvaluator` aggregates spans into
observability stats, :class:`SpanContext` enables manual ``with collector.span()``
nesting, and :class:`TraceFacade` (wrapped by the @module-decorated
:class:`TraceModule`) exposes the public surface to the rest of the platform.

## Key API (facade methods)
(module-level API)

## Tests
```bash
python3 -m pytest modules/llmops_trace/tests -q
```

## Import
```python
from enterprise.modules.llmops_trace import create_llmops_trace_module
m = create_llmops_trace_module()
```
