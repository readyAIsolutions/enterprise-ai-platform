---
name: eni-module-llmops_trace
description: Operate the ENI Enterprise `llmops_trace` module (Legacy Core) — ENI LLMOps Trace OS Module — local, offline LLM tracing & observability. Use when working with llmops_trace in the Enterprise Platform.
---

# Module skill: llmops_trace

- Category: Legacy Core (priority ?)
- Version: 1.1.0
- Purpose: ENI LLMOps Trace OS Module — local, offline LLM tracing & observability.

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

## Key API (facade methods on the @module class)
(module-level API)

## Use
Import via:
```python
from enterprise.modules.llmops_trace import create_llmops_trace_module
m = create_llmops_trace_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/llmops_trace/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
