# Verify

Purpose: ENI Vuln Scanner OS Module — offline LLM vulnerability scanning (garak-style).

## Role
Verify for the `vuln_scanner` module.

## Inputs
The vuln_scanner deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/vuln_scanner/tests -q  (REAL suite; must pass)
