# Gather and normalize inputs

Purpose: ENI LLMOps Trace OS Module — local, offline LLM tracing & observability.

## Role
Gather and normalize inputs for the `llmops_trace` module.

## Inputs
Raw inputs/context for llmops_trace: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for llmops_trace. No unvalidated data passes.

## Scripts
python3 -m pytest modules/llmops_trace/tests -q (validates core logic)
