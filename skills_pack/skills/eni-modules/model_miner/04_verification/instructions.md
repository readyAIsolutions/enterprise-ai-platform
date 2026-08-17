# Verify

Purpose: Enterprise Model Miner OS Module — scan/rip local model training into the KB.

## Role
Verify for the `model_miner` module.

## Inputs
The model_miner deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/model_miner/tests -q  (REAL suite; must pass)
