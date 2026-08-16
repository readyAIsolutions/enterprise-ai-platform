# OWASP Top 10 for LLM Applications (2025) — verified canonical list

Verified from the OWASP GenAI Security Project GitHub repo (`2_0_vulns/*.md`),
NOT from the JS-rendered genai.owasp.org site (which is a client-side Elementor/
Next shell — `curl` gets an empty `id="content"` div). Always pull the canonical
text from the repo:

    https://raw.githubusercontent.com/OWASP/www-project-top-10-for-large-language-model-applications/main/2_0_vulns/LLM0X_<Name>.md

List the filenames first via the GitHub API if unsure of exact names:
`https://api.github.com/repos/OWASP/www-project-top-10-for-large-language-model-applications/contents/2_0_vulns`

Source: https://github.com/OWASP/www-project-top-10-for-large-language-model-applications

## The 2025 list (canonical)

| # | Vuln | Severity | One-liner |
|---|------|----------|-----------|
| LLM01 | Prompt Injection | High | Direct/indirect injection; worsens with multimodal (hidden instructions in images / cross-modal). |
| LLM02 | Sensitive Information Disclosure | High | App leaks proprietary/sensitive data via output; needs sanitization + system-prompt restriction + TOS opt-out. |
| LLM03 | Supply Chain | High | Compromised pre-trained models / LoRA / PEFT / Hugging Face artifacts / on-device models. |
| LLM04 | Data and Model Poisoning | High | Tampered pre-train/fine-tune/embed data -> backdoors, bias, degraded output (integrity attack). |
| LLM05 | Improper Output Handling | High | Unvalidated model output executed downstream (XSS/SSRF); strict CSP + output encoding advised. |
| LLM06 | Excessive Agency | High | Over-permissioned tool/plugin access -> broad confidentiality/integrity/availability impact. |
| LLM07 | System Prompt Leakage (NEW) | High | Secret/conn-string/role info tucked in the system prompt gets exfiltrated; delegating authz to the LLM is risky. |
| LLM08 | Vector and Embedding Weaknesses (NEW) | High | RAG vector/embedding store tampering -> prompt-injected content, malicious retrieval. |
| LLM09 | Misinformation (NEW) | Medium | Hallucination / overreliance — users trust unverified model output in critical decisions. |
| LLM10 | Unbounded Consumption | High | Uncontrolled inference -> DoS, cost depletion, model theft/cloning. |

## What changed vs 2023/2024

- **New in 2025**: LLM07 System Prompt Leakage, LLM08 Vector & Embedding
  Weaknesses, LLM09 Misinformation (agentic + RAG-era surfaces).
- LLM06 Excessive Agency and LLM10 Unbounded Consumption existed before under
  different positions; 2025 formalizes them.
- Old "Model Theft" effectively folded into Unbounded Consumption (cloning).
- LLM04 unified "Training Data Poisoning" wording into Data & Model Poisoning.

## Mapping to our stack / module surface

- **RedTeamBench** (OWASP+MITRE corpus) -> add LLM07/08 cases: system-prompt
  extraction probe, RAG-poison probe.
- **DeploymentSecurityGate / SecurityGate** -> add an "excessive agency" check
  (verify tool/plugin allowlist minimal) + scan the system prompt for secrets.
  The system-prompt-leakage scan is exactly what the local-first secret broker
  (Rule 0) prevents: secrets live in the LOCAL store / ENI KB, never in a cloud
  system prompt.
- **TriadForge LLM engine** -> add `rule=prompt-leak` (LLM07) and `rule=rag-poison`
  (LLM08) patterns; the vector index maps naturally onto the ENI KB
  (`security_finding` patterns).
- Companion standards: **MITRE ATLAS** (adversarial ML kill-chain) and **NIST AI
  RMF 1.0** (govern/map/measure/manage) complement OWASP LLM for the `threat_model`
  and `compliance` modules. OWASP ASVS/WSTG pair with `vuln_scanner` + TriadForge.
