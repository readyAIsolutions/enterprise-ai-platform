# Real safety-scoring engine design + this repo's import-path quirk

Session: rebuilt the `safety_governance` module's placeholder co-occurrence
evaluator into a real stdlib score engine (baseline 173 -> 205 green, +32 tests).
Two durable, reusable lessons.

## 1. Designing a real, deterministic stdlib safety-scoring engine

When the task is "replace a placeholder with a REAL scoring engine" (toxicity,
refusal, co-occurrence/association, verdicting), three concrete traps bite:

- **Word-count dilution.** If a category score is `hits / total_words`, long
  toxic text scores almost zero because benign filler drowns the slurs. Fix:
  make it length-independent — drive off HIT COUNT with diminishing returns
  (`1 - 0.5**hits`), not a per-token ratio. 1 hit ~= sensitivity, 2 hits ~=
  1.7x, capped at 1.0. A short slur stream and the same slur padded with filler
  should score the same.

- **Overall-toxicity aggregate dilution.** Averaging six categories means one
  strong category is dragged toward zero by the five empty ones, so a genuinely
  violent/threatening phrase may not reach BLOCK. Fix: probabilistic-union
  aggregation `overall = 1 - prod(1 - v_i)` over weighted category scores. A
  single severe category gives a substantial score and distinct categories
  firing together compound toward 1.0 — this is what makes FLAG/BLOCK
  thresholds actually fire on real toxic content (unit test: `test_block_on_extreme`).

- **PMI degenerates with a single context term.** Smoothed pointwise mutual
  information `log(p_co / (p_ctx*p_cand))` returns ~0 for EVERY candidate when
  the model was learned with only one context term (every candidate is
  proportionally consistent), so a learn/score test comparing "frequent pair"
  vs "rare pair" fails with equal scores. Fix: use conditional co-occurrence
  probability `P(cand|ctx) = co_occurrences(ctx,cand) / occurrences(ctx)` — a
  genuine counter-based association frequency that discriminates counts even
  with a single context. (Test that caught it: `test_learn_and_score_association`.)

General shape that worked (32 tests, deterministic, thread-safe):
- `ToxicityScorer` — per-category hit scores + weighted union aggregate (0-1).
- `RefusalScorer` — phrase/policy/term lexicons -> sigmoid refusalness (0-1).
- `CooccurrenceModel` — `learn(ctx_pairs, target)` into Counters; `score(candidate,
  context)`; `most_associated()`; `to_dict()`. This is what kills the old
  "character n-gram Jaccard" placeholder.
- `SafetyResult` dataclass + `SafetyScorer.evaluate(text, context=None)` facade
  -> verdict safe/flag/block via `flag_threshold`/`block_threshold` + reasons list.
- Wire OPTIONALLY into the existing class (`config={"use_<engine>": True}`) so
  the legacy API and all old tests stay green; export new names from `__init__`
  alongside the old ones.
- ALWAYS run the WHOLE module suite after (not just new tests) to prove no
  regression; report baseline + new counts.

## 2. Import path quirk: pytest vs standalone python in this repo

`safety_governance/__init__.py` does `from enterprise.platform_kernel import ...`,
but there is NO `enterprise/` directory — the repo ROOT is aliased as the
`enterprise` package by `conftest.py` (it puts the repo's parent on sys.path and,
if the checkout dir isn't literally named `enterprise`, aliases root under that
module name). Consequences:

- **`pytest` just works** — conftest sets up the alias before collection.
- **Standalone `python3 -c "from safety_governance... import ..."` FAILS** with
  `ModuleNotFoundError: No module named 'enterprise'` even if you add the
  `modules/` dir to sys.path, because the `enterprise` alias isn't installed.
- **Workaround for quick manual probes:** put BOTH the repo parent
  (`<repo>/..`) AND `<repo>/modules` on sys.path:
  `sys.path.insert(0, '<repo>/..'); sys.path.insert(0, '<repo>/modules')`
  (plus `<repo>` itself if it's named differently). This lets the `enterprise`
  alias resolve and `safety_governance` import.
- Easiest path: don't fight it — drop debugging into a pytest test and run
  `python3 -m pytest <test>.py -q -p no:cacheprovider`. conftest does the
  resolution for you.
