# Landmark eval during training (mid-run self-testing)

## Why
For a long fine-tune (here ~12h, 30k steps on a 5M-token corpus), waiting until the
end to find out whether the model learned the wrong thing burns a whole night. The
fix: run a small **deterministic eval at intervaled landmarks** (every N steps) so you
get signal early and can watch the metric trend across the run.

For an AGENT model the highest-value probe is **result-literacy**: feed the model a
prompt whose answer lives in a real tool result, and check whether the REAL number /
string shows up in the generated answer (vs. a hallucinated one). This directly tests
the thing small LoRAs are flaky at.

## Implementation (Keras/TF callback)
Add a callback that fires on `on_step_end`, switches the model to eager inference for
a handful of probes, then flips back to train mode:

- On step_end: `if state.global_step % every != 0 or state.global_step == 0: return`
- `model.eval()` (disables dropout / grad checkpointing), generate deterministically
  on 5 fixed probes, check `probe_answer in model_out` (case-insensitive), write a
  row to `landmark_report.jsonl` (`{step, score, correct, total}`), `print("[LANDMARK]
  result-literacy: 4/5 (80%)")`, then `model.train()`.
- Because training uses `use_cache=False` + gradient checkpointing for memory, remember
  caching is toggled by `model.eval()` — the same switch that pauses those toggles.
- Keep probes stable across checkpoints so the score is comparable step-to-step
  (landmark curve = x=step, y=result-literacy%).

## Pitfalls
- Probe generation during a 12h run is cheap (~seconds). ~14 landmarks on a 30k-step
  run = negligible wall-clock cost.
- Make the callback idempotent and safe to leave unattended overnight — no user input,
  no interactive state.
- First landmark should land reasonably early (e.g. step 2000 of 29772 ≈ 50 min in) so
  early failure is caught within the first ~hour, not at the end.

## Deliverable
At completion, produce the landmark curve (x=step, y=result-literacy%) alongside the
final end-to-end verify of REAL tool results flowing through the served model — i.e.
pair "it quoted 47 during training" with "the live controller now returns 47".
