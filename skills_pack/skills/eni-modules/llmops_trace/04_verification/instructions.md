# Verify

Purpose: ENI LLMOps Trace OS Module — local, offline LLM tracing & observability.

## Role
Verify for the `llmops_trace` module.

## Inputs
The llmops_trace deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/llmops_trace/tests -q  (REAL suite; must pass)
