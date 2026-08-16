# Headless per-wallpaper FPS / drop-rate estimator (LUMEN)

Reusable model for ANY LUMEN module that must predict whether a wallpaper will
hit its target fps WITHOUT a GPU / display (benchmark, what-if, preflight,
recommend extension). Shipped as `lumen/benchmark.py` (ADD-ONLY, Qt-free,
imports ONLY `lumen.perf` + stdlib). Use `lumen.perf.gpu_fragment_load` as the
single source of truth so your numbers match the live engine / `recommend` /
`auto_tune`.

## MODEL (rigorous, matches the live engine)
- Fragment load of one surface at `fps`:
  `load = gpu_fragment_load(w, h, fps, dpr) = w * h * dpr^2 * fps`  [frag/s]
  Reuse `lumen.perf.gpu_fragment_load` VERBATIM — never recompute.
- Box throughput `T` = `capacity_surfaces * (1920 * 1080 * dpr_cap^2 * 30)`
  fragments/sec. Default `capacity_surfaces = 1.0` == AMD-safe (one software-
  WebGL surface, matches `max_webgl_surfaces = 1`). `HardwareCap.default()`
  yields throughput 139_968_000 frag/s.
- Per-frame GPU time:
  `draw_cost_ms = (w * h * dpr^2) / T * 1000`  ( = frags/frame ÷ throughput ).
  An image is composited once -> `draw_cost_ms = 0` (always SMOOTH).
- Kind discounts (match `recommend.estimate_load`): shader/scene = full load;
  video ≈ 0.4×; remote web URL ≈ 0.5×; image = small nominal constant.

## VERDICT (the metric a user FEELS)
- If `draw_cost_ms <= 1000 / fps` -> GPU keeps up -> SMOOTH (zero drops).
- Else it falls to its max sustainable rate `max_rate = 1000 / draw_cost_ms`
  (capped at `fps`) -> DEGRADED or UNUSABLE.
- `delivered_fps = min(fps, max_rate)`; `dropped_fps = max(0, fps - delivered)`;
  `drop_rate = dropped_fps / fps`.
- Thresholds: SMOOTH `drop_rate <= 0.05`; DEGRADED `<= 0.5`; else UNUSABLE.

## CLOSED-FORM SAFE FPS
`safe_fps = floor(T / (w * h * dpr^2))` — the highest fps with zero drops
("run this wallpaper at 24 fps instead of 30"). Verified identical to the
simulation when smooth.

## PITFALL — the vsync-skip counter (cost a self_test cycle this build)
A naive model that counts "every vsync that fires while a draw is still running"
reports ~50% "drop rate" for a 30fps-on-60Hz wallpaper that is PERFECTLY
SMOOTH — because at a sub-refresh target the engine SKIPS every other vsync by
design; that skipped vsync is NORMAL pacing, not a dropped frame. The raw skip
counter is therefore meaningless at sub-refresh targets. ALWAYS derive the
verdict from `delivered_fps` vs `target` (above), never from the raw skip count.
Also: `as_dict()` must include `width`/`height`/`fps` (not just `load`/`fps`-
derived fields) or a shape-assertion test fails; and a 4K shader on a
capacity-1 box lands at UNUSABLE (not DEGRADED), so a report test that asserts
both SMOOTH and DEGRADED appear needs a DEGRADED case (e.g. a 2560×1080 shader)
in its fixture.

## LEASH
Module imports ONLY `lumen.perf` (explicitly Qt-free) + stdlib. Prove it with
the import-block guard (see SKILL.md LEASH VERIFICATION) — `benchmark.py`
imports AND `self_test()` returns True even with PyQt6/PySide6/Xlib blocked at
`builtins.__import__`. The repo conftest prints `QApplication created by (in
order)` with an EMPTY list for the benchmark test module — no GUI constructed.

## VERIFICATION (this run, 2026-07-11)
- `python -m lumen.benchmark --self-test` -> 17 checks, exit 0 (PASS).
- `pytest tests/test_benchmark.py` -> 21 passed.
- flake8 clean; importlint clean; mypy: 0 errors in the module.
- Full suite: 1009 passed, 2 pre-existing failures (lumen/migration.py, owned
  by another builder, NOT mine — verified by removing benchmark.py and
  re-running the migration tests; they still failed identically).
