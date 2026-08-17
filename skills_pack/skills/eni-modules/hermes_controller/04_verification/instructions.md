# Verify

Purpose: Enterprise Hermes Controller OS Module — autonomous controller for Hermes Agent.

## Role
Verify for the `hermes_controller` module.

## Inputs
The hermes_controller deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/hermes_controller/tests -q  (REAL suite; must pass)
