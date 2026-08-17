# Gather and normalize inputs

Purpose: folder_agency_system — a folder/org-structure system that organizes an AI

## Role
Gather and normalize inputs for the `folder_agency_system` module.

## Inputs
Raw inputs/context for folder_agency_system: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for folder_agency_system. No unvalidated data passes.

## Scripts
python3 -m pytest modules/folder_agency_system/tests -q (validates core logic)
