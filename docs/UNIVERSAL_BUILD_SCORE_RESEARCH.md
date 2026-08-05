# Universal Build-Quality Score — Industry Framework Research & Fusion Design

Goal: ONE normalized 0-100+ number where 100 = "fully sellable enterprise build"
and >100 is possible (excellence/bonus). Every dimension below is a real, named
industry framework so the score is defensible. Each is mapped to a sub-signal and
carried into a fused weighted formula at the end.

================================================================================
1) ISO/IEC 25010 — Software Product Quality Model
================================================================================
WHAT: The international standard for software product quality. Defines 8 product
quality characteristics, each with sub-characteristics (quantifiable).

CHARACTERISTICS + SUB-CHARACTERISTICS (25010:2011, renamed in 25010:2023):
  1. Functional suitability — functional completeness, functional correctness,
     functional appropriateness
  2. Performance efficiency — time behaviour, resource utilization, capacity
  3. Compatibility — co-existence, interoperability
  4. Usability — appropriateness recognizability, learnability, operability,
     user error protection, user interface aesthetics, accessibility
  5. Reliability — maturity, availability, fault tolerance, recoverability
  6. Security — confidentiality, integrity, non-repudiation, accountability,
     authenticity
  7. Maintainability — modularity, reusability, analysability, modifiability,
     testability
  8. Portability — adaptability, installability, replaceability

SCALE/RANGE: No single number — a structured checklist/attribute tree. Each
characteristic is scored independently (often 0-100 or ordinal Low/Med/High).

COMPUTED: By evaluation against the sub-characteristics per project.

ADOPTABLE FORMULA: Treat as weighted tree. For a build:
  ISO_score = w1*FunctionalSuitability + w2*Performance + w3*Compatibility
            + w4*Usability + w5*Reliability + w6*Security + w7*Maintainability
            + w8*Portability
  where each characteristic = weighted mean of its sub-characteristics scored
  0-100 by an LLM/verifier against checklist evidence.

VERDICT FOR US: Best as the ORGANIZING BACKBONE — it is exactly an 8-dimension
quality tree. Their 8 dimensions are richer than our 6 below, so we borrow the
idea but collapse to what a single LLM build can truthfully verify.

================================================================================
2) SonarQube — Quality Gate, Ratings (A-E), Maintainability Index (0-100)
================================================================================
WHAT: Static-analysis quality control. Three ratings + a COMBINED pass/fail gate.

RATINGS (each A,B,C,D,E -> mapped to 0-100):
  - Reliability:   based on # Bugs weighted by severity, per lines of code
  - Security:      based on # Vulnerabilities weighted by severity, per LOC
  - Maintainability: based on Technical-Debt Ratio
  Letter bands: A=0-0.05, B=0.05-0.1, C=0.1-0.2, D=0.2-0.5, E=>0.5
  (ratio = problem count or debt / LOC)

MAINTAINABILITY INDEX (MI), 0-100 (higher=better):
  Original SEI formula:
    MI = 171 - 5.2*ln(Halstead_Volume) - 0.23*Cyclomatic_Complexity
         - 16.2*ln(LOC)
  Modern heuristics + comment factor. Bands commonly:
    (85,100] = highly maintainable
    (65,85]  = moderately maintainable
    (20,65]  = difficult to maintain
    [0,20]   = extremely difficult
  SonarQube effectively uses a debt-ratio MI variant on 0-100.

QUALITY GATE: a single PASS/FAIL gate = AND of boolean conditions, e.g.:
  - no new Bugs/blockers
  - new code Coverage >= 80%
  - Security Hotspots reviewed
  - no new vulnerabilities of high severity
  - MI >= user threshold
  Define the conditions; the gate collapses them to 0/1.

ADOPTABLE:
  - Use debt ratio (or MI) as THE maintainability sub-signal on 0-100.
  - Bug/vulnerability counts -> severity-weighted -> reliability/security subscores.
  - Portable "gate" logic: our final score treats 100 as the gate floor.
VERDICT: THE most useful per-dimension numeric engine. Adopt its 0-100 rating
logic + MI + gate philosophy wholesale.

================================================================================
3) DORA — Four Key Software Delivery Metrics
================================================================================
WHAT: Industry (Google/Accelerate state-of-the-art) metrics for DELIVERY health,
not code quality. Strongly predicts org performance.

FOUR KEYS:
  1. Deployment Frequency (DF)     — how often you ship
  2. Lead Time for Changes (LT)    — commit -> production
  3. Change Failure Rate (CFR)     — % of deployments causing failure
  4. Time to Restore Service (TTR) — how fast you recover (MTTR variant)

PERFORMER BANDS (DORA 2023/24):
  ELITE : DF multiple/day, LT < 1 day,  CFR < 15%,  TTR < 1 hour
  HIGH  : DF weekly-monthly, LT < 1 week, CFR 16-30%, TTR < 1 day
  MEDIUM: DF monthly-6mo,    LT 1-6 mo,  CFR 16-30%, TTR < 1 week
  LOW   : DF > 6 months,     LT > 6 mo,  CFR > 30%,  TTR > 1 week

HOW TO COMBINE: No official single number. A defensible fusion:
  DORA_score = 0.25*DF_score + 0.25*LT_score + 0.25*CFR_score + 0.25*TTR_score
where each key mapped to 0-100 via its band (Elite=100, High=80, Medium=50,
Low=20) with interpolation; CFR and TTR inverted (lower better).

ADOPTABLE for an LLM build (one-shot, no real CI history):
  - Assess: repeatable one-command build+test (DF proxy), CI pipeline config,
    rollback path, documented deploy runbook (TTR proxy).
  - Score 0-100 on repeatability + CI + deploy automation — the "deliverability"
    dimension that a static build can actually prove.
VERDICT: The "can we actually ship and recover" axis. Use as delivery/CI-CD
sub-signal, not pure history.

================================================================================
4) Code Coverage / Test Metrics — Industry Norms
================================================================================
WHAT: % of code executed by tests. Industry guidance (NOT a hard standard):
  - The "old 80% line" is widely cited as a common enterprise bar.
  - Google/industry guidance often: 60-80% reasonable floor; >90% for paths
    that matter.
  - Line coverage >= 80% on NEW code is the most common quality-gate threshold
    (SonarQube default suggestion; many orgs use 80%).
  - Coverage is a proxy, not a guarantee: 100% coverage with weak assertions is
    useless. Pair with mutation-testing or assertion/meaningful-test review.

NORMALIZED BANDS (Ours, defensible):
  >= 90% : Excellent                 100
  80-89% : Strong / enterprise floor  90
  70-79% : Acceptable                 70
  50-69% : Weak                       45
  < 50%  : Poor / unsellable          20

ADOPTABLE:
  coverage_score = piecewise-linear band map; REQUIRE (a) line coverage and
  (b) tests actually passing (pass% first — a 0% pass rate is a hard fail
  regardless of coverage).
VERDICT: Primary "tests are real" signal. Combine pass% (gate) + coverage%
(scaled) + test-presence as one dimension.

================================================================================
5) CMMI (Maturity Levels) & SPICE / ISO 15504 (Capability Levels)
================================================================================
WHAT: Process-maturity models — how disciplined/defined the engineering PROCESS is.

CMMI MATURITY LEVELS (1-5):
  1 Initial              — ad hoc, reactive
  2 Managed              — project-level, repeatable
  3 Defined              — org-wide standards
  4 Quantitatively Managed — measured & controlled by stats
  5 Optimizing           — continuous improvement

SPICE / ISO 15504 CAPABILITY LEVELS (0-5):
  0 Incomplete, 1 Performed, 2 Managed, 3 Established, 4 Predictable,
  5 Optimizing

SCALE/RANGE: Ordinal 1-5 / 0-5. L3 (Defined) is the industry "professional
baseline"; L4-5 are elite.

COMPUTED: CMMI appraisals score practice/process areas; for a static build we
map to EVIDENCE of defined process.

ADOPTABLE for a single build:
  maturity_score = map to 0-100 by how many of these are present and real:
    - reproducible build (lockfile, pinned deps)          -> Managed
    - version control + git history discipline            -> Managed
    - documented runbook / dev+deploy docs / CI config    -> Defined
    - automated tests in CI, code review process          -> Defined
    - measured metrics (CI dashboards, coverage tracked)  -> Quantitatively M
    - retro/improvement artifacts                         -> Optimizing
  Map: L1=20, L2=50, L3=75, L4=90, L5=100 (interpolate).
VERDICT: The "is this a one-off hack or an engineered artifact" axis. Best
proxy for 'sellable enterprise'; a Level-2-ish build with docs and CI reads as
Level 3.
================================================================================
6) Snyk / OWASP — Security & Dependency Risk Scoring
================================================================================
WHAT: Supply-chain and app-security risk.

SNYK SCORE (0-100, higher=safer/better):
  Weighted composite of 8 categories: supply-chain security, project activity,
  code quality, dependencies quality, developer community, maintenance,
  popularity, licensing. A weighted average of 0-100 category scores
  (tags/scopes weighted by exploitability). A normalized health number to mirror.

SNYK A-F GRADE (vulnerability letter grade):
  Ratio = project's vulnerability count / industry-peer median, mapped to A-F.
  A = well below median (safe); F = far above median (dangerous).

OWASP:
  - OWASP Top 10: 10 most common web-app risk classes (A01 Broken Access
    Control, A02 Crypto Failures, A03 Injection, A04 Insecure Design, A05
    Security Misconfiguration, A06 Vulnerable and Outdated Components, A07
    Identification/AuthN Failures, A08 Software and Data Integrity, A09
    Logging/Monitoring Failures, A10 SSRF).
  - OWASP ASVS: 4 levels (L1 automated/black-box baseline, L2 typical app w/
    sensitive data, L3 high-assurance/security-critical) across 14 categories.

CVSS (raw severity): 0-10 (0 none, 0.1-3.9 low, 4-6.9 medium, 7-8.9 high,
9-10 critical).

ADOPTABLE CONCRETE FORMULA (our own Snyk-style A-F + 0-100):
  deps_at_risk = count of deps with unpatched vulns
  severity_weighted = sum( (CVSS/10) * exploited_flag ) over deps
  security_score = 100 - clamp( 50 * severity_weighted / max(1,total_deps) )
  grade = A if >=90, B if >=75, C if >=60, D if >=45 else F
  Then add app-level checks: OWASP Top-10 scan, no hardcoded secrets, no
  eval()/injection sinks, TLS, auth with hashing, input validation.
VERDICT: The dependency + app-security axis. Mirror Snyk's weighted multi-
category 0-100 and A-F to give both a number and a letter.

================================================================================
7) Single-Number "Health Score" Models
================================================================================
These are the precedents for collapsing everything to ONE number.

 - SONAR QUALITY GATE: single PASS/FAIL = AND of conditions. Binary (100 or 0).
   Lesson: a gate is a minimum, not a ranking.

 - CODE CLIMATE GPA: 0.0-4.0 (school GPA), computed from per-file maintainability
   ratings (A-F) averaged: GPA = sum(rating_grades)/count. Lesson: GPA = simple
   average fusion of per-file grades.

 - GITLAB SECURITY GRADE: A-F for a project's security posture (dependency + SAST
   findings severity-weighted). Lesson: severity-weighted aggregation to a letter.

 - SNYK A-F + SNYK SCORE 0-100: as in (6). Lesson: provide BOTH a letter (fast
   signal) and a number (fine resolution).

 - OPENSSF SCORECARD: 0-10 weighted sum of signals: branch protection, CI, code
   review, pinned deps, license, security policy, SAST, token permissions,
   signed releases, vulnerability disclosure. Lesson: weighted additive composite
   with a passable floor — the closest template to what we want.

 - DORA / DX platform scores: equal-weight four keys (see 3).

KEY DESIGN LESSONS ACROSS ALL SEVEN:
 a) Every serious model is a WEIGHTED ADDITIVE COMPOSITE of named, defendable
    sub-signals, plus a HARD GATE floor for unsellable builds.
 b) Severity-weighting (security) and ratio-to-peer (Snyk) beat raw counts.
 c) Bands/piecewise maps (letter->number) beat naive linear scaling.
 d) 100 must be a REACHABLE excellence bar, not the theoretical max — so align
    100 = enterprise-sellable and let bonus/escalation exceed it.

================================================================================
>>> PROPOSED FUSION: THE UNIVERSAL BUILD SCORE (0-100+, 100 = sellable) <<<
================================================================================
PRINCIPLES
  1. HARD GATES first: if any hard gate fails, score is capped/blocked regardless
     of other dimensions. Gates = things making a build literally unsellable:
       - tests do NOT pass (pass% < 100, or no tests at all)
       - core features are FAKE (stubbed/mock/placeholder at runtime)
       - secrets hardcoded / committed to repo
       - no real persistence (in-memory/empty when a real DB was promised)
       - build does not run from scratch (no dep install + start command)
     A gate failure -> score floor = min(score, 40) => "not sellable".
  2. SIX DIMENSIONS (collapsed from ISO's 8 + delivery/process axes so a single
     LLM build can truthfully verify each). Weights sum to 1.0.
  3. Each dimension = weighted mean of 0-100 sub-signals (bands, not naive).
  4. BONUS (excellence) adds up to +25 so the score can exceed 100.

THE 6 DIMENSIONS + WEIGHTS (sum = 1.00)
  D1  Reliability & Correctness ...... 0.25
  D2  Security & Supply-Chain ........ 0.15
  D3  Maintainability & Engineering .. 0.20
  D4  Test Quality ................... 0.15
  D5  Delivery / CI-CD (DORA) ........ 0.10
  D6  Completeness & Docs / Sellability 0.15
  ---------------------------------------
  SUM ................................ 1.00

SUB-SIGNALS PER DIMENSION (0-100; fractions shown as share of that dimension):

  D1 RELIABILITY & CORRECTNESS (0.25) — "does it actually work, correctly, robustly"
     - Features REAL vs FAKE (0.40): audit every claimed feature; fully
       functional -> 100; partial -> 60; fake -> 0 (HARD GATE if core)
     - Correctness / edge cases & error handling (0.25): no crashes, real error
       handling, validation, no crash on bad input
     - Persistence real & durable (0.20): real DB/files, survives restart,
       transactional where needed (in-memory when DB promised -> gate)
     - Performance / reliability under load (0.15): no O(n^2) blowups, timeouts
       on I/O, concurrency-safe, availability design

  D2 SECURITY & SUPPLY-CHAIN (0.15) — Snyk/OWASP
     - Dependency vulnerability score (0.40): Snyk-style, CVSS/severity-weighted
       per dep; mirror A-F -> 0-100
     - App security / OWASP Top 10 (0.35): authN/authZ, injection, TLS, input
       validation, no secrets; any critical class -> gate
     - Supply-chain hygiene (0.25): pinned/lockfile deps, no known-bad licenses,
       no risky native deps, provenance if applicable

  D3 MAINTAINABILITY & ENGINEERING (0.20) — Sonar + CMMI
     - Maintainability Index / tech-debt ratio -> 0-100 (0.35)
     - Code structure & modularity (0.25): clean modules, no god-objects,
       consistent naming, low duplication, docs-in-code
     - Process/maturity evidence (CMMI-ish, 0.25): version-control discipline,
       reproducible build w/ lockfile, code-review trail, config-as-code
     - Type-safety & lint cleanliness (0.15): typed, linter clean, no dead code

  D4 TEST QUALITY (0.15) — coverage norms
     - Test pass rate (0.40): HARD GATE — <100% passing blocks; real asserts
     - Coverage % (0.30): banded (>=90->100, 80->90, 70->70, 50->45, <50->20)
     - Test meaningfulness (0.30): asserts real behavior (not trivial), covers
       error paths, integration over pure mocks (mutation-mindset review)

  D5 DELIVERY / CI-CD (DORA) (0.10)
     - Reproducible one-command build+test (0.35)   [DF/LT proxy]
     - CI pipeline present and green (0.30)
     - Deploy automation + rollback/runbook (TTR proxy, 0.35)

  D6 COMPLETENESS & DOCS / SELLABILITY (0.15)
     - README, setup, usage, API/config docs (0.30)
     - Packaging (0.25): installable, no missing assets, env-config, migration
       scripts, correct entrypoints
     - Feature-completeness vs stated spec (0.25): every promised feature exists
       and is reachable
     - Professional polish (0.20): config, logging, observability, DX

BONUS / EXCELLENCE (up to +25, not in the 1.0 base):
     +8  fully automated, documented reproducible CI/CD (DORA-Elite-like)
     +6  security clean: SBOM + no OWASP/dep-scan findings
     +5  high test bar: >=90% coverage AND meaningful (mutation-like) tests
     +4  packaging installs and runs 1-command anywhere (Docker/one-shot)
     +2  license / SBOM / provenance artifacts present
  (cap total at ~125 to keep it sane)

THE FORMULA (single line):
  UBS = 0.25*D1 + 0.15*D2 + 0.20*D3 + 0.15*D4 + 0.10*D5 + 0.15*D6 + BONUS
  if any HARD GATE fails -> UBS = min(UBS, 40)

READOUT MAPPING:
  100+      = Elite / excellence (enterprise + bonus)
  90-100    = Fully sellable enterprise (the required bar)
  70-89     = Strong / near-sellable, needs polish
  50-69     = Functional prototype, NOT sellable
  <50 / gated = Unmarketable (fake features, failing tests, secrets, no real
                persistence)
