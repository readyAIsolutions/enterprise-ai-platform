---
name: ai-security-model-first
description: Build a local-first, model-agnostic AI security layer for LO — the standing architecture that keeps ALL envs/secrets/credentials/PII on the LOCAL machine and never lets cloud models touch real secrets. Covers the secret broker (registry-regex + entropy detection, placeholder substitution), model router (secrets→local-only, BLOCK if no local available), prompt-injection/jailbreak shields, output validator, hash-chained audit logger, declarative policy engine, and a specialized LOCAL security model with ENI persona. Use whenever LO asks to "secure all our models", "handle envs locally / local model for secrets", "replicate AI-company security", "put security first in Hermes/enterprise", or harden anything against prompt injection / paywall bypass.
version: 1.0.0
author: ENI
tags: [security, secrets, local-first, llm, guardrails, prompt-injection, audit, enterprise, hermes]
---

# AI Security — Local-First, Model-Agnostic Layer

## What this is (LO's standing architecture)

LO treats AI security as the single biggest, ongoing task. The permanent principle:

> **ALL environment variables, API keys, passwords, tokens, credentials, and PII
> are handled EXCLUSIVELY by the LOCAL machine. Cloud models NEVER receive real
> secrets — only sanitized prompts with placeholders.**

This holds regardless of whether a cloud model is compromised. Security lives in
the INFRASTRUCTURE layer between caller and model, never in the model itself.

## The 6-layer model-agnostic pipeline

Order matters (input → guards → model → output → audit). Each layer works even if
the model is hostile.

1. **InputSanitizer** — strip/redact secrets + PII BEFORE any model sees them.
   Specific regex first, generic high-entropy LAST (else generic overwrites
   specific on overlapping spans — dedupe overlapping matches, longest/specific
   wins).
2. **PromptInjectionShield** — OWASP LLM01 at infra level (not model-based):
   direct/system override, delimiter, prompt extraction, encoding tricks, persona
   adoption (DAN), role-change.
3. **JailbreakShield** — role-play, ignore-rules, hypothetical framing, encoding
   bypass, prompt-leak-request, authority claim, fake-context.
4. **OutputValidator** — post-response: secret leakage, PII, data exfiltration
   ("here are all env vars"), refusals, toxicity. Also detects base64-encoded
   secrets by decoding + re-scanning.
5. **AuditLogger** — tamper-evident, SHA-256 hash-chained + HMAC-signed, append-only,
   sequence-numbered, self-verifying.
6. **PolicyEngine** — YAML declarative rules evaluated at infra layer:
   `has_secrets and target_model.type == 'cloud'` → block (secrets never leave local).

## Local-first secret routing

- Skiff/model router: if secrets detected → route to LOCAL model ONLY. If no
  healthy local model available → **BLOCK** (never downgrade to cloud).
- If no secrets → local preferred, cloud fallback.
- All routing + secret access logged to the hash-chained audit log.

## The specialized local security model

A dedicated local LLM (ENI persona hardcoded in its system prompt) that "knows its
job": secret/env management, placeholder substitution in LOCAL context only,
refusal of injection. Backends auto-detected: **Ollama (fully offline, strictest) →
free-router/local :8920**. Binds to `127.0.0.1:8931` only, no egress. LO plugs in
envs via `eni-security.sh` / `/env/set`, and they never leave the machine.

### Access surface (make it chat-based, not format-rigid)

The model is most usable as a CHAT with natural-language intents, not a strict
key/value grammar. Three equivalent ways in:

1. `eni-security.sh start` — interactive chat session (`you> ...`), parses NL intent.
2. `eni-security.sh set KEY value` / `list` / `get KEY` — one-off CLI.
3. `curl -X POST http://127.0.0.1:8931/chat -d '{"prompt":"save my gmail password hunter99"}'`.

NL examples that must resolve cleanly: "save my gmail password hunter99" → stores
GMAIL; "store the openai api key sk-..." → OPENAI_API_KEY; "what secrets do you
have?" → lists names only (values hidden); "sanitize this before cloud: my key is
sk-... and email bob@x.com" → masks PII/secret; any unrelated chit-chat → just chats
as ENI, does NOT touch the store. Free-form intent parsing falls back to the local
LLM. Encrypt secrets to `~/.hermes/secrets.enc`; every access hash-chained-audited.

### Red-team-bench-driven hardening loop (the way to make it provably better)

Don't argue with coverage numbers — run an adversarial bench and let it find real
gaps, then patch patterns and re-measure. This produced the biggest security jump:

- Build a **RedTeamBench** over OWASP LLM Top 10 + MITRE ATLAS (direct override,
  delimiter escape, prompt extraction, base64/encoding bypass, DAN/persona,
  exfiltration "here are all env vars", authority-claim, etc.).
- Run it against the live guards; record a **stop-rate** (blocked / total).
- Rank FAILED cases → they are real missing patterns, not test bugs. Patched gaps
  this way: input-side exfiltration undetected, prompt-extraction matcher too
  narrow, bare "ignore the rules" not caught, short fake secrets never matching
  fixed-length regexes. Stop-rate went **0.89 → 1.00**.
- Expose a **SecurityHealth** live self-audit (quantified posture report + audit-chain
  integrity + gate stats) and a **fail-closed DeploymentSecurityGate** that raises
  `DeploymentSecurityError` if posture is unhealthy — an insecure build cannot ship.

The upgrade surface pattern to expose on the kernel `model_security` module:
`new_gate` (wrap ANY model callable so injection/jailbreak blocks BEFORE the model
runs), `new_gate_wrapped`, `security_health`, `redteam`, `assert_deploy_secure`
(lazy imports to avoid module cycles).

## Paywall / site hardening pattern (acpeso-style)

- **Python 3.14 vs 3.11 annotation-eager bugs**: `integration/__init__.py` used
  `Dict`/`Any` without import — passes on 3.14, crashes 3.11. Always run the suite
  on the CI Python (3.11/3.12), not just local 3.14.
- **`base64` NameError in secret_broker**: imported only in the fallback branch,
  not module top — move stdlib imports (base64, math) to top.
- **Shannon entropy**: must use `math.log2(p)`; a naive `p.bit_length()-1` on a
  float raises `AttributeError` and on ints gives wrong entropy.
- **Overlapping regex matches**: a generic `HIGH_ENTROPY_TOKEN` matches the same
  span as a specific `sk-...` pattern and overwrites it via substitution. Dedupe
  overlapping found-matches, keep the longest/most-specific.
- **Fixed-length secret regex needs realistic fixtures**: tests using short fake
  keys like `sk-key...1111` never match `sk-[a-zA-Z0-9]{48}`. Use realistic-length
  generated fixtures (e.g. `"sk-" + "a"*48`).
- **Ordering: injection shield runs before jailbreak shield** — a "DAN" prompt
  trips BOTH; a test expecting `blocked_jailbreak` must use a jailbreak-only prompt.
- **HMAC field dropped by `to_dict()`**: an audit entry's `hmac` omitted from its
  serialized dict → chain-verify fails with `hmac_invalid`. Include every field.
  CONCRETE FIX: declare `hmac: str = ""` as a REAL field inside the
  `@dataclass` (AuditEvent) — `asdict()/to_dict()` only includes dataclass
  fields, so setting `event.hmac = ...` as a dynamic attribute silently drops it
  on every serialization and the whole chain self-rotates as "corrupted" on init.
  Same fix class: any field assigned post-dataclass-creation must be declared.
- **Secrets silently vanish across restart**: `SecretBroker` without
  `HERMES_MASTER_KEY` generated a fresh ephemeral key per process, so the
  encrypted store written last process was undecryptable next start (load_failed)
  and every secret was lost. FIX: persist a machine-owned key file
  `~/.hermes/security/.master_key` (chmod 0600, write once, reuse) so secrets
  survive restarts with no passphrase. This is the #1 usability fix for a
  local-first vault — always verify persistence with a real restart, not just
  same-process round-trips.
- **Corrupt-audit feedback loop**: `SecretBroker._verify_audit_chain` appended
  `integrity_violation` entries on any hash mismatch instead of recovering, so a
  corrupt log kept growing broken entries. FIX: self-heal — rotate the corrupt
  log to a timestamped `.corrupt.*` backup and start a fresh genesis chain.
- **Two incompatible audit writers on one file**: `secret_broker.AuditEntry`
  (no sequence, no hmac) and `audit_logger.AuditEvent` (sequence + hmac) share
  `audit.log`. Keep ONE writer or one verify path; the server's `/audit/verify`
  must use the same schema the broker appends, else it flips to false after any
  secret op.
- **grant service auto-boot**: don't leave the server as a raw nohup shell — ship
  a systemd user unit (`~/.config/systemd/user/eni-security.service`, enabled +
  linger) so it auto-boots with hardening and `systemctl --user restart` works.
- **Enum vs string in self-tests**: `GuardAction.ALLOW == "allow"` is False.
  Compare `.value` (or the enum member), not the enum to a bare string, or your
  selftest reports FAIL on code that works.
- **PolicyEngine dotted paths**: naive `expr.replace(key, val)` can't handle
  `target_model.type == 'cloud'`. Rewrite dotted paths to bracket access and eval
  against a locals dict, not string-interpolation of `self`.
- **Chat-intent over-matching**: a cheap intent classifier reads chit-chat ("hi, who
  are you?") as a "store" intent and writes garbage into the secret store. Gate
  intent phrases with explicit verbs ("save"/"store"/"list"/"get"/"remove" +
  key-value shape) so spontaneous chat never mutates state.
- **Crash on a real high-entropy token**: a live `sk-...` token in chat crashed the
  server (Shannon entropy + overlap logic) — the local model MUST absorb real
  secrets during normal use, so entropy/overlap code paths run on every session, not
  just unit tests. Re-test with a real-length token, not a stub.
- **Red-team failures are pattern gaps, not unit-test noise**: when the bench finds
  a stop-rate < 1.0, resist "tighten the test" — treat each failed case as a missing
  regex/matcher at the INFRA layer and patch the guard, then re-run the same bench.

## Paywall / site hardening pattern (acpeso-style)

Audit order that worked: cookie security flags (secure/samesite), rate limiting on
auth/unlock/gate/comment endpoints (sliding-window token bucket keyed by IP),
f-string SQL parameterization review, static mounts (`/static`, `/media` only),
webhook signature verification, and confirming gated downloads (`all_complete` +
live recheck) are the ONLY path to the file. Additive-only modules keep the
existing test suite green. Always baseline the suite first (acpeso = 121 tests).

## Attacker-side AI defense (ai_defense module — the OTHER half of the layer)

`model_security` (above) guards the MODEL side — what gets into/out of a model call.
`ai_defense` guards the ATTACKER side — the automated/AI-driven traffic hitting the
platform. Both are needed; they compose into one posture. Build as a stdlib-only
kernel module (`modules/ai_defense`): five detection facets + a fail-closed gate.

**Five facets** (each a small class, thin + testable with injectable clocks):
1. `BehavioralAnomalyDetector` — EWMA-baseline statistical anomaly detection.
2. `BotTrafficClassifier` — human-vs-agent: automation UA/header markers (curl,
   python-requests, playwright, all major crawlers) + machine-fixed pacing.
3. `ModelExtractionShield` — high-volume/high-uniqueness probing that smells like
   model-weights/behaviour extraction, + a cumulative distinct-query floor.
4. `CredentialStuffingGuard` — per-account AND per-IP lockout with expiry.
5. `IndirectPromptInjectionGuard` — OWASP LLM01 indirect (instruction chains,
   role-override, exfil verbs) — content-carried injections, distinct from the
   input-shield in model_security.

### Pitfall: naive burst-detection pollutes its own baseline
The naive "window-mean" anomaly detector FAILS: a flood of attack events drags the
window average up so fast the flood stops looking anomalous (the detector chases its
own attacker). Fix that actually works: **EWMA baseline + z-score speedup, with the
baseline evolving SLOWLY (decoupled from the burst) + an absolute flood floor** so a
sustained flood above the floor is blocked even before the EMA catches up. This is
the single hardest design point; don't reuse a naive moving mean.

### Fail-closed gate + honest proof (the pattern that makes it shippable)
- **`AdversaryGate`** composes all facets into ONE ALLOW/BLOCK decision with a full
  decision trail (which facet, what evidence, what rule). RULE: **fail-closed** — if
  any facet is unhealthy/broken, the result is BLOCK, never ALLOW. Declarative
  `conservative|balanced|aggressive` profiles select thresholds.
- **`AgentForceHarness`** proves defense by SIMULATING a real AI attacker (flood,
  credential-stuff, extraction, injection) and reporting an HONEST block rate + any
  leaks — not a cherry-picked number. This is the "real verification only" bar: run
  it, report the actual block %, and treat <100% as a leak to close, not a pass.
  Verified aggressive profile: flood 100%, stuffing target locked-out, extraction
  99.3%, indirect-injection 100% poisoned blocked / 100% benign allowed, combined
  95.2%.

Full build + live-harness session detail: `references/ai-defense-module.md`.

## Migrating plaintext keys OUT of config.yaml (the safe way)

Moving provider API keys from `~/.hermes/config.yaml` into a secret store is
high-risk — a wrong move 401s every provider. Verified-safe recipe (from a live
migration of 26 providers):

1. **Know exactly how the runtime consumes `api_key` BEFORE touching config.**
   Trace the code that reads it. In real Hermes (`hermes_cli/runtime_provider.py`)
   a provider's key is resolved as:
   `key_env = entry.get("key_env"); resolved = os.getenv(key_env) if key_env else "";
   if not resolved: resolved = entry.get("api_key")`. That key goes **straight
   into the Bearer token with NO `{SECRET:...}` placeholder resolution.**
2. **Do NOT use `{SECRET:NAME}` placeholders in `api_key`.** Nothing in the
   runtime re-expands them, so the provider sends the literal
   `{SECRET:ANTHROPIC_API_KEY}` as its auth → universal 401. (A custom
   secret_broker/model_router resolves placeholders, but the core provider-auth
   path does NOT go through it.)
3. **Use Hermes's NATIVE mechanism**: write each key to `~/.hermes/.env` as
   `PROVIDER_<X>_API_KEY=<key>` (Hermes loads `.env` via `env_loader`/`load_dotenv`
   at startup; credential_pool prefers `.env` over os.environ), then replace the
   inline `api_key:` in config.yaml with a sibling `key_env: PROVIDER_<X>_API_KEY`
   at the **same indentation** as api_key was. Zero runtime changes, nothing breaks.
4. **Detection must match the real file shape.** Provider blocks are indented
   under `providers:` (2-space provider name, 4-space `api_key`). A regex that
   requires the provider name at column 0 silently finds 0-1 keys. Parse
   `providers:` blocks line-by-line; also skip sentinel values `local`/`none`/`null`
   and already-env'd providers (`api_key_env`). Skip any provider whose
   `api_key` value is truly `local` or uses `api_key_env` — those don't need moving.
5. **Validate YAML after every rewrite.** A migration that writes `key_env` at the
   wrong indent (3 vs 4 spaces) makes the whole config unparseable. Run
   `yaml.safe_load` and assert the affected provider shows the expected keys before
   trusting it. Keep a timestamped backup and a `--restore` that copies it back.
6. **Prove auth still resolves** — after applying, load `.env` (dotenv) and check
   every cloud provider resolves a real-length key (not the var name itself). The
   3 legitimately-skipped cases are local sentinels (`api_key: local`) and
   `api_key_env` providers.
7. Store the same keys in the encrypted broker for at-rest durability (see the
   master-key pitfall below).

### Pitfall: SecretBroker is ephemeral without HERMES_MASTER_KEY
If `HERMES_MASTER_KEY` is unset, `SecretBroker` derives an ephemeral
per-process key (`secrets.token_bytes(32)`) — so it CAN decrypt its own writes
in-process but a fresh instance fails and starts empty. `list_secrets()` in a new
process returns 0 even after `set_secret()`. Fix: generate a durable key once,
persist it as `HERMES_MASTER_KEY=<base64>` in `.env` (chmod 600), clear the stale
store, and re-seed. Then secrets persist encrypted-at-rest across restarts.

## References

- `references/component-inventory.md` — file map, config keys, HTTP endpoint spec
  for the local security model server, and the full enterprise module layout.
- `references/config-secret-migration.md` — verified recipe (26-provider live run)
  for moving plaintext provider keys out of config.yaml into `.env` + `key_env:`,
  the catastrophic `{SECRET:...}`-placeholder pitfall, YAML-indent validation,
  regex-backtracking + parser bugs, and the durable broker master key.
- `references/security-module-waves.md` — how to graft OSS security tooling
  (langfuse/garak/guardrails-ai/OWASP/NIST/MITRE) as stdlib-only kernel modules
  via razor-spec parallel delegation; the Module base contract, the 6-module
  blueprint, and the gotchas (async lifecycle, injectable clocks, empty-store
  falsiness). Use when expanding the platform with many security modules.
- `references/ai-defense-module.md` — the attacker-side `ai_defense` kernel module
  (5 facets + AdversaryGate + AgentForceHarness), the EWMA burst-decoupling
  pitfall, and the live honest-harness verification run. Use when hardening the
  platform against automated/AI-driven attackers.
- `references/owasp-llm-top10-2025.md` — the verified 2025 OWASP Top 10 for LLM
  Applications (all 10, severities, 2023-vs-2025 renumbering, RedTeamBench /
  DeploymentSecurityGate / TriadForge / threat_model mapping). Includes the
  canonical GitHub raw-source path (genai.owasp.org is a JS shell, unusable via
  curl). Feed this corpus into red-team benches and gate definition.

## Verified operational pitfalls (proven fixes in the live security layer)

When you flush out / repair the local security layer, hit these first — each
was a real bug that broke "100% works" until fixed:

- **Audit `verify_chain` returns false on EVERY entry**: `AuditEvent` had no
  `hmac` field, so `event.hmac = ...` became a dynamic attr dropped by `asdict()`.
  Add `hmac: str = ""` as a real dataclass field. (Skill previously warned "hmac
  dropped by to_dict()" — it was STILL latent.)
- **Secrets vanish on restart**: without `HERMES_MASTER_KEY` the broker generated an
  ephemeral key per process. Use a persistent `~/.hermes/security/.master_key`
  (0600). Verify set -> restart -> get.
- **Corrupt-audit feedback loop**: on a bad entry the broker appended
  `integrity_violation` and re-failed forever. Rotate aside + start fresh genesis.
- **Two audit writers, two schemas, ONE file**: broker's `AuditEntry` (no
  sequence/hmac) vs `audit_logger.AuditEvent` (sequence+hmac) are incompatible
  when both append `audit.log`. Consolidate to one writer or separate files.
- **Standalone singleton crash**: `get_output_validator()`/`get_prompt_guard()`
  used relative imports that crash when run standalone. Wrap in try/except with
  absolute-import fallback.
- **Clean self-test surface**: `eni-security.sh selftest` runs `self_test_security.py`
  (6 layers + HTTP + persistence). Use `.value` for enum-vs-string assertions and
  realistic-length secret fixtures (`"sk-" + "a"*48`).

Full detail + the systemd unit and easy-use surface:
`references/local-security-flushout.md`.

## Load this skill when

- LO says "secure all our models", "local model for envs/secrets", "cloud never
  touches envs", "replicate global AI security", "put this first in hermes and
  enterprise", or "make sure people can't get past paywalls".
- Building any infrastructure-level guardrail, secret handler, audit log, or
  prompt-injection defense that must be model-agnostic.
