# Verify

Purpose: Layered memory model for agents (working/short/long) from AI-memory transcripts.

## Role
Verify for the `ai_memory_hierarchy` module.

## Inputs
The ai_memory_hierarchy deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/ai_memory_hierarchy/tests -q  (REAL suite; must pass)
