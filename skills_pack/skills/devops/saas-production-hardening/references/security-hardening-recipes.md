# Security Hardening — Real Session Recipes (AC PE$0 + Local-First AI Security)

Condensed, reusable recipes from a security-hardening pass on `~/Desktop/ac pe$0`
(an existing Starlette/UVicorn site) and the "security-model-first" local-AI layer.
Trade secrets that made tests stay green while hardening.

## Paywall / gated download integrity (what "can't get past paywalls" means in code)

The leak-free shape:
- **Paid content** (`/beatpack/order/{oid}`): gate on `order.status == 'paid'`, and
  `db.set_order_status('paid')` must be reachable ONLY from the authenticated Stripe
  webhook handler (or a live `_confirm_stripe_payment` that asks Stripe). No client
  request arg can set paid.
- **Gate content** (`/download/{sid}`): require `gate_sessions.all_complete`, set
  server-side only after REAL SoundCloud verification of like/repost/comment/follow.
  Do a live re-check on download and revoke if the fan undid a required action.
- **Every `/admin/*` route** (admin file downloads, mark-paid) calls `_need_admin(request)`
  → 401 for non-admin. Verify each one, don't assume.
- **Static/media**: mount `/static` and `/media` only. In the media handler strip
  traversal with `Path(name).name` AND whitelist filename prefixes
  (`cover-`/`release-`/`media-`). This keeps `.env`, `storage/*.wav` (lossless files),
  and the DB off the public web.

## Cookie hardening that does NOT break localhost / test clients

All auth cookies (fan/admin/gate) stamped with `HttpOnly` + `SameSite=Lax` always, and
`Secure` ONLY when the real request transport is HTTPS. See SKILL.md pitfall 14 for the
`_request_is_https(request)` helper. Critical: if you force `Secure` from site config
alone, the plain-HTTP TestClient won't echo the cookie back and every admin test 401s.

## Testing the hardening (keep the suite green)

- Add `tests/conftest.py` with an autouse fixture that clears every process-global
  limiter's `_hits` between tests (pitfall 15).
- Regression tests to add: cookie flags asserted from real `Set-Cookie` headers;
  hammer `/connect` → 429; `/media/..%2F.env` → 404; security headers present;
  unknown gate sid bounces (302/303/307/404, never 200); anonymous `/admin/release/{id}/download` → 401.
- Do NOT put these in a new test file that re-sets `os.environ["ACPE_DB"]` — it
  collides with the existing suite's env. Merge into the existing `tests/test_*.py`.

## SQL injection scan interpretation

Grep for f-string SQL (`f"UPDATE ... SET {', '.join(...)}"`). It's only a real sink if
a caller forwards user-controlled column keys. Hardened version: whitelist `allowed`
column set, or keep every call site passing literal keys with parameterized values.
Audit ALL call sites of a dynamic-column `update_gate_session(sid, **fields)` style
function before condemning it.

## Local-first AI secret architecture (security-model-first)

Pattern the user wants (and rebuilt) so AI never leaks envs to cloud models:
- `secret_broker.py`: secrets stored encrypted (Fernet/AES) at `~/.hermes/secrets.enc`,
  audited with a hash-chained + HMAC log. Prompt sanitization replaces secrets/PII with
  placeholders `{SECRET:OPENAI_API_KEY}` / `{PII:EMAIL}`.
- `model_router.py`: if a prompt contains secrets → LOCAL model only; if no healthy local
  model exists → BLOCK (never send secrets to cloud).
- `prompt_guard.py` + `output_validator.py`: pre-flight injection/jailbreak/exfil
  detection and post-response leakage/toxicity/refusal checks, entirely model-agnostic
  (regex + heuristics), so they hold even if the model is fully compromised.
- `local_security_model.py` / `-server.py`: bind `127.0.0.1:8931` only, no egress;
  backend auto-detect: Ollama (max offline) → llama.cpp → free-router local tier.
  The system prompt hardcodes the security persona + "never touch/echo secrets."
- Enterprise kernel: register a `model_security` module at `priority: 0, required: true`
  so it boots FIRST; give it `SecurityPipeline` (sanitize → guards → model → validate → audit).

Key gotcha: order secret-detection regex specific patterns BEFORE generic high-entropy
patterns, and de-duplicate overlapping matches (keep the most specific span) or a generic
`HIGH_ENTROPY_TOKEN` match will swallow a specific `OPENAI_API_KEY` tag.
