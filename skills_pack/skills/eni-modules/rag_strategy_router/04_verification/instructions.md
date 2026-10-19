# Verify

Purpose: ``rag_strategy_router`` — intent-based VECTOR / GRAPH / HYBRID RAG router.

## Role
Verify for the `rag_strategy_router` module.

## Inputs
The rag_strategy_router deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/rag_strategy_router/tests -q  (REAL suite; must pass)
