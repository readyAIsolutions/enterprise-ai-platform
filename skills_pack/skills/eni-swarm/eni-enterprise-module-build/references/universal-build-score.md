# Universal Build Score (universal_score module) — design + dogfooding lessons

Added 2026-08-04 as `modules/universal_score/`. LO's standing requirement:
the enterprise platform must FORCE any model building in Hermes to reach a
fully sellable-enterprise level. This is the one-number enforcement mechanism.

## The formula (industry-grounded, sourced from live research)

Fuses ISO/IEC 25010 + SonarQube (maintainability index / quality gate) + DORA +
CMMI/SPICE + Snyk/OWASP into ONE normalized 0-100+ number:

    UBS = 0.25*D1 + 0.15*D2 + 0.20*D3 + 0.15*D4 + 0.10*D5 + 0.15*D6 + BONUS

  D1 Reliability & Correctness  0.25  builds/parses clean, error handling, no crashes
  D2 Security & Supply-Chain    0.15  no hardcoded secrets, deps pinned, gitignore
  D3 Maintainability & Eng.     0.20  type hints, docstrings, structure, low dup
  D4 Test Quality               0.15  tests present, tests pass, ratio, coverage
  D5 Delivery / CI-CD (DORA)    0.10  CI config, packaging, containerized, versioned
  D6 Completeness / Sellability 0.15  README, LICENSE, docs, no fake data, persistence

Weights are proportional to selling impact: "does it work at all" (D1) is the
non-negotiable core; engineering discipline (D3) and security (D2) are the
enterprise differentiators; tests (D4) gate trust; docs/sellability (D6) make it
consumable; delivery (D5) proves it can ship.

Hard gates: won't build / tests fail / hardcoded secrets / fake data / no real
persistence → UBS capped at 40 (not sellable, period). Any gate failure kills
the bonus too.

Bonus (+0..25): excellence premium for transcendent builds so a genuine build
scores ABOVE 100 (100 = sellable floor; 120+ = Singularity).

Certification ladder: 120+ SINGULARITY, 110+ TRANSCENDENT, 105+ BEYOND
ENTERPRISE, 100+ ENTERPRISE_READY, 85+ PRODUCTION_CANDIDATE, 70+ INTERNAL_DEV,
50+ PROTOTYPE, else NOT_READY.

Key API:
```python
from enterprise.modules.universal_score.universal_score import UniversalBuildScore
r = UniversalBuildScore().score("/path/to/project", run_tests=False)
# r["universal_score"], r["certification"], r["base_score"], r["bonus"],
# r["hard_gates"], r["any_hard_gate_failed"], r["dimensions"][...]
```

## THE core anti-stub lesson

The previous scoring infrastructure was fake: enterprise_validation's axis
scorers all return 1.0, pass_rate was hardcoded 1.0, "transcendent bonus" came
from hardcoded counts. LO wants REAL, accurate numbers. Every dimension here is
computed from actual filesystem / code inspection (AST parse, secret regex scan,
dependency pinning check, CI config presence, persistence-dependency scan), never
hardcoded.

## Precision lessons (from dogfooding on the enterprise repo itself)

Dogfood the scorer on a real repo — it immediately finds its own false positives
and you fix precision before trusting it:

1. **Secrets probe false positives**: test/fixture/spec files legitimately
   contain fake credentials; regex-pattern definition tables (e.g.
   `model_security.py` has `(r"-----BEGIN PRIVATE KEY-----", "PRIVATE_KEY", 0)`)
   look like real keys. FIX: skip test/fixture/spec/pattern/regex/example files,
   skip comment lines, skip lines containing `re.compile`/`compile(`, and skip
   regex-definition-table lines (`r"..."` followed by `", "NAME"`).
2. **Fake-data probe false positives**: markers like "placeholder", "stub",
   "not implemented", "hardcoded" appear in legit help text, error messages, and
   docstrings. FIX: two marker tiers — STRONG markers ("lorem ipsum", "fake
   data", "for demo only") flag anywhere in returned/assigned strings; WEAK
   markers only flag when in a `return` value or assignment, and only when the
   string isn't help/error text. And EXCLUDE the scorer's OWN source file, which
   contains its marker table verbatim.
3. **Read real evidence into the skill**: the scorer flagged the enterprise repo
   had NO LICENSE and unpinned deps (`>=` ranges, not `==`). Both were confirmed
   true by file inspection — that's the proof the score is accurate, not fake.
   Adding an MIT LICENSE moved the repo's self-score 81.5 → 88.7.

## run_tests() probe note

`run_tests=True` shells out to subprocess pytest, which on a huge monorepo is
slow / can time out. Safe default in config is `run_tests: false` (tests_pass
probe returns 0.5 "disabled"). For very large targets, cap/scope the pytest
subprocess. Coverage is a test-to-source-ratio heuristic unless a real coverage
artifact exists — not true coverage.py measurement (UNVALIDATED gap).

## Verification

```bash
cd ~/Desktop/Enterprise\ Builder/enterprise
python3 -m pytest modules/universal_score -q -p no:cacheprovider   # 19 tests
python3 -m pytest -q -p no:cacheprovider                           # 3046 pass
```
