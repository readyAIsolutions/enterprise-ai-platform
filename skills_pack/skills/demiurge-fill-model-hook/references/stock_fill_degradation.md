# STOCKBOT standalone fill-degradation gate-input — SB01 contract

Condensed from the SB01 build (swarm builder, workspace 1, project STOCKBOT).
Companion to the SKILL.md "STOCKBOT standalone gate-input estimator" section.

## Why this module exists (claim-map)
The STOCKBOT deploy gate needs `fill_degradation >= 0.70`. 12 product builders
B01–B12 claimed: backtest_engine, stock_walk_forward, stock_purged_cv,
oanda_live (raw gap report), mtf_confluence, risk_guard, feature_exports,
signal_scorer, regime_filter, dashboard_backend, stock_deploy_gate, config_validate.
Grepping the tree for `fill_degradation` returned ZERO hits -> the DERIVED
degradation scalar was unassigned (B04 only reports raw gaps; B11 only combines
metrics). That gap = the SB01 module.

## Module shape (ADD-ONLY, standalone)
File: `stock_fill_degradation.py` (NEW; no core/sibling import).
Public API:
  compute_fill_degradation(blotter, *, scores=None, spread_bps=2.0, stress=1.0,
      size_frac=None, illiq=None, tox=None, sl_bps_per_R=100.0, ...) -> dict
  returns: n_trades, expected_R_total, degraded_R_total, fill_degradation,
           fill_degradation_raw, pass (>=0.70), gate_threshold,
           per_trade_degradation_median, net_positive_rate, mean_partial_q,
           mean_round_turn_bps, mean_adverse_bps, mean_spread_eff_bps, score_aware
`blotter` accepts: array of expected_R floats, OR dict/DataFrame with
`expected_R` (+ optional `score`, `sl_bps`, `size_frac`, `illiq`, `tox`).
CLI: `python3 stock_fill_degradation.py --selftest` -> exit 0 if ALL PASS;
writes `stock_fill_degradation_selftest.json`.

## Calibration that bit us (and the fix)
Forex SL_PER_R=25 bps carried over -> slippage/R ~4x too large -> a genuine
winning book retained only 0.68 and FAILED the 0.70 gate. Fixed by setting
stock-realistic SL_BPS_PER_R=100. Result after fix: winning book 0.8202,
7-fold mean 0.8116 (min 0.8007), pass_rate 1.00. The 0.70 GATE threshold is
UNCHANGED — only the cost calibration is realistic for stocks.

## Real self-test numbers (synthetic gens, USB unmounted = RED-by-contract)
T1 low-edge haircut 0.442 > high-edge 0.103          PASS
T2 wide-spread haircut 0.440 > narrow 0.224           PASS
T3 winning book degradation 0.8202, net_pos 1.000     PASS
T4 noise book forced 0.000000 / FAIL                   PASS
T5 thin-tape haircut 0.448 > normal 0.248             PASS
T6 7-fold mean 0.8116 min 0.8007 pass_rate 1.00       PASS
T7 imported_forbidden == []                           PASS
Discrimination check: a MARGINAL book (mean R~0.35, scores 0.2-0.6) -> ~0.55
and FAIL — gate is non-trivial, not a rubber stamp.

## ADD-ONLY verification (do this in every sibling module)
T7 asserts none of {backtest, walk_forward, purged_cv, config, deploy_gate_check,
stock_deploy_gate, oanda_live, fill_model, feature_exports, mtf_confluence,
regime_filter, signal_scorer} are in sys.modules. Keep estimator pure numpy;
ZERO network/file/OANDA IO (read-only benchmark only, never place orders).

## Wiring contract for the gate builder (B11)
  report = compute_fill_degradation(blotter, scores=scorer_out, spread_bps=2.0)
  fill_gate_pass = report["pass"]   # == fill_degradation >= 0.70
Edge-aware mode requires B08's signal_scorer output as `scores`; without it the
estimator falls back to a 1/0 sign proxy (spread/volume-aware only).

## UNVALIDATED (RED-by-contract)
K_TOX/K_IMPACT/K_ADVERSE/K_PARTIAL/SL_BPS_PER_R are placeholder-stock, not
calibrated to a real tape. On USB DEMIURGE mount, feed real BA-candle bid/ask
spreads + ADV-based size_frac + volume-profile illiq/tox and re-measure on a
>=36mo stock backtest. End-to-end B8->this->B11 wiring untested until those
builders are DONE. No green verdict asserted on synthetic.
