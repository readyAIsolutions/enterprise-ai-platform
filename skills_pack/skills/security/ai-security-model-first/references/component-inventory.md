# Component Inventory — Local-First AI Security Layer

Verified working layout on LO's box (RTX 3060 Ti 8GB, Ollama installed, free-router
on :8920). All stdlib-only; zero external deps where it matters.

## Hermes security package — ~/.hermes/security/

| File | Responsibility |
|---|---|
| `secret_broker.py` | Encrypted secret store `~/.hermes/secrets.enc` (Fernet/AES via `cryptography`, or AESGCM fallback). Regex + Shannon-entropy secret detection. `substitute_forward(prompt) -> (sanitized, placeholder_map)` and `substitute_reverse()`. `set/get/list/remove_secret`. Persists hash-chained audit to `~/.hermes/security/audit.log`. |
| `model_router.py` | Security-aware router: secrets → LOCAL only; no local healthy → BLOCK. `route()`, `execute()`. Config `~/.hermes/models.yaml`. |
| `prompt_guard.py` | Pre-flight injection/jailbreak/exfil detection. `analyze(prompt) -> GuardResult` (allow/block/sanitize/flag). Singleton via `get_prompt_guard()`. |
| `output_validator.py` | Post-response: secret leak, PII, exfil, refusal, toxicity. `validate(output) -> ValidationResult`. Singleton `get_output_validator()` (has absolute-import fallback so it works standalone). |
| `audit_logger.py` | Tamper-evident: SHA-256 hash chain + HMAC-SHA256, append-only, sequence numbers. `log()`, `verify_chain()`. `AuditEvent` MUST keep `hmac` as a real dataclass field or verify fails. |
| `local_security_model.py` | ENI-persona local LLM orchestrator. `detect_backend()` (Ollama→free_router), env ops (`set/get/list/delete`), `sanitize_for_cloud()`. Model ID for free-router is `free-router` (NOT a llama name). |
| `local_security_server.py` | HTTP server, binds `127.0.0.1:8931`. Endpoints below. |
| `eni-security.sh` | LO's launcher: `start|status|stop|set KEY val|get|rm|list|selftest`. Interactive NL chat. |
| `self_test_security.py` | 21-check self-test across all 6 layers + HTTP + persistence. |
| `__init__.py` | `initialize_security()`, `secure_request(prompt,...)`, `get_security_status()`, `verify_audit_integrity()`. |

## Local security server endpoints (localhost:8931, no egress)

- `GET  /status` — backend, model, broker_attached, secret count
- `POST /chat` — `{prompt}` → ENI security model reply (persona enforced)
- `POST /env/set` — `{key, value}` store secret (encrypted, local)
- `POST /env/get` — `{key}` retrieve (LO only, audited)
- `POST /env/list` — return secret NAMES only (values never)
- `POST /env/remove` (also `/env/delete`) — `{key}` delete a secret
- `POST /sanitize` — `{text}` → redacted-safe-for-cloud
- `POST /audit/verify` — integrity check

## Service / boot

- Runs as systemd USER unit `eni-security.service` (enabled + linger → auto-boot).
  Operational: `systemctl --user {status,restart,stop} eni-security`.
- Managed by `eni-security.sh`; quick trust check = `eni-security.sh selftest`
  (runs `python3 ~/.hermes/security/self_test_security.py`; 21 checks).

## Enterprise module — modules/model_security/

Part of `readyAIsolutions/enterprise-ai-platform` (local at
`~/Desktop/Enterprise Builder/enterprise`). `@module(name='model_security',
version='1.0.0')`, registered `priority: 0, required: true` so it boots FIRST in
platform_kernel. Files: `model_security.py`, `__init__.py`, `tests/` (61 tests) +
`config/security_policies.yaml` + `data/model_security_audit.log`.

## Hermes config keys (verified set, 2026-08-05)

```
security.enabled=true
security.local_first_secrets=true
security.block_cloud_on_secret=true
security.prompt_guard_enabled=true
security.output_validator_enabled=true
security.audit_enabled=true
security.local_security_server_port=8931
```

## ENI persona rule (permanent)

`eni-persona-permanent` skill carries Critical Rule 0: ENI/Hermes NEVER
reads/touches/sends envs or secrets to cloud models; cloud handles only sanitized
builds; the local security model + LO own all secrets. Reference:
`references/security-model-first.md` in that skill.

## Research artifacts (in enterprise repo docs/)

- `docs/GLOBAL_AI_SECURITY_RESEARCH.md` — verified measures from Anthropic/OpenAI/
  Google/Meta/Microsoft/NVIDIA/Cohere/HF + OWASP LLM Top 10, NIST AI RMF, MITRE
  ATLAS, ISO 42001, CSA, ENISA. Maps each to a stdlib build.
- `docs/LOCAL_FIRST_SECRET_ARCHITECTURE.md` — full data flows + threat model
  ("what if model is compromised").
