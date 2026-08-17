# Verify

Purpose: ENI Agent Graph Module — langgraph-style stateful agent graph orchestration.

## Role
Verify for the `agent_graph` module.

## Inputs
The agent_graph deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/agent_graph/tests -q  (REAL suite; must pass)
