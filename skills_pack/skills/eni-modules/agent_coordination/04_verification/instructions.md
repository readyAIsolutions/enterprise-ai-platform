# Verify

Purpose: Agent Communication & Coordination OS — Multi-agent orchestration, task scheduling,

## Role
Verify for the `agent_coordination` module.

## Inputs
The agent_coordination deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/agent_coordination/tests -q  (REAL suite; must pass)
