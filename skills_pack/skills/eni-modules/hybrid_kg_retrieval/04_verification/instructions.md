# Verify

Purpose: hybrid_kg_retrieval — an agentic RAG 2.0 retrieval engine that combines a

## Role
Verify for the `hybrid_kg_retrieval` module.

## Inputs
The hybrid_kg_retrieval deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/hybrid_kg_retrieval/tests -q  (REAL suite; must pass)
