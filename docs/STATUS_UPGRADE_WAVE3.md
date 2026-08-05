# STATUS_UPGRADE_WAVE3 — Security Wave 2 (6 modules)

Updated: 2026-08-03

## PASS/FAIL BOARD (real numbers)

| Check | Result | Evidence |
|-------|--------|----------|
| llmops_trace (langfuse-style) | PASS | 45/45 |
| vuln_scanner (garak-style) | PASS | 67/67 |
| guardrails (guardrails-ai style) | PASS | 48/48 |
| compliance (OWASP/NIST/MITRE map) | PASS | 46/46 |
| secret_rotation (hash-only hygiene) | PASS | 51/51 |
| threat_model (MITRE ATLAS / STRIDE) | PASS | 56/56 |
| **Full platform suite** | **PASS** | **2718 passed** (was 2405 → +313) |
| config.yaml | PASS | 26 modules registered |
| Kernel boot (6 new) | PASS | all 6 → HEALTHY (6/6) |
| Import smoke (6 facades) | PASS | all OK |

## The 6 security modules (all stdlib-only, zero new deps)

1. **llmops_trace** — langfuse-style LLM observability, fully local/offline: Trace/Span
   nesting, latency p50/p95/p99 stats, error rate, cost est, span-tree, JSON/JSONL export
   + file backend, size-cap eviction. TraceFacade. (45 tests)

2. **vuln_scanner** — garak-style offline LLM vulnerability scanner: 7 attack probes
   (prompt injection, jailbreak, PII leak, prompt extraction, toxicity, data-exfil,
   refusal echo), ProbeRegistry, Scanner → ScanReport with overall risk + risk level
   + stop_rate, rescorer. VulnScannerFacade. (67 tests)

3. **guardrails** — guardrails-ai style programmable validators with validate/refix/reask
   loop: NoPII, NoToxic, JSONSchema, Profanity, Length, Regex, NoPromptInjection; Guard
   with on_fail filter/raise/fix/refix; GuardRailRunner. GuardRailFacade. (48 tests)

4. **compliance** — security-control mapping offline: 18 controls (OWASP LLM01–10,
   NIST AI RMF GOVERN/MAP/MEASURE/MANAGE, MITRE ATLAS), ComplianceEvaluator (coverage,
   risk, PASS/FAIL), GapAnalyzer, ComplianceReport. ComplianceFacade. (46 tests)

5. **secret_rotation** — credential hygiene: hash-only storage (sha256, raw never kept),
   RotationPolicy (max_age/alert window), age/expiry/due detection (injectable clock),
   rotation with hash history, breach revocation, DueReport. SecretRotationFacade. (51)

6. **threat_model** — MITRE ATLAS / STRIDE threat modeling: 17 ATLAS technique catalogue,
   ThreatAssessor (risk=likelihood*impact, severity), ThreatLibrary, STRIDEThreatMapper,
   ThreatModelReporter. ThreatModelFacade. (56 tests)

## What this ADDS (R calculus)
- **Full security observability**: llmops_trace gives the platform a local audit/tracing
  surface (complements model_security audit chain).
- **Attack-surface scanning**: vuln_scanner = scheduled black-box vuln scans per model,
  garak-style but offline/deterministic.
- **Policy enforcement**: guardrails = programmable input/output policies with refix.
- **Governance evidence**: compliance maps to 3 real frameworks → posture/coverage/report.
- **Credential lifecycle**: secret_rotation = hash-only secrets + rotation/expiry/breach.
- **Risk registered**: threat_model = STRIDE + ATLAS register, sorted, severity-ranked.

## What to DROP / consider
- None. All 6 are additive, dependency-free, and fill distinct gaps.

## UNVALIDATED
- No real LLM call was made (all probes/metrics/validators are offline heuristics).
  Sensitivity against live model outputs requires the model layer.
- vuln_scanner / guardrails / eval_gate thresholds were not calibrated against a real
  corpus — default values are reasonable starting points; tune with real data.
- secret_rotation stores hash-only by design (no re-keying of live credentials is performed;
  rotation is a policy/hygiene manager, not a live vault).

## Git
- Branch: upgrade/gold-picks
- Commit: "SECURITY WAVE 2: llmops_trace + vuln_scanner + guardrails + compliance + secret_rotation + threat_model (2718 tests, +313)"
