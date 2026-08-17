# Verify

Purpose: Swarm Network Optimization OS — Enterprise Module

## Role
Verify for the `swarm_network` module.

## Inputs
The swarm_network deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/swarm_network/tests -q  (REAL suite; must pass)
