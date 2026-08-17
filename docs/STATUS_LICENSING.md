# STATUS — Licensing + Product-Auth Layer (B1 + B2)

Date: 2026-08-16
Scope: enterprise/licensing (independent of the multiplayer server)
Status: COMPLETE — all tests green

## What was built

### B2 — licensing/license.py (LicenseManager)
Server-side, stdlib-only license engine (HMAC-SHA256-signed keys):

- Tier constants: FREE = 10 builders, TEAM = unlimited, PRO = per-seat,
  HOSTED = unlimited (managed fleet). Exported from the package root.
- `LicenseManager.create(key, tier, max_builders, expires) -> signed token`
  builds a JSON payload (`{key, tier, max_builders, expires}`), base64url-encodes
  it and appends an HMAC-SHA256 signature over the payload using a server-held
  secret. FREE defaults to 10 seats; PRO uses the per-seat value supplied;
  TEAM/HOSTED are unlimited.
- `LicenseManager.validate(token) -> {valid, tier, seats, expires}` verifies the
  embedded signature in constant time (`hmac.compare_digest`), rejects malformed
  or tampered keys (`InvalidLicenseError`), and rejects past-expiry keys
  (`ExpiredLicenseError`).
- `LicenseManager.broker_enforce(token, builder_count) -> bool` returns whether
  `builder_count` concurrent builders fit the license (FREE/PRO are seat-capped,
  TEAM/HOSTED always allow). Also enforces expiry.

### B1 — licensing/auth.py (AuthManager)
Minimal but real product-auth token helper, in-memory with expiry:

- `issue_token(tenant, scope)` issues a `secrets.token_urlsafe(32)` bearer token
  and stores `{tenant, scope, expires}` (1h default lifetime) in a thread-safe
  in-memory store keyed by SHA-256 digest.
- `verify_token(token) -> {tenant, scope}` verifies with constant-time
  comparisons (`hmac.compare_digest`), distinguishing a tampered/unknown token
  (`InvalidTokenError`) from an expired-but-known one (`ExpiredTokenError`).
  Stale tokens are purged on access.
- Top-level `issue_token` / `verify_token` module functions use a default shared
  manager.

## Tests — licensing/tests/test_licensing.py (17 passed, 0 failed)

Required cases proven:
- valid FREE key with 12 builders -> broker_enforce returns False (exceed) PASS
- valid TEAM key allows 100 builders (and 10k) -> True PASS
- expired key is invalid (validate + broker_enforce raise ExpiredLicenseError) PASS
- token verify rejects a tampered token (flipped char) -> InvalidTokenError PASS

Additional coverage: PRO per-seat boundary, HOSTED unlimited, future expiry,
tampered license payload/signature, signature differs across secrets, unknown
tier rejected, executory exceed helper, token round-trip (manager + module-level),
unknown/empty/expired token rejection, independent tokens.

## Run

    cd "/home/hunter/Desktop/Enterprise Builder/enterprise"
    python3 -m pytest licensing/tests/ -v          # 17 passed

## Files
- enterprise/licensing/__init__.py        (re-documented, re-exports API)
- enterprise/licensing/license.py         (new — LicenseManager, tiers)
- enterprise/licensing/auth.py            (new — AuthManager, token issue/verify)
- enterprise/licensing/tests/test_licensing.py (new — 17 tests)
- enterprise/STATUS_LICENSING.md          (this file)

## Notes / issues
- Initially `broker_enforce` only checked the signature, not expiry, so an
  expired key wasn't rejected there — fixed by checking expiry in both
  validate() and broker_enforce().
- Auth token store initially purged expired entries before verification, making
  expired tokens indistinguishable from tampered ones — changed the store to
  return known-but-stale matches so verify_token can raise ExpiredTokenError
  (tampered/unknown still raise InvalidTokenError).
- No files owned by other streams were touched (multiplayer/server/*, tenancy
  left alone).
