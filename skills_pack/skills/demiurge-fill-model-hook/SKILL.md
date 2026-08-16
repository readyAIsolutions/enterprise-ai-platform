---
name: demiurge-fill-model-hook
description: Build an edge-aware fill/volume-degradation model for the DEMIURGE FTMO bot and wire it into the backtest via the add-only monkeypatch-hook pattern. Use when working on ENI4 (fill_model) or any ENI that must add realistic cost/risk to run_backtest_v2 without editing core.
category: domain
---

# DEMIURGE — edge-aware fill model + add-only backtest hook

## When to use
- Task is fill_model.py / slippage / partial fills / spread dynamics / "make fills edge-aware so noise degrades harder".
- Any ENI that must inject per-trade cost/risk into the backtest while honoring
  "ADD ONLY — never edit backtest.py / walk_forward.py / purged_cv.py / config.py".

## Core pattern: monkeypatch run_backtest_v2 (add-only, SAFE)
Mirror crash_guard.py + strategy_guard_hook.py. Capture the original, wrap it,
rebind in memory. Restore on uninstall.

```python
import backtest, config
from config import SCORE_MIN, SCORE_MAX

_ORIG = None
def _filled_backtest(score, r_legs, floor=50, meta_score=None, meta_floor=0.5, *a, **k):
    rl = np.asarray(r_legs, float)
    degraded = _MODEL.apply_to_rlegs(rl, np.asarray(score, float), floor, micro=_MICRO)
    return _ORIG(score, degraded, floor=floor, meta_score=meta_score,
                 meta_floor=meta_floor, *a, **k)

def install(micro=None):
    global _ORIG, _MICRO
    if micro is not None: _MICRO = micro
    if _ORIG is None: _ORIG = backtest.run_backtest_v2
    backtest.run_backtest_v2 = _filled_backtest
    try:
        import gate_stress
        gate_stress.run_backtest_v2 = _filled_backtest   # keep stress harness in sync
    except Exception: pass

def uninstall():
    global _ORIG
    if _ORIG is None: return
    backtest.run_backtest_v2 = _ORIG
    try:
        import gate_stress; gate_stress.run_backtest_v2 = _ORIG
    except Exception: pass
    _ORIG = None
```

## Edge-aware fill physics (the point of ENI4)
The fill cost a trade pays must grow as its edge SHRINKS, so noise/overfit
marginal trades (score ~ floor) degrade harder than real-edge trades.

- `edge_norm = clip((score - floor)/(SCORE_MAX - SCORE_MIN), 0, 1)`
- `spread_eff = spread_bps * (1 + K_TOX*toxicity) * stress`  (spread widens w/ toxicity+stress)
- `impact = K_IMPACT * size_fraction * (1 + illiquidity)`
- `adverse = K_ADVERSE * (1 - edge_norm) * spread_eff`  (ENTRY-side only — "picked off")
- `round_turn_bps = 2*(spread_eff + impact) + adverse`
- `partial_q = clip(1 - K_PARTIAL*(1 - edge_norm)*(1 + illiquidity), MIN_PARTIAL, 1)`
- `net_R = partial_q * gross_R - round_turn_bps / SL_BPS_PER_R`

`SL_BPS_PER_R` = stop-distance-in-bps per 1R (default 25). slippage/R rises as
stops tighten. All K_* are env-tunable (DEMIURGE_FILL_*).

To degrade an (n,3) r_legs matrix while keeping the backtest's column-sum
semantics: `net = partial_q*total - slip_R`; reconstruct `out = net[:,None]*frac`
where `frac = rl/total[:,None]` (rows with total~0 put net on leg1). The backtest
only consumes the per-trade sum, so this is exact.

## VOLUME MODEL (the edge-aware volume half)
The fill cost must ALSO scale with the TAPE. Derive per-bar illiquidity
(THIN tape) and toxicity (CLIMAX volume) from a volume stream and feed both
straight into the edge-aware cost, so a low-edge trade in thin/climax volume
is "picked off" hardest (adverse = K_ADVERSE*(1-edge)*spread_eff, and
spread_eff widens with toxicity; partial_q shrinks with illiquidity).

- `volume_profile(volume, base_win=120)` -> (illiquidity, toxicity) per bar.
`rel = vol / trailing_mean(vol, base_win)` (no-lookahead, cumsum).
`illiq = K_ILLIQ*(1/rel - 1)` clipped to [0, VOL_ILLIQ_CAP];
`tox  = K_TOX*max(rel - VOL_TOX_THRESH, 0)` clipped to [0, VOL_TOX_CAP].
- `volume_micro(volume)` -> the `micro` dict (arrays aligned to bars) for
`apply_to_rlegs` / `degrade_r`.
- `simulate_wf_fills(..., volume_is=, volume_oos=)` accepts per-FOLD volume
lists -> per-fold mean illiq/tox -> volume-aware OOS/IS ratio.
- `install(volume=book_volume)` makes the live backtest hook volume-aware
(slices `volume[-n:]` to the current book; merge with a scalar `micro`).
All VOL_* are env-tunable (DEMIURGE_FILL_VOL_*).

## Self-test must prove (real numbers, not just author):
- T1 edge-aware core: low-edge haircut > high-edge haircut (noise degrades harder).
- T2 spread dynamics: wide/stressed spread -> larger haircut.
- T3 fold level: REAL agg post-fill ratio >= 0.70 & pass_rate >= 0.80;
NOISE agg (OOS gross ~ 0) forced to 0.000 / pass_rate 0.00.
- T4 hook: install(), run_backtest_v2 on a POSITIVE-edge book (high floor so
only winners accepted), assert filled avgR < plain avgR. (NEGATIVE gross R
will IMPROVE under partial fills — so use a winning book for this test.)
- T5 legacy null-detect: permuted-label agg still forced to fail.
- T6 composition: install crash_guard hook THEN fill hook; assert combined
degrades avgR (fill wraps the already-guarded fn).
- T7 volume core: thin-tape region haircut > 1.2x normal; climax-spike
haircut > 1.1x normal; low-edge trade in thin tape degrades >1.5x a
high-edge trade in normal volume. (volume_profile proves illiq>0 on thin,
tox>0 on climax.)
- T8 volume-aware WF: simulate_wf_fills(..., volume_is=, volume_oos=) on a
REAL book (normal volume) still pass_rate >= 0.80; on a NOISE book with a
thin-volume profile pass_rate < 0.80.
- T9 volume hook: install(volume=book_volume) on the backtest hook -> filled
avgR < plain avgR AND filled+vol avgR <= filled (volume adds cost).

## Pitfalls (learned the hard way)
- CLOCK SKEW on this box: stale .pyc can be NEWER than .py -> import a class with
  the wrong signature ('unexpected keyword argument'). `rm -rf __pycache__` first.
- crash_guard.py API churns under the swarm. Make ANY CrashGuard-constructing
  hook pass only the stable prefix kwargs (vol_window/vol_z/edge_window/
  edge_floor/cooldown); let crash_guard keep its dd_* defaults. Otherwise the
  whole gate import path breaks.
- Don't assert a specific haircut multiple (e.g. >2x) — the base spread both
  trades pay bounds the ratio (~1.6x). Assert noise degrades HARDER, not a fixed multiple.
- LAW 1: pure numpy, NO socket/file/oanda in the scaffold. LAW 3: report R / WR only.
- STOCKBOT PORT (standalone gate-input, NO monkeypatch): for the STOCKBOT deploy
  gate the fill_degradation scalar is often an UNASSIGNED gate INPUT (e.g. B04
  only *reports* raw gaps; B11 only *combines* metrics). Build a STANDALONE
  estimator (pure numpy, no backtest.run_backtest_v2 monkeypatch) that returns
  fill_degradation = sum(degraded_R)/sum(expected_R) in [0,1.5]; >=0.70 PASS.
  This avoids touching forbidden core and stays sibling-safe.
- STOCK SL calibration: stocks carry WIDER stops than forex. Forex SL_PER_R=25
  bps; a stock strategy is realistically 100-300 bps per 1R. If you reuse the
  forex 25 bps default, slippage/R is ~4x too large and even a genuine WINNING
  book lands ~0.68 and FAILS the 0.70 gate. Use SL_BPS_PER_R=100 for stocks.
- ADD-ONLY claim-map BEFORE building: read PL_GUIDANCE_<PROJECT>_B*.md (and sibling
  STATUS files) to confirm the sub-module is NOT already claimed; grep the tree
  for the metric/name (zero hits = genuinely unassigned). Never import or edit
  backtest/walk_forward/purged_cv/config/deploy-gate or sibling modules — assert
  `imported_forbidden == []` inside the self-test (call it T7) so core stays clean.

## Verification
`cd /home/hunter/Commander/demiurge_scaffold && source .venv/bin/activate && python fill_model.py`
-> EXPECT "[fill_model selftest] ALL PASS". Then write
`status/STATUS_DEMIURGE_fill_model.md` with PASS/FAIL board (real numbers),
what-adds-R, what-to-drop, and an UNVALIDATED section (real calibrated costs
need the USB DEMIURGE drive mounted with >=36mo bars — gate is RED on synthetic
by design).

## STOCKBOT standalone gate-input estimator (reusable SB pattern)
When the deploy gate needs a fill-degradation input that no builder owns, build
`stock_fill_degradation.py` (or equivalent) as a STANDALONE, edge-aware estimator
— do NOT monkeypatch run_backtest_v2 for this; you only need the scalar.

  edge_norm = clip((score - SCORE_MIN)/(SCORE_MAX - SCORE_MIN), 0, 1)  # or 1/0 by sign
  spread_eff = spread_bps * (1 + K_TOX*tox) * stress
  impact     = K_IMPACT * size_frac * (1 + illiq)
  adverse    = K_ADVERSE * (1 - edge_norm) * spread_eff          # entry-only pickoff
  round_turn_bps = 2*(spread_eff + impact) + adverse
  slip_R     = round_turn_bps / SL_BPS_PER_R
  partial_q  = clip(1 - K_PARTIAL*(1 - edge_norm)*(1 + illiq), MIN_PARTIAL, 1)
  degraded_R = partial_q * expected_R - slip_R
  fill_degradation = clip(sum(degraded_R)/sum(expected_R), 0, 1.5)   # ~0 if sum~0 (noise)

Self-test must prove (real numbers, synthetic gens, no live OANDA):
  T1 edge-aware: low-edge haircut > high-edge haircut (noise degrades harder)
  T2 spread dynamics: wide/stressed spread -> larger haircut
  T3 winning book: degradation >= 0.70 and pass True (expect ~0.82 with SL=100)
  T4 noise book (sum expected_R ~ 0): forced 0.0 / FAIL
  T5 thin-tape: thin-region haircut > normal-tape haircut
  T6 fold consistency: split a winning book into >=7 folds; mean>=0.70 & pass_rate>=0.80
  T7 ADD-only: assert no forbidden/core/sibling module is imported (imported_forbidden==[])

Contract for the gate builder (e.g. STOCKBOT B11): call
  report = compute_fill_degradation(blotter, scores=..., spread_bps=2.0)
and treat `report["pass"]` (>=0.70) as the fill gate. Expect winning~0.82,
noise forced 0.0/FAIL, thin-tape haircut>normal. Full SB01 contract + STATUS
shape: references/stock_fill_degradation.md. UNVALIDATED until USB DEMIURGE
mounts with >=36mo stock bars — K_* are placeholders, not calibrated.
