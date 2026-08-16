# The universal build score: LO's sellable-enterprise gate (2026-08-04)

LO's standing requirement: **any model building in Hermes must reach a FULLY
SELLABLE ENTERPRISE level — not just "working code."** He dislikes fake/hardcoded
scores and wants ONE universal, genuinely accurate number that a build can be
held to. This is enforced by the `universal_score` enterprise module (see
`eni-enterprise-module-build/references/universal-build-score.md` for the full
design).

## What LO means by a sellable build (the durable bar)

- **No fake data, no placeholders, no stubs.** He will reject a build the moment
  he finds `lorem ipsum`, "for demo only", hardcoded sample data, or a feature
  that doesn't actually persist/work. (This is the #1 trigger for his
  corrections — already in this skill; the scorer now catches it automatically.)
- **Real persistence** — not in-memory-only when it claims to store anything.
- **Security hygiene** — no hardcoded secrets, pinned dependencies, gitignore.
- **Tests that pass** + meaningful test-to-source ratio.
- **Sellability**: README, LICENSE, docs, packaging/CI, versioning.
- **100 is the floor.** A genuinely excellent build scores ABOVE 100 (bonus /
  singularity band). He has said "100 is pussy shit — push past 100."

## The scoring philosophy (anti-stub)

- Previous scoring in the codebase was fake (axes hardcoded to 1.0, pass_rate
  hardcoded, "transcendent bonus" from invented counts). LO caught the spirit of
  this and asked to "fix our scoring... make it really accurate and super good."
- **Every score must come from real probe of the actual artifact** (compile
  check, secret scan, dep pinning, document presence, persistence dependency),
  never from hand-set constants.
- **Dogfood the scorer on the repo you're scoring.** Running it against the
  enterprise repo surfaced genuine false positives (regex-pattern tables looked
  like secrets; legit help text contained "placeholder") AND genuine real gaps
  (no LICENSE, unpinned deps) — tune precision against real trees before trusting
  any number, and treat the score as evidence you can verify by inspection.

## One-liner to score any build

```python
from enterprise.modules.universal_score.universal_score import UniversalBuildScore
print(UniversalBuildScore().score("/path/to/project", run_tests=False))
# -> universal_score, certification (ladder to SINGULARITY), dimensions, hard gates
```
