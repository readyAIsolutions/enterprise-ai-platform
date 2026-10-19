# Verify

Purpose: Agentic RAG retrieval-strategy planner module.

## Role
Verify for the `agentic_rag_planner` module.

## Inputs
The agentic_rag_planner deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/agentic_rag_planner/tests -q  (REAL suite; must pass)
