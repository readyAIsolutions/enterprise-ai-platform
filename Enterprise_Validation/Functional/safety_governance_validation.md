# Module Validation Evidence: safety_governance

| Field | Value |
|-------|-------|
| **Module Name** | safety_governance |
| **Version** | 1.0.0 |
| **Type** | Module |
| **Source Lines** | 13,202 |
| **Test Count** | 168 |
| **Tests Passed** | 168 |
| **Tests Failed** | 0 |
| **Pass Rate** | 100.0% |
| **Functional Score** | 84.0 / 100 |
| **Certification Level** | INTERNAL DEVELOPMENT |
| **Last Validated** | 2026-08-01 |
| **Evidence ID** | VAL-safety_governance-001 |
| **Validation Engine** | Enterprise Validation & Certification OS v1.0.0 |

## Test Coverage Summary

Tests rewritten 2026-08-01 to fix obsolete API signatures:
- RateLimiter (token bucket, burst, window, per-user/IP limits)
- Evaluator (hallucination detection, bias scoring, toxicity checks)
- Monitor (real-time guardrail enforcement, alerting)
- Incident (SEV1-SEV5 classification, L1_SUPPORT-L5_EXECUTIVE escalation)
- Governance (policy enforcement, compliance reporting)
- Guardrails (prompt injection protection, output filtering, content safety)

## Scoring Breakdown

| Axis | Weight | Score |
|------|--------|-------|
| Functional | 20% | 1.000 |
| Reliability | 15% | 0.920 |
| Security | 15% | 0.850 |
| Performance | 10% | 0.750 |
| Maintainability | 10% | 0.820 |
| Scalability | 8% | 0.802 |
| Observability | 8% | 0.660 |
| Documentation | 7% | 0.500 |
| Cost Efficiency | 4% | 0.254 |
| AI Quality | 3% | 0.990 |

## Evidence

- Source: `enterprise/modules/safety_governance/tests/test_safety.py`
- All 168 tests pass — async→sync conversion completed
- Root cause of prior failures: obsolete API signatures across RateLimiter, evaluator, monitor, incident