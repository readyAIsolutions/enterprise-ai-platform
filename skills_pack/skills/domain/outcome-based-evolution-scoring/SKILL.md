---
name: outcome-based-evolution-scoring
description: >
  Design and build outcome-based evolution / self-improvement scoring for
  skills, agents, or models — a durable feedback store plus a deterministic
  0-100 weight derived from REAL recorded usage (success rate, volume,
  feedback, latency-efficiency, recency), not from heuristic embedding.
  Use whenever a task asks to "score", "rank", "evolve", "promote", or
  "self-improve" a set of items and the score must reflect actual usage
  outcomes (the ENI skill_factory evolution engine, stockbot selflearn,
  demiurge, bandit-style skill pruning, etc.).
---

# Outcome-Based Evolution Scoring

The anti-pattern this replaces: scoring from a single in-memory boolean stream
(e.g. a moving average over one success/fail bit) with no persistence and no
use of volume, feedback, latency, or recency. That is a heuristic that cannot
tell a lucky one-shot from a well-measured champion.

Master-class scoring derives the weight **entirely from real, durable usage
outcomes** recorded per item. The build in ENI `skill_factory/evolution.py`
is the canonical reference implementation (see
`references/skill-factory-implementation.md` for exact formulas + constants).

## The scoring model (blend these into a 0-100 weight)

For each scored item, read its stored outcomes and compute:

1. **Success rate, Bayesian-shrunk** — `(successes + 0.5*prior) / (n + prior)`
   with `prior` ≈ 4. Shrinkage pulls a handful of samples toward the neutral
   0.5 so one lucky run is NOT a perfect track record. Raw 100% with n=1 gives
   ~0.6, not 1.0.
2. **Volume / confidence** — `confidence = n / (n + confidence_prior)` with
   `confidence_prior` ≈ 5. Multiplying the final weight by this is what makes
   few samples NOT overweighted: a 1-sample 100% run scores far below a
   20-sample 100% run despite identical success rate.
3. **Average feedback** — mean of captured 0-10 ratings / 10. When no feedback
   was recorded, degrade to NEUTRAL (0.5) rather than zero — absence is not a
   penalty.
4. **Efficiency** — inverse of mean latency and iterations, each smoothed by
   `1/(1 + x/norm)`: `latency_score = 1/(1 + avg_latency/latency_norm)` and
   `iter_score = 1/(1 + avg_iter/iter_norm)`, blended 50/50.
5. **Recency** — `exp(-age / half_life)` on the newest outcome, where
   `age = reference_time - newest_timestamp`. Older skills decay smoothly.

Final: `weight = (Σ w_i * comp_i) * confidence * 100`, weights summing to 1
(e.g. success 0.40, feedback 0.25, efficiency 0.20, recency 0.15). Round to 2
decimals for determinism.

## Durable store

Persist every outcome row: `{skill, result: success/fail, score, latency,
iterations, feedback 0-10, timestamp}`. SQLite is the natural fit (stdlib
`sqlite3`). Normalise result strings and CLAMP feedback into [0,10] on write.
Auto-create schema + an index on the grouping key. Expose `clear()` and a
close for lifecycle/tests. Build the in-memory set of known items from the DB
(`SELECT DISTINCT ...`) so it survives reloads.

## Evolution engine

- `record_outcome(...)` → delegate to the store, return the row.
- `update_score(item)` → compute from stored outcomes only.
- `rank_skills(limit)` → sort desc by weight; **deterministic tie-break** (e.g.
  by name ascending) so ordering is stable.
- `identify_top(n)` / `identify_bottom(n)` → slices of the rank (bottom =
  weakest performers, the natural refinement candidates).
- `promote(item, threshold)` → mark for refinement when weight < threshold;
  optionally invoke a `refiner` callable once per promoted item. Track
  promotions in a dict; clear an item from it once it scores above threshold.
- `refresh(...)` → loop all known items: update_score + promote; return a list
  of per-item results. Drive the refiner ONLY for below-threshold items.

## Determinism / testability discipline (critical)

- **Injectable reference time.** Recency depends on "now"; let callers pass a
  fixed `now` (epoch or ISO) so tests are reproducible. Default to the newest
  stored timestamp when omitted (age 0 → recency 1.0).
- **Fixed timestamps in tests.** Seed outcomes with literal ISO strings
  (e.g. `2026-08-03T00:00:00+00:00`) and pass a matching reference `now`.
- **Assert behavioural properties**, not just pinned numbers: ordering
  (good > bad), monotonicity (feedback/recency/efficiency raises score),
  and the volume-stability invariant (`steady_weight > lucky_weight * factor`).
- Keep normalisation helpers pure and testable (result normalise, feedback clamp).

## Pitfalls

- Do NOT multiply by confidence if you also want base volume contribution —
  the confidence factor IS the volume contribution; the interplay is what gives
  volume-weighted stability. Verify with a "1 lucky sample vs 20 consistent
  100%" test (>3x gap).
- Zero-outcomes term: return weight 0.0 with n=0 rather than dividing by zero.
- Sorted unicode ISO timestamps compare lexicographically only if same format;
  parse to epoch seconds for robust max/age.
- Weights must sum over a positive total — normalise after checking it isn't ≤ 0.
- Writing a new skill when "12-18 tests" is requested: over-write, then
  consolidate redundant cases INTO broader ones to land exactly in range
  without losing coverage (merge normalisation into the record test, drop
  duplicated identify tests, etc.).
