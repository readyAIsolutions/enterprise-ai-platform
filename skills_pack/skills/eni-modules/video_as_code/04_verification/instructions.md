# Verify

Purpose: Represent/edit long-form video (animations) as code/scripts.

## Role
Verify for the `video_as_code` module.

## Inputs
The video_as_code deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/video_as_code/tests -q  (REAL suite; must pass)
