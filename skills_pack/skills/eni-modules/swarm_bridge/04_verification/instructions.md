# Verify

Purpose: ENI Swarm Enterprise Module v5.0.0

## Role
Verify for the `swarm_bridge` module.

## Inputs
The swarm_bridge deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/swarm_bridge/tests -q  (REAL suite; must pass)
