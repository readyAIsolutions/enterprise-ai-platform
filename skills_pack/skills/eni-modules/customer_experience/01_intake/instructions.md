# Gather and normalize inputs

Purpose: Customer Experience OS Module.

## Role
Gather and normalize inputs for the `customer_experience` module.

## Inputs
Raw inputs/context for customer_experience: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for customer_experience. No unvalidated data passes.

## Scripts
python3 -m pytest modules/customer_experience/tests -q (validates core logic)
