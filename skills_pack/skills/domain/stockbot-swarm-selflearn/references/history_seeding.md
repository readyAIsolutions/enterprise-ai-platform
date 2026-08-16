# History Seeding — make the online learner WAY faster + honest

## Why
The live bot trickles ~33 days of M15 into a ~3,500-row buffer. On that tiny window the
temporal holdout AUC reads ~1.0 — a REGIME/LEAKAGE ARTIFACT, not edge. Seeding the FULL
USB M15 history gives the learner years of labeled bars instantly and drops the honest
AUC to 0.82–0.98 (a real, defensible number).

## Source
`/run/media/hunter/DEMIURGE/data/historical/<SYM>/M15.parquet`
- 24 symbols, 2016→now, UTC DatetimeIndex, cols [open,high,low,close,volume].
- Includes the 2020 COVID + 2022 flash crash windows — keep them in the training tail.

## Method
- `OnlineLearner.seed_history(symbols, history_root, model_resolver)`:
  loads each parquet, normalizes the UTC index, calls `features_and_labels`
  (engine `build_features` + `label_trades`, `tp1_hit` label), appends ALL history rows
  (NOT tail) to the per-family buffer, then persists buffer + model.
- `Coordinator.seed_history_once()` calls it once, guarded by flag
  `online/seeded_history.done`. Delete that flag to re-seed.
- Buffer cap raised 4000 → **20000** so the full history fits (~19,900 rows/symbol
  post-seed vs ~3,500 live-only).

## Result (real numbers, this session)
Honest multi-year temporal holdout AUC after seed:
XAUUSD 0.822, XAGUSD 0.960, EURUSD 0.980, GBPUSD 0.983, GBPCAD 0.984, GBPCHF 0.980,
CHFJPY 0.971, USDJPY 0.966, CADJPY 0.974, NZDUSD 0.981, AUDUSD 0.970, NZDCHF 0.971,
AUDNZD 0.962, AUDCAD 0.968, EURCHF 0.975, EURGBP 0.973, GBPJPY 0.966, GBPAUD 0.978 —
all 24 seeded, buffer ~19.7k–20k rows/sym.

## Principle
A near-perfect AUC on a SHORT window is always suspect. Seed full history (years) and
read the multi-year holdout before trusting or reporting the model's edge. Live bars keep
appending on top of the seeded buffer after the one-time seed.
