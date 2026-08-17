# Verify

Purpose: ENI Autonomous Agent Runtime Module -- Multi-provider LLM abstraction.

## Role
Verify for the `autonomous_agent_runtime` module.

## Inputs
The autonomous_agent_runtime deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/autonomous_agent_runtime/tests -q  (REAL suite; must pass)
