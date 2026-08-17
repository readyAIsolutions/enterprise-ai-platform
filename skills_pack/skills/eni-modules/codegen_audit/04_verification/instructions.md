# Verify

Purpose: Audit generated code for correctness, security and quality signals.

## Role
Verify for the `codegen_audit` module.

## Inputs
The codegen_audit deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/codegen_audit/tests -q  (REAL suite; must pass)
