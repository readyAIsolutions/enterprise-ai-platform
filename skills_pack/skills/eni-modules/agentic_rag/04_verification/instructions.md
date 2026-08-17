# Verify

Purpose: Agent-driven retrieval-augmented generation workflow.

## Role
Verify for the `agentic_rag` module.

## Inputs
The agentic_rag deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/agentic_rag/tests -q  (REAL suite; must pass)
