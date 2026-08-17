# Verify

Purpose: Production RAG System — Enterprise-grade Retrieval-Augmented Generation.

## Role
Verify for the `rag` module.

## Inputs
The rag deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/rag/tests -q  (REAL suite; must pass)
