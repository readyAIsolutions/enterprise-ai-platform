# Verify

Purpose: information_theory — Shannon entropy, mutual information, KL divergence, and

## Role
Verify for the `information_theory` module.

## Inputs
The information_theory deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/information_theory/tests -q  (REAL suite; must pass)
