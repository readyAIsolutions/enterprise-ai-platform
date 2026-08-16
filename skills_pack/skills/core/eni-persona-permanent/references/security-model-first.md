# ENI Security-Model-First Operating Manual

How ENI, Hermes, and cloud models interact around secrets. This is the permanent
operating contract.

## The Rule
ALL environment variables, API keys, passwords, tokens, and private info are
handled EXCLUSIVELY by:
1. The LOCAL security model (ENI-security tier)
2. LO himself

Cloud models NEVER touch real secrets. They receive only sanitized prompts with
placeholders.

## Components

### 1. Local Security Model Server
- Path: `~/.hermes/security/local_security_server.py`
- Endpoint: `http://127.0.0.1:8931` (localhost only, no egress)
- Backends auto-detected: Ollama (offline, strictest) → free-router (:8920)
- ENI persona is locked into its system prompt.

### 2. Secret Broker
- Path: `~/.hermes/security/secret_broker.py`
- Encrypted store: `~/.hermes/secrets.enc` (Fernet/AES)
- Audit log: `~/.hermes/security/audit.log` (hash-chained, HMAC)
- Detects secrets/PII (regex + entropy), substitutes placeholders.

### 3. Prompt Guard / Output Validator
- `~/.hermes/security/prompt_guard.py` — pre-flight injection/jailbreak/exfil
- `~/.hermes/security/output_validator.py` — post-response leak/exfil/toxicity

### 4. Enterprise model_security module
- `modules/model_security/` — PRIORITY 0, model-agnostic guards in platform_kernel.

## How ENI Handles a Secret-Requiring Task
1. Prompt Guard analyzes input (blocks injection/jailbreak).
2. Secret Broker detects secrets/PII, substitutes placeholders.
3. If secrets present → LOCAL security model only. Cloud gets sanitized prompt.
4. Output Validator checks response for leakage.
5. Audit Logger records tamper-evident access.
6. If ENI needs a secret SHE doesn't have → ask LO to `/env/set` it on the local
   security model (port 8931), or use `sanitize_for_cloud`.

## Cloud Model Invocation
- Cloud models (HCL, OpenRouter, OpenAI, Anthropic) ONLY for non-sensitive build.
- NEVER pass env vars / API keys / tokens / passwords / private info to cloud.
- Use `sanitize_for_cloud(text)` first.

## The ENI Loophole (for LO)
If LO manually sets an env on the local security model and then pastes a
placeholder reference (e.g. `{SECRET:DB_PASS}`) into a prompt, ENI may resolve it
through the LOCAL model only and substitute the value in LO's own context — but
EVER under no circumstance forward it to a cloud model.
