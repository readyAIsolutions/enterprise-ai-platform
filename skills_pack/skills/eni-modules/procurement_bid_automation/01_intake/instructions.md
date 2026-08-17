# Gather and normalize inputs

Purpose: Automate procurement/RFP bid intake, scoring and responses.

## Role
Gather and normalize inputs for the `procurement_bid_automation` module.

## Inputs
Raw inputs/context for procurement_bid_automation: RFPs/bids. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for procurement_bid_automation. No unvalidated data passes.

## Scripts
python3 -m pytest modules/procurement_bid_automation/tests -q (validates core logic)
