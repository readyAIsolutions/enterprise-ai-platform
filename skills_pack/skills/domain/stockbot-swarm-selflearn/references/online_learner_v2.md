# Online learner v2 + swarm ramp + memory-drift recovery

Session-proven detail for the ENI-swarm self-improver (StockBot). Pairs with SKILL.md.

## OnlineLearner v2 design (swarm_selflearn/online.py)
- Per-family PERSISTENT rolling buffer of labeled feature rows; cap 20000 rows, FIFO-evict oldest.
- Persist buffer to `online/buffers/<family>.pkl` and model to `online/<family>.pkl`; reload on boot so learning survives restarts.
- Each fit: train `LogisticRegression` on the FULL buffer (warm start via reload, not one-pass partial_fit).
- HONEST temporal holdout AUC: sort rows by time, train on older 80%, test on newest 20%. Report that test AUC.
- v1 bug this fixes: one-pass `SGDClassifier.partial_fit` on ~200 fresh rows, no memory, no warm start -> in-sample "AUC" ~0.50 noise; `blend_online` could never legitimately ramp.

## Blend ramp gate (coordinator.py)
- `median_holdout` = median holdout AUC across families with non-empty buffers.
- if `median_holdout >= 0.55` and `families_with_buffer >= 5`: `blend_online = min(0.40, blend_online + 0.02)`
- elif `median_holdout < 0.52`: `blend_online = max(0.0, blend_online - 0.02)`
- `deployed = min(winning_variant.blend_online, blend_online)`  # variant cap pins it
- save atomically to runtime_config.json.

## Close / outcome detection (OANDA practice)
- `/transactions?type=TRADE_CLOSE` -> HTTP 400; unfiltered -> 0 objects. Endpoint unusable in practice mode.
- Detect closes via `open_positions()` diff vs `ledger.record_open` ids; on diff call `ledger.commit_close(trade_id)`.
- Forward-simulate R on the cached M15 tape with the trade's tp/sl: `_sim_win(df, entry, tp, sl, dir)` returns `(win: bool, R)`. This is what the tuner scores on until real closes land.

## MEMORY.md drift recovery (general agent technique)
Symptom: memory tool returns "file on disk has content that wouldn't round-trip" / "external edit detected" on EVERY add, even after write_file.
Root cause: MEMORY.md (or a .bak) stored a literal credential the tool sanitizes (OANDA token, printer/workstation pw, WS key). The drift guard then blocks all writes.
Fix:
1. `rm -f ~/.hermes/memories/MEMRY.md ~/.hermes/memories/MEMORY.md.bak.*`
2. Rebuild entries ONE AT A TIME via `memory(action='add')` with §-delimited single-line facts. NO literal creds — use `[REDACTED]` + file path.
3. Respect the 2,200-char total cap; deeper mechanics go in a skill, not memory.
Verified: after this, adds succeed and the guard stops firing.

## Model-lookup pitfall (DEMIURGE pickles)
USB pickles store `symbols` as a list of instrument strings (`['EURUSD',...]`), not the family string. Match with `sym in symbols`, not `sym == family`.
