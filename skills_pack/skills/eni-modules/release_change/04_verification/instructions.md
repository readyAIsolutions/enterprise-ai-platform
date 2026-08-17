# Verify

Purpose: Release & Change Management OS Module

## Role
Verify for the `release_change` module.

## Inputs
The release_change deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/release_change/tests -q  (REAL suite; must pass)
