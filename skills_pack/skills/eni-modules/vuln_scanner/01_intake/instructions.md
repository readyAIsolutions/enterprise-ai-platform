# Gather and normalize inputs

Purpose: ENI Vuln Scanner OS Module — offline LLM vulnerability scanning (garak-style).

## Role
Gather and normalize inputs for the `vuln_scanner` module.

## Inputs
Raw inputs/context for vuln_scanner: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for vuln_scanner. No unvalidated data passes.

## Scripts
python3 -m pytest modules/vuln_scanner/tests -q (validates core logic)
