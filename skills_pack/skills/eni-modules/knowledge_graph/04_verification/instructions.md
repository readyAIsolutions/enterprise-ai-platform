# Verify

Purpose: Knowledge Graph OS Module

## Role
Verify for the `knowledge_graph` module.

## Inputs
The knowledge_graph deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/knowledge_graph/tests -q  (REAL suite; must pass)
