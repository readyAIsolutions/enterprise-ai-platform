# Gather and normalize inputs

Purpose: Represent/edit long-form video (animations) as code/scripts.

## Role
Gather and normalize inputs for the `video_as_code` module.

## Inputs
Raw inputs/context for video_as_code: video scripts. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for video_as_code. No unvalidated data passes.

## Scripts
python3 -m pytest modules/video_as_code/tests -q (validates core logic)
