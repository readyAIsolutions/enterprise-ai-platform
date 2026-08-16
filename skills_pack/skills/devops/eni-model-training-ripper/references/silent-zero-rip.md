# Silent zero-rip failure: exit 0, freed disk, but ZERO KB entries (2026-08-05)

Distinct from interrupted-batch-resume (SIGTERM mid-download). This is a run that
**completes cleanly (exit code 0)** and looks like it did something — it downloads
and DELETES each model — yet banks NOTHING into the KB. More dangerous because the
green exit masks the loss.

## The failure signature
- `--train-batch --limit N --deep` returns exit 0.
- Every model reports `"ok": false, "saved": 0, "error": null`, but
  `"freed_mb": <large>` — meaning download + delete happened, rip saved nothing.
- KB model-rip count is UNCHANGED after the run.
- Hundreds of MB to GB of disk got freed because delete_after fired anyway.

## Root cause 1: battery default clobbered by `topics or []`
The rip loop's battery default (RIP_TOPICS / DEEP_TOPICS) only applies when the
`topics` argument is literally `None`:

    if topics is None:
        topics = DEEP_TOPICS if deep else RIP_TOPICS

But `train_and_rip` did `topics or []` before handing off. `None or []` evaluates
to `[]` (empty list), so rip() received an EMPTY list, not None, and never applied
its default. The loop then iterated over **zero topics** → `saved:0, error:null`.

## Root cause 2: `--deep` / topics never propagated through the train path
`run_batch` lacked a `deep` parameter and forwarded no topics to `train_and_rip`,
so `--train-batch --deep` silently ignored the deep flag. (The single `--train` and
`--mine` paths had working deep wiring — which is why a prior single-model batch
"worked" and masked the batch-path bug.)

## Root cause 3: delete-after-rip trap
`delete_after` was unconditional. A silent empty-rip "looked like success," so the
trainer deleted the model anyway — destroying the only copy of an asset we failed
to learn from. Per-model isolation (try/except skipping one model) made it worse:
it never surfaced the aggregate "everything saved 0" signal.

## The fix (encode this shape into the pipeline)
1. **Propagate the flag end-to-end**: `run_batch(deep)` → `train_and_rip(deep)` →
   `_rip_with_server(deep)` → `rip(deep)`. Never drop a mode flag at a boundary.
2. **Stop `topics or []` from clobbering the default.** Pass topics through as None
   and let rip() apply its own default. Guard the `or []` idiom.
3. **DELETE-AFTER-RIP GUARD**: only free disk when the rip actually banked entries
   (`saved > 0`). When `saved == 0`, keep the model cached and set
   `kept_for_retry: True` so it can be retried instead of destroyed.
   Opt out explicitly via `force_delete=True` (default off / guard on).
4. **Suspicion rule**: ANY batch result where `saved:0` for every model is not a
   "nothing to rip" — it's a propagation/default bug until proven otherwise.
   Check the pipe of `topics`/`deep` before blaming the model or the server.

## Verification pattern (prove the fix, don't just author it)
- Unit: `rip(topics=None, deep=True)` must save exactly `len(DEEP_TOPICS)` with a
  stubbed `chat()`; `deep=False` must save `len(RIP_TOPICS)`.
- Unit: guard defaults to ON (`ModelTrainer(force_delete=False)._force_delete is False`).
- Live: run ONE small model `--train <tiny> --deep`, expect `extracted:10, saved:10`
  for the 10-topic deep battery, `ok:true`, and KB count +10.
- Always snapshot KB count before and after (`ls ~/.eni/kb/controller_model_rip_*.md | wc -l`).
