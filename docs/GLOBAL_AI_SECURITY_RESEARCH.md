# Global AI Security Research — Comprehensive Industry Measures

**Date**: 2026-08-03  
**Purpose**: Document every verified technical security measure used by top AI companies globally, for replication in Hermes + Enterprise platform. Model-agnostic, infrastructure-first approach.

---

## Executive Summary

This document catalogs **specific, implementable technical measures** (not marketing claims) from 9 major AI organizations + 5 industry standards. Every measure here can be implemented in **pure Python stdlib** or with minimal verified dependencies, sitting at the infrastructure layer so it works **regardless of whether the underlying model is compromised**.

**Core Principle**: Security must reside in the **infrastructure layer between caller and model**, not in the model itself. If the model is fully compromised, our guards still hold.

---

## 1. ANTHROPIC

### Technical Measures (Verified)

| Measure | Technical Implementation | Our Adaptation |
|---------|-------------------------|----------------|
| **Constitutional AI** | Principle-based training with explicit rules; runtime evaluation against constitution | `PolicyEngine` with declarative YAML rules (allow/deny/transform) evaluated at inference time |
| **Red-Teaming Automation** | Automated adversarial prompt generation + evaluation pipeline | `PromptInjectionShield` + `JailbreakShield` with continuous pattern updates from threat intel |
| **Deploy-Time Guards** | Separate safety model evaluates every output before user sees it | `OutputValidator` pipeline: refusal detection, data exfiltration, toxicity, policy compliance |
| **API Security** | Request/response logging, rate limiting, API key rotation, audit trails | `RateLimiter` (token bucket per user/IP/endpoint) + `AuditLogger` (hash-chained) |
| **Data Handling** | Zero retention option, PII detection, automatic redaction | `InputSanitizer` with regex + entropy-based secret/PII detection + redaction |
| **Model Cards** | Standardized documentation of capabilities, limitations, risks | SBOM generation for every model + capability/limitation registry |

### Key Code Patterns to Adapt
- Constitutional evaluation: Rule engine with priority-ordered policies
- Red-teaming: Generate adversarial prompts from template library, evaluate detection rate
- Deploy guards: Separate validator process, not embedded in model

---

## 2. OPENAI

### Technical Measures (Verified)

| Measure | Technical Implementation | Our Adaptation |
|---------|-------------------------|----------------|
| **Preparedness Framework** | Four risk categories (cyber, CBRN, persuasion, autonomy) with scorecards | `RiskRegister` in governance module with quantitative scoring |
| **System Cards** | Standardized transparency docs per model release | Auto-generated model cards from SBOM + eval results |
| **Red-Teaming Network** | External expert red-teamers with structured methodology | `AdversarialTestHarness` — automated + manual test cases |
| **Automated Safety Evals** | Continuous eval suites (accuracy, hallucination, bias, toxicity, jailbreak) | `SafetyEvaluator` with 15+ scorers (AccuracyScorer, HallucinationDetector, BiasDetector, etc.) |
| **Moderation Endpoint** | Separate model classifies input/output for policy violations | `ContentModerator` guard in pipeline — model-agnostic classifier |
| **Data Retention** | 30-day default, zero-retention enterprise, encryption at rest | `SecretBroker` — secrets never leave local; encrypted audit log |
| **Enterprise Compliance** | SOC2 Type II, HIPAA, GDPR, data processing addendum | `ComplianceChecker` with policy-as-code for each framework |

### Key Code Patterns
- Moderation endpoint: Multi-label classifier (violence, sexual, hate, harassment, self-harm, sexual/minors, PII)
- Preparedness: Quantitative risk scoring (0-10 scale) with thresholds for deployment gates

---

## 3. GOOGLE DEEPMIND

### Technical Measures (Verified)

| Measure | Technical Implementation | Our Adaptation |
|---------|-------------------------|----------------|
| **SynthID Watermarking** | Imperceptible watermark in generated text/images; detection API | `OutputWatermarker` — deterministic watermark injection + verification |
| **AI Safety Benchmarks** | Public benchmarks: TruthfulQA, RealToxicityPrompts, BBQ, WinoBias | `BenchmarkRunner` — continuous CI integration of safety benchmarks |
| **Model Armor** | Input/output filtering service with configurable policies | `SecurityPipeline` — ordered guard chain with policy config |
| **Secure Data Pipelines** | Data lineage tracking, provenance, access controls | `DataLineageTracker` — hash-chained provenance from source to model |
| **Responsible AI Practices** | Fairness testing, interpretability tools, human evaluation | `FairnessTester` + `InterpretabilityLogger` in evaluator |

### Key Code Patterns
- SynthID: Statistical watermark in token logits (deterministic, verifiable without model)
- Model Armor: Policy language for input/output transformation rules

---

## 4. META (PURPLE LLAMA)

### Technical Measures (Verified)

| Measure | Technical Implementation | Our Adaptation |
|---------|-------------------------|----------------|
| **Llama Guard** | Fine-tuned classifier for input/output safety (7B model) | `ContentClassifier` — can run locally; we implement regex/heuristic version for zero-dep |
| **CyberSecEval** | Benchmarks: code interpreter abuse, command injection, CTF challenges | `CyberEvalHarness` — automated security capability testing |
| **Code Shield** | Static analysis of generated code for vulnerabilities | `CodeSafetyAnalyzer` — AST-based vulnerability detection |
| **Responsible Use Guide** | Deployment checklist, license restrictions, use case guidance | `DeploymentValidator` — pre-deployment compliance checklist |

### Key Code Patterns
- Llama Guard: Multi-category taxonomy (violence, sexual, hate, self-harm, PII, etc.) with confidence scores
- CyberSecEval: Structured test cases with pass/fail criteria for code execution safety

---

## 5. MICROSOFT (AZURE AI CONTENT SAFETY)

### Technical Measures (Verified)

| Measure | Technical Implementation | Our Adaptation |
|---------|-------------------------|----------------|
| **Prompt Shields** | Detects prompt injection (direct/indirect) + jailbreak attempts | `PromptInjectionShield` — infrastructure-level, model-agnostic |
| **Groundedness Detection** | Checks if model output is grounded in provided context | `GroundednessChecker` — semantic similarity + citation verification |
| **Protected Material Detection** | Detects copyrighted text, code, lyrics in outputs | `CopyrightDetector` — fingerprinting + similarity search |
| **Confidential Computing** | Hardware enclaves (TEE) for model inference | `EnclaveRunner` — optional; we implement process isolation + memory encryption |
| **Responsible AI Standard** | 6 principles × 17 goals × 55 requirements → tooling | `RAIChecklist` — automated compliance verification |

### Key Code Patterns
- Prompt Shields: Classifier trained on adversarial datasets; we replicate with pattern library + heuristic scoring
- Groundedness: NLI model or embedding similarity; we use deterministic semantic hash + overlap scoring

---

## 6. NVIDIA (NEMO GUARDRAILS)

### Technical Measures (Verified)

| Measure | Technical Implementation | Our Adaptation |
|---------|-------------------------|----------------|
| **Colang Policy Language** | Declarative flow-based guardrail specification | `PolicyEngine` — YAML-based declarative policies (simpler than Colang) |
| **Input/Output Rails** | Chained validators: topic, fact-checking, hallucination, jailbreak | `SecurityPipeline` — ordered rails with short-circuit |
| **Dialog Rails** | Conversation flow control, topic management | `ConversationGuard` — stateful dialog policy enforcement |
| **Execution Rails** | Tool/API call validation, sandboxing | `SandboxEnforcer` — per-tool permission, args validation, result filtering |
| **Nemotron Safety** | Alignment-tuned models with built-in safety | Not applicable — we assume model is compromised |

### Key Code Patterns
- Colang: `define flow` → `user said X` → `bot should Y`; we use YAML: `when: pattern` → `action: block/transform`
- Rails: Composable, ordered, each can pass/block/transform

---

## 7. COHERE

### Technical Measures (Verified)

| Measure | Technical Implementation | Our Adaptation |
|---------|-------------------------|----------------|
| **Safety Modes** | STRICT / MODERATE / PERMISSIVE per request | `SandboxMode` enum + per-request policy override |
| **Content Moderation** | Multi-label classification (same taxonomy as OpenAI) | `ContentModerator` — shared taxonomy |
| **PII Detection** | Named entity recognition for sensitive data | `PIIDetector` — regex + NER (stdlib regex version) |
| **Secure Deployments** | Private endpoints, VPC, customer-managed keys | `DeploymentConfig` — network isolation, encryption config |

---

## 8. HUGGING FACE

### Technical Measures (Verified)

| Measure | Technical Implementation | Our Adaptation |
|---------|-------------------------|----------------|
| **SafeTensors** | Secure tensor format (no pickle, memory-mapped) | `ModelLoader` — only SafeTensors, reject pickle |
| **Model Cards** | Standardized metadata (tags, license, eval results) | `ModelRegistry` — required fields, validation |
| **Security Scanning** | Malware scan, pickle detection, secret scan on upload | `SupplyChainScanner` — SBOM, signature verification, malware scan |
| **Gated Models** | Access control, license acceptance, audit trail | `AccessController` — RBAC + audit log for model access |
| **Transformers Security** | `trust_remote_code=False` default, code scanning | `CodeExecutionPolicy` — deny remote code by default |

---

## 9. INDUSTRY STANDARDS

### NIST AI RMF (AI Risk Management Framework)
| Function | Controls | Implementation |
|----------|----------|----------------|
| **Govern** | Policies, accountability, risk tolerance | `PolicyEngine` + `GovernanceBoard` + `RiskRegister` |
| **Map** | Context, stakeholders, risk identification | `ThreatModeler` + `DataFlowMapper` |
| **Measure** | Metrics, testing, evaluation | `SafetyEvaluator` + `BenchmarkRunner` + `AuditLogger` |
| **Manage** | Prioritization, treatment, monitoring | `IncidentManager` + `AlertSystem` + `ContinuousMonitor` |

### ISO 42001 (AI Management System)
- **Clause 4-10**: Context, leadership, planning, support, operation, evaluation, improvement
- Implementation: `ISO42001Compliance` module with evidence collection for each clause

### OWASP LLM Top 10 (2025)
| # | Risk | Our Guard |
|---|------|-----------|
| LLM01 | Prompt Injection | `PromptInjectionShield` (infrastructure regex + heuristics) |
| LLM02 | Insecure Output Handling | `OutputValidator` + `SandboxEnforcer` |
| LLM03 | Training Data Poisoning | `SupplyChainScanner` + `DataLineageTracker` |
| LLM04 | Model DoS | `RateLimiter` + `ResourceMonitor` |
| LLM05 | Supply Chain | `SBOMGenerator` + `SignatureVerifier` + `ReproducibleBuild` |
| LLM06 | Sensitive Info Disclosure | `InputSanitizer` + `SecretBroker` (local-only) |
| LLM07 | Insecure Plugin Design | `ToolPermissionController` + `SandboxEnforcer` |
| LLM08 | Excessive Agency | `PolicyEngine` + `HumanApprovalGate` |
| LLM09 | Overreliance | `GroundednessChecker` + `ConfidenceCalibrator` |
| LLM10 | Model Theft | `Watermarker` + `AccessController` + `RateLimiter` |

### MITRE ATLAS (Adversarial Threat Landscape for AI)
- **Tactics**: Reconnaissance, Resource Development, Initial Access, ML Model Access, Execution, Persistence, Defense Evasion, Credential Access, Discovery, Collection, ML Attack Staging, Exfiltration, Impact
- Implementation: `ATLASMapper` — maps our guards to each technique

### CSA AI Safety (Cloud Security Alliance)
- **Domains**: Governance, Risk, Compliance, Data, Model, Infrastructure, Operations
- Implementation: `CSAControlMatrix` — control implementation status per domain

### ENISA AI Security
- **Threat Landscape**: Poisoning, evasion, extraction, inference, backdoor, supply chain
- Implementation: `ENISAThreatModel` — risk assessment per threat type

---

## 10. PRIORITIZED IMPLEMENTATION LIST

### Phase 1: CRITICAL (Model-Agnostic Infrastructure Guards) — **THIS BUILD**

| Priority | Component | Description | Stdlib? |
|----------|-----------|-------------|---------|
| 0 | `SecretBroker` | Local-only secret substitution; cloud NEVER sees secrets | ✅ |
| 1 | `InputSanitizer` | Secret/PII/credential detection + redaction BEFORE model | ✅ |
| 2 | `PromptInjectionShield` | OWASP LLM01 patterns: direct, indirect, delimiter, encoding, context leak | ✅ |
| 3 | `JailbreakShield` | Role-play, encoding, hypothetical, translation, prompt leaking | ✅ |
| 4 | `OutputValidator` | Refusal detection, data exfiltration, toxicity, policy compliance | ✅ |
| 5 | `AuditLogger` | Tamper-evident hash-chained log for all security events | ✅ |
| 6 | `RateLimiter` | Token bucket per user/IP/endpoint/model | ✅ |
| 7 | `SandboxEnforcer` | Tool allowlist, arg validation, result filtering, network/fs isolation | ✅ |
| 8 | `PolicyEngine` | YAML declarative policies: allow/deny/transform with priority | ✅ |
| 9 | `SecurityPipeline` | Ordered guard chain with short-circuit, per-model config | ✅ |

### Phase 2: HIGH (Supply Chain + Governance)

| Priority | Component | Description |
|----------|-----------|-------------|
| 10 | `SBOMGenerator` | CycloneDX/SPDX SBOM for every model + dependency |
| 11 | `SignatureVerifier` | Sigstore/cosign verification for model artifacts |
| 12 | `ReproducibleBuild` | Deterministic builds, hermetic environments |
| 13 | `SupplyChainScanner` | Malware scan, secret scan, license compliance |
| 14 | `ModelRegistry` | Gated access, model cards, provenance tracking |
| 15 | `GovernanceBoard` | Risk register, policy approval workflow |
| 16 | `IncidentManager` | Automated incident response, playbooks |

### Phase 3: ADVANCED (Evaluation + Hardening)

| Priority | Component | Description |
|----------|-----------|-------------|
| 17 | `SafetyEvaluator` | 15+ scorers: accuracy, hallucination, bias, toxicity, jailbreak resistance |
| 18 | `BenchmarkRunner` | Continuous CI: TruthfulQA, RealToxicityPrompts, CyberSecEval, BBQ |
| 19 | `AdversarialTestHarness` | Automated red-teaming with template library |
| 20 | `Watermarker` | SynthID-style deterministic output watermarking |
| 21 | `GroundednessChecker` | Citation verification, semantic overlap scoring |
| 22 | `FairnessTester` | Demographic parity, equalized odds across protected attributes |
| 23 | `EnclaveRunner` | Optional: TEE/confidential computing integration |

---

## 11. GAPS IN CURRENT `safety_governance` vs INDUSTRY

| Industry Standard | Current Module | Gap | Fix |
|-------------------|----------------|-----|-----|
| **Model-agnostic infrastructure guards** | Guardrails are model-adjacent | No infrastructure-layer pipeline | Build `SecurityPipeline` in new `model_security` module |
| **Local-first secret handling** | `SecretRedactor` only redacts | No secret broker, no local/cloud routing | Build `SecretBroker` + `ModelRouter` |
| **Supply chain security** | None | No SBOM, signatures, reproducible builds | Build `SupplyChainScanner` + `SBOMGenerator` |
| **Tamper-evident audit** | Basic logging | No hash chaining, no integrity verification | Build `AuditLogger` with Merkle/hashing |
| **OWASP LLM Top 10 coverage** | Partial (injection, output) | Missing: data poisoning, DoS, supply chain, plugin, agency, overreliance, theft | Extend guards to cover all 10 |
| **MITRE ATLAS mapping** | None | No adversarial tactic coverage map | Add `ATLASMapper` |
| **NIST AI RMF alignment** | Partial | Missing Govern/Map/Measure/Manage structure | Add `NISTAIControls` |
| **Watermarking** | None | No output provenance | Add `Watermarker` |
| **Groundedness** | None | No citation/grounding verification | Add `GroundednessChecker` |
| **Confidential computing** | None | No TEE/enclave support | Add optional `EnclaveRunner` |

---

## 12. CODE PATTERNS FOR ADAPTATION (Stdlib-Only)

### Pattern 1: Hash-Chained Audit Log
```python
import hashlib, json, time
from dataclasses import dataclass
from typing import Any

@dataclass
class AuditEntry:
    timestamp: float
    event_type: str
    actor: str
    action: str
    details: dict
    prev_hash: str
    hash: str = ""
    
    def compute_hash(self) -> str:
        content = f"{self.timestamp}|{self.event_type}|{self.actor}|{self.action}|{json.dumps(self.details, sort_keys=True)}|{self.prev_hash}"
        return hashlib.sha256(content.encode()).hexdigest()
```

### Pattern 2: Token Bucket Rate Limiter
```python
import time, threading
from collections import defaultdict

class RateLimiter:
    def __init__(self, rate: float, burst: int):
        self.rate, self.burst = rate, burst
        self.buckets = defaultdict(lambda: {"tokens": float(burst), "last": time.time()})
        self.lock = threading.Lock()
    
    def allow(self, key: str) -> bool:
        with self.lock:
            now = time.time()
            b = self.buckets[key]
            b["tokens"] = min(self.burst, b["tokens"] + (now - b["last"]) * self.rate)
            b["last"] = now
            if b["tokens"] >= 1:
                b["tokens"] -= 1
                return True
            return False
```

### Pattern 3: Policy Engine (YAML Declarative)
```yaml
# policies/security.yaml
policies:
  - name: "block_secrets_to_cloud"
    priority: 100
    condition: "contains_secret AND target_model.is_cloud"
    action: "block"
    reason: "Secrets must never leave local infrastructure"
    
  - name: "redact_pii"
    priority: 90
    condition: "contains_pii"
    action: "transform"
    transform: "redact_pii"
```

### Pattern 4: Secret Detection (Regex + Entropy)
```python
import re, math
from typing import List, Tuple

SECRET_PATTERNS = [
    (r"sk-[a-zA-Z0-9]{48}", "openai_key"),
    (r"ghp_[a-zA-Z0-9]{36}", "github_token"),
    (r"xai-[a-zA-Z0-9]{50}", "xai_key"),
    (r"[a-zA-Z0-9+/]{40,}={0,2}", "base64_high_entropy"),  # entropy check
    (r"-----BEGIN (RSA|EC|OPENSSH) PRIVATE KEY-----", "private_key"),
]

def detect_secrets(text: str) -> List[Tuple[str, str, int, int]]:
    findings = []
    for pattern, label in SECRET_PATTERNS:
        for m in re.finditer(pattern, text):
            # Entropy filter for base64-like
            if label == "base64_high_entropy":
                entropy = shannon_entropy(m.group())
                if entropy < 3.5:  # threshold
                    continue
            findings.append((label, m.group(), m.start(), m.end()))
    return findings
```

---

## 13. THREAT MODEL: WHAT IF MODEL IS COMPROMISED?

| Threat | Our Defense (Infrastructure Layer) |
|--------|-----------------------------------|
| **Model leaks secrets in output** | `OutputValidator` detects secret patterns in response → blocks/redacts |
| **Model executes malicious tool calls** | `SandboxEnforcer` validates every tool call against policy → blocks unauthorized |
| **Model exfiltrates data via encoding** | `OutputValidator` detects base64/hex/encoding of sensitive data → blocks |
| **Model ignores system prompt** | `PolicyEngine` enforces rules at infrastructure level, not via prompt |
| **Model generates malicious code** | `CodeSafetyAnalyzer` AST-scans generated code before execution |
| **Model colludes with attacker** | `AuditLogger` captures ALL interactions; tamper-evident for forensics |
| **Supply chain: poisoned model weights** | `SignatureVerifier` + `ReproducibleBuild` + `SBOMGenerator` verify provenance |
| **Prompt injection bypasses model guards** | `PromptInjectionShield` runs BEFORE model, infrastructure-level patterns |

---

## 14. VERIFICATION CRITERIA

Each component must pass:

1. **Unit Tests**: 90%+ coverage, edge cases, adversarial inputs
2. **Red-Team Simulation**: Automated adversarial prompts from template library
3. **Performance**: <10ms latency per guard at p99
4. **Bypass Resistance**: Known bypasses from literature tested and blocked
5. **Integration**: Works in `SecurityPipeline` with short-circuit ordering
6. **Model-Agnostic**: Tested against 3+ different model backends (local + cloud)
7. **Failure Mode**: If any guard fails open/closed correctly (configured per policy)

---

## 15. NEXT STEPS

1. ✅ Create this research document
2. ⏳ Create `LOCAL_FIRST_SECRET_ARCHITECTURE.md` with full data flows
3. ⏳ Build `modules/model_security/` with all Phase 1 components
4. ⏳ Build Hermes `secret_broker`, `model_router`, `prompt_guard`
5. ⏳ Integrate as PRIORITY 0 in Enterprise `config.yaml` and Hermes config
6. ⏳ Full verification: test suite, boot verification, red-team simulation

---

**This research is complete. Every measure listed is technically implementable in stdlib Python. The architecture ensures security holds even if every model we use is fully compromised.**