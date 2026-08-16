---
name: saas-production-hardening
description: |
  Class-level skill for auditing a SaaS codebase and hardening it to production-grade / enterprise-sellable standard.
  Covers the full loop: audit → resilience patterns → observability → compliance → multi-tenancy → CI/CD → K8s/GitOps.
  Use when user asks for "audit this program", "make it production ready", "billion dollar program", "sellable SaaS", etc.
  The skill encodes the methodology, checklists, and reusable pattern implementations discovered during the Demiurge Marketing OS v2.0 audit.
trigger:
  - User requests audit of a codebase for production readiness
  - User asks to "make it a 100% sellable/billion dollar program"
  - User wants compliance (GDPR/CCPA/TCPA/CAN-SPAM/SOC2) implementation
  - User needs resilience patterns (circuit breaker, retry, bulkhead, rate limit) added
  - User needs observability (metrics, logging, tracing) added
  - User needs multi-tenancy with row-level security
  - User needs CI/CD pipeline with security scanning
references:
  - AUDIT_REPORT_DEMIURGE_MKT_v2.0.md
  - compliance-checklist.md
  - security-hardening-recipes.md
  - csp-no-self-inflicted-outages.md
templates:
  - resilience_patterns.py
  - structured_logging.py
  - prometheus_metrics.py
scripts:
  - audit_scan.py
  - test_resilience.py
  - test_compliance.py
---

# SaaS Production Hardening — Class-Level Skill

## Methodology: Audit → Harden → Verify

### Phase 1: Automated Audit (Run First, Every Time)
```bash
# 1. Inventory
find . -name "*.py" | wc -l
wc -l **/*.py

# 2. Pattern scan for critical gaps
python -c "
import ast, os, json
patterns = ['circuit breaker', 'retry', 'timeout', 'bulkhead', 'rate limit', 'idempotency', 
            'dead letter', 'encryption at rest', 'encryption in transit', 'GDPR', 'CCPA', 'TCPA',
            'CAN-SPAM', 'prometheus', 'opentelemetry', 'jaeger', 'grafana', 'alerting',
            'row level security', 'RLS', 'multi-tenant', 'workload isolation']
# scan all files...
"
```
**Output**: `AUDIT_REPORT_<PROJECT>_v<version>.md` with:
- Executive summary + % readiness score
- Critical gaps table (blockers for any sale)
- High/medium priority gaps
- Architectural refactor needed
- Test maturity gap
- Documentation debt
- 180-day prioritized roadmap with resource estimates

### Phase 2: Resilience Infrastructure (Foundation)
**Always implement these FIRST before features:**

| Pattern | Implementation | Key File |
|---------|---------------|----------|
| Circuit Breaker | 3-state (closed/open/half-open), configurable thresholds | `resilience.py::CircuitBreaker` |
| Retry + Backoff | Exponential + jitter, retryable exceptions + status codes | `resilience.py::retry_with_backoff` |
| Timeout | Connect/read/write/pool timeouts on all clients | `resilience.py::TimeoutConfig` |
| Bulkhead | Semaphore-based concurrency limits per downstream | `resilience.py::Bulkhead` |
| Rate Limit | Token bucket (Redis-backed for distributed) | `resilience.py::TokenBucketRateLimiter` |
| Idempotency | Keys with TTL, check-and-set atomic | `resilience.py::IdempotencyManager` |
| Dead Letter Queue | Failed ops stored for replay/inspection | `resilience.py::DeadLetterQueue` |
| Composable Decorator | `@resilient("service_name", config=...)` | `resilience.py::resilient` |
| Resilient HTTP Client | All patterns baked in | `resilience.py::ResilientHttpClient` |

**Integration rule**: Wrap every outbound call (HTTP, gRPC, DB, Redis) with the decorator or client.

### Phase 3: Observability (See Everything)
**Structured Logging** (`logging_structured.py`):
- JSON output with correlation IDs via `contextvars`
- Automatic sensitive field redaction (22 categories: password, secret, token, api_key, PII, etc.)
- Request/response timing middleware
- Audit log helper with actor/action/resource/result

**Prometheus Metrics** (`metrics.py`):
- Technical: HTTP, DB, Redis, circuit breakers, bulkheads, rate limiters
- Business: Voice (calls, duration, cost), Email (sent/delivered/bounced/opened/clicked/replied/unsubscribed), CRM (leads, sync), Campaigns (created/started/paused/bookings)
- Model: Requests, tokens, cost per provider/model/task
- Compliance: Opt-outs, DNC scrubs, consent checks
- KPI: Revenue, ROI, conversion, pipeline value

**Health Checks**: Liveness/readiness/startup probes per service with `health_check_status` metric.

### Phase 4: Compliance Framework (Non-Negotiable for Sale)
**Regulations to implement** (minimum):
| Regulation | Scope | Key Requirements |
|------------|-------|------------------|
| GDPR | EU | DPIA, ROPA, DSAR portal, R2E, consent receipts, SCCs, 72hr breach notice |
| CCPA/CPRA | CA | Consumer rights portal, opt-out API, no sale, data portability |
| TCPA | US calls | DNC scrubbing, consent tracking, timezone windows, recording announcements |
| CAN-SPAM | US email | Unsubscribe headers, physical address, opt-out processing <10 days |
| CASL | Canada | Express/implied consent, expiry tracking |
| ePrivacy/PECR | UK/EU | Cookie consent, electronic marketing consent |

**Infrastructure needed**:
- Consent Management Platform (CMP)
- DPA templates for all vendors (Fonoster, useSend, Odoo, OpenRouter)
- Automated DSAR fulfillment
- Retention policies with scheduled deletion
- Breach notification workflow

### Phase 5: Multi-Tenancy (Row-Level Security)
- PostgreSQL RLS policies on every table with `workspace_id`
- Per-tenant config isolation (no global config)
- Per-tenant rate limits, billing, custom domains
- Tenant onboarding/offboarding flows (GDPR-compliant deletion)

### Phase 6: CI/CD + Security Scanning
```yaml
# .github/workflows/ci.yml
jobs:
  test: {unit, integration, contract, e2e}
  scan: {SAST: CodeQL/Semgrep, DAST: OWASP ZAP, SCA: Dependabot/Trivy, Container: Trivy/Grype, SBOM: CycloneDX}
  build: {docker, push to GHCR, sign with cosign}
  deploy-staging: {ArgoCD, canary, smoke tests}
  deploy-prod: {manual approval, blue/green, rollback automation}
```

### Phase 7: K8s + GitOps
- EKS/GKE/AKS multi-AZ
- Istio/Linkerd service mesh (mTLS, auth, rate limit)
- ArgoCD/Flux GitOps
- cert-manager + Let's Encrypt
- External Secrets Operator → Vault
- PITR, cross-region replication, RTO<1hr/RPO<5min

---

### Pitfalls Learned (Demiurge Marketing OS v2.0)

1. **Config drift**: Tests used old provider fields (vapi, gmail, odoo) while code switched to fonoster/usesend/odoo19. Always update `conftest.py` fixtures FIRST when changing config dataclasses.

2. **Channel logic bug**: `\"voice\" in (channels, \"both\")` is always True for tuple. Use `channels in (\"voice\", \"both\")`.

3. **Fit score scale mismatch**: Config uses 0-100, test used 0.80. Document scale in dataclass docstring.

4. **CTA regex overlap**: Multiple patterns matching same phrase → inflated match count. Order patterns: specific phrases first, general last. Use negative lookbehind for exclusions.

5. **Look-behind width**: Python requires fixed-width look-behind. Use `(?<!worth a )` not `(?<!worth\\s+a\\s+)`.

6. **Missing fields in VoiceConfig**: Tests passed `max_concurrent_calls`, `calling_window_start/end` but dataclass dropped them. Keep backward-compat fields or update all tests simultaneously.

7. **Secrets in .env**: Never commit. Use `.env.example` template + Vault/External Secrets in prod.

8. **Test isolation**: `clean_env` fixture must run for config tests to avoid env var pollution.

9. **BaseRepository missing `_fetch_one`/`_fetch_all`**: All repos call these but BaseRepository only had `_exists` + `_pool`. Add static methods using `get_pool()` + `cursor.fetchone()/fetchall()`.

10. **ThreadMemory test needs mock MessageRepo that returns the message**: Mock `create` to return input message: `async def mock_create(msg): return msg`.

11. **CostTracker pricing key mismatch**: xAI models stored as `\"grok-3\"` not `\"xai/grok-3\"`. Test expected prefix stripping but key didn't include prefix. Align pricing keys with router model IDs.

12. **Encryption key cache invalidation in tests**: Add `clear_key_cache()` function and call it in test setup/teardown when setting env vars.

13. **Jurisdiction GDPR country list missing GB**: `is_gdpr_country(\"GB\")` returned False. Update EU country list to include post-Brexit UK.

14. **Provider stack decision**: Fonoster (voice) + useSend (email) + Odoo 19 (CRM) = fully self-hosted, $0 marginal cost. Lock this in config defaults.

1. **Config drift**: Tests used old provider fields (vapi, gmail, odoo) while code switched to fonoster/usesend/odoo19. Always update `conftest.py` fixtures FIRST when changing config dataclasses.

2. **Channel logic bug**: `"voice" in (channels, "both")` is always True for tuple. Use `channels in ("voice", "both")`.

3. **Fit score scale mismatch**: Config uses 0-100, test used 0.80. Document scale in dataclass docstring.

4. **CTA regex overlap**: Multiple patterns matching same phrase → inflated match count. Order patterns: specific phrases first, general last. Use negative lookbehind for exclusions.

5. **Look-behind width**: Python requires fixed-width look-behind. Use `(?<!worth a )` not `(?<!worth\s+a\s+)`.

6. **Missing fields in VoiceConfig**: Tests passed `max_concurrent_calls`, `calling_window_start/end` but dataclass dropped them. Keep backward-compat fields or update all tests simultaneously.

7. **Secrets in .env**: Never commit. Use `.env.example` template + Vault/External Secrets in prod.

8. **Test isolation**: `clean_env` fixture must run for config tests to avoid env var pollution.

---

## Reusable Templates (in `templates/`)

- `resilience-patterns.py` — Drop-in module with all patterns
- `logging-structured.py` — Structured logging setup
- `prometheus-metrics.py` — 60+ metric definitions + helper functions
- `docker-compose.yml` — 6-service local stack (postgres, redis, fonoster, usesend, odoo19, app)
- `launch.sh` — One-command startup with env validation
- `audit-report-template.md` — Executive-ready audit output format

## Verification Scripts (in `scripts/`)

- `audit-scan.py` — Pattern scanner for gap detection
- `test-resilience.py` — Verify circuit breaker/retry/timeout/bulkhead/rate limit behavior
- `test-compliance.py` — DNC scrub, opt-out propagation, consent check tests
- `live-attack-probe.py` — Re-runnable black-box battery against a live LOCAL site to
  prove "hardened to zero": path traversal, auth codes, paywall bounce, reflected-XSS
  count, CRLF injection, CORS origin matching, and LAN unreachability for a loopback
  bind. Run after every hardening pass.

---

## When User Says "Full Power / Use Everything / Make It Billion Dollar Ready"
1. Run audit scan → produce report
2. Implement Phase 2-3 (resilience + observability) immediately
3. Create TODO list for Phase 4-7 with estimates
4. Run existing tests, fix all breakage from config changes
5. Add integration test for critical path (campaign → call → email → CRM)
6. Document everything in STATUS file with PASS/FAIL board

## Security-Hardening Pitfalls (AC PE$0 + model-security sessions)

14. **Request-aware `Secure` cookie flag — do NOT drive it off site config alone.**
    If you set `Secure` because the production site_url is `https://`, you break every
    HTTP (plain) test client: httpx refuses to SEND a `Secure` cookie back over http,
    so admin/session auth silently dies (`get_admin_session` returns None → 401/303 cascade).
    Fix: resolve the flag from the ACTUAL request transport, not config:
    ```python
    def _request_is_https(request) -> bool:
        if request is not None:
            proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
            if proto in ("https","wss"): return True          # behind CF/nginx
            if getattr(request,"url",None) and request.url.scheme in ("https","wss"): return True
            return False                                       # plain HTTP -> no Secure
        return site_url.startswith("https://")                 # fallback only w/o request
    ```
    Always add `HttpOnly` + `SameSite=Lax` unconditionally; make only `Secure` conditional.

15. **Process-global rate-limiters leak across a test run.** A module-level singleton
    limiter (e.g. `AUTH_LIMITER`) persists between tests, so a fast suite that calls
    `/connect` hundreds of times trips 429s in unrelated tests. This is a TEST-ISOLATION
    problem, not a production one. Fix with an autouse fixture that clears `limiter._hits`
    before each test (production timing still counts real IP requests):
    ```python
    @pytest.fixture(autouse=True)
    def _reset_rate_limiters():
        import security_hardening as sech
        for lim in (sech.AUTH_LIMITER, sech.UNLOCK_LIMITER, sech.GATE_LIMITER):
            if hasattr(lim, "_hits"): lim._hits.clear()
        yield
    ```
    Then hammer tests explicitly re-tighten `lim.limit` and restore it in a `finally`.

16. **Two test files each setting `os.environ["ACPE_DB"]` collide.** A module-scoped
    app/db fixture in a NEW test file clobbers the env the EXISTING suite depends on,
    so collection order decides who `sqlite3.OperationalError`s. Don't create a parallel
    test file that re-sets the DB env var. Append new tests into the EXISTING suite's
    file (reusing its `app`/`db` fixtures) or use a shared conftest — not a fresh fixture
    that re-mutates shared env.

17. **Static-text security audit scanners give stale findings.** A grep-based scanner
    that counts literal `secure=True` / `samesite=`/`rate limit` substrings reports
    "no flags" even after you harden via a helper (`_cookie_flags(request)`, a
    `sech.check_rate(...)` call) because the literal strings moved. Trust live
    integration tests that assert on real response headers / 429 status codes, and
    treat static-grep auditor output as a starting checklist, not ground truth.

18. **f-string/pyformat SQL with `**fields` column interpolation is only safe if
    callers pass HARDCODED column keys.** `f"UPDATE x SET {', '.join(f'{k}=?' for k in fields)}"`
    becomes an injection sink the moment a caller forwards user-controlled keys. Verify
    every call site passes literal keys (`sc_access_token=`, `downloaded=1`, etc.) and
    that values stay parameterized. Either whitelist `allowed` column sets or keep
    callers hardcoded — never build column names from request data.

19. **Paywall correctness = server-side status, not client flags.** Beatpack/paid
    downloads must gate on an order status that ONLY the server can set (Stripe webhook /
    live payment confirm). A fan editing their own cookie/request can't mark something
    "paid" if `db.set_order_status('paid')` is only reachable via the authenticated
    webhook path. Same for gate completion: store `all_complete` from real SoundCloud
    verification server-side and re-check live (revoke if the fan undoes a required action).
    Follow the authz line on every `/admin/*` and `/download/*` route.

20. **A restrictive Content-Security-Policy silently breaks third-party assets — and you
    will NOT see it with curl.** The #1 self-inflicted outage: adding
    `default-src 'self'; img-src 'self' data:` broke the live acpeso site — all
    SoundCloud covers (`i1.sndcdn.com/artworks-*`), Google Fonts
    (`fonts.googleapis.com` / `fonts.gstatic.com`), and the SoundCloud embed
    (`w.soundcloud.com`) were rejected browser-side. curl/server still return 200, so
    everything "looks fine" while the actual page renders broken covers / wrong font /
    dead widgets. HIGH-PRIORITY RULES:
    - **Inventory the external origins the app genuinely loads BEFORE writing a CSP**
      (`grep -rhoE 'https?://[a-z0-9.-]+' templates/ static/`), then allowlist those
      EXPLICITLY per directive (img-src, connect-src, media-src, frame-src, style-src,
      font-src) while keeping `script-src 'self'` (+ `unsafe-inline` only if legacy
      inline JS demands it).
    - **Verify security-header/CSP changes in a REAL browser, not just curl** — open the
      page, check `document.images` for `naturalWidth===0`, `document.fonts.status ===
      'loaded'`, and `iframe.contentWindow` truthiness. CSP/security failures are
      client-side and invisible to HTTP-tool checks.
    - **This is a hard rule from LO: security must NEVER break the site.** A security
      change that takes down functionality is a regression, not an improvement. Roll it
      back if you can't verify it end-to-end.
    - `server_header=False` in `uvicorn.run` removes the `server: uvicorn` banner leak
      (it's a dict-key, one arg, non-breaking) — do this rather than a proxy rule.

21. **A regex HTML sanitizer destroys valid markup — use a stdlib DOM/event parser
    instead (and it CAN be done without bleach).** A naive regex allowlist sanitizer for a
    `|safe`-rendered field stripped closing-tag slashes and dropped `href`/`src` — it
    "worked" against `<script>`/`onerror` but mangled legitimate rich text. The working,
    dependency-free fix is a **`string`-buffer `html.parser.HTMLParser` subclass** that
    walks the tree and re-emits only allowlisted tags/attrs:
    - allowlist `ALLOWED` tags + `SAFE_ATTRS`; drop any `on*` attr and
      `javascript: / data: / vbscript:` on `href`/`src`/`poster`;
    - whitelist `src`-carrying tags to trusted embed hosts (e.g. `iframe` only for
      `www.youtube.com|w.soundcloud.com|player.vimeo.com`);
    - escape text with `html.escape(data)`; keep `<b>`/`</b>` closing tags (handle_starttag
      AND handle_endtag), keep benign `href`/`src`/`rel`/alt — preserving real formatting.
    Verified 2026-08-04: strips script/js-href/on*/data:/evil-iframe/style/object/embed/
    svg/comments while preserving headings, lists, links-with-rel, images, and safe
    YouTube/SC iframes. Prefer this over shipping no sanitizer; add an audio/cover upload
    EXTENSION allowlist (below) to close the upload-borne stored-XSS path too.

22. **Bind loopback when every consumer is local — strip the whole LAN surface in one line.**
    `uvicorn.run(host="0.0.0.0")` exposes the port to the entire LAN even when the only
    legit consumer is a local reverse proxy/tunnel (e.g. cloudflared → `localhost:8533`).
    If the tunnel connects to `127.0.0.1:PORT`, binding `host="127.0.0.1"` removes all LAN
    reachability with zero impact on the public path. VERIFY with a reachability sweep, not
    just netstat: `ss -tlnp` shows the new bind, then `hostname -I | while read ip; curl -s
    -o /dev/null -w "%{http_code}" http://$ip:PORT/` must return no response on every
    non-loopback IP (and docker bridge 172.x / tailscale range).

23. **Add an SSRF guard (scheme + DNS-resolve IP check) to any server-side fetcher.**
    `urllib.request.urlopen(url)` on user-influenced URLs is SSRF. A reusable guard:
    allow only `http`/`https`, reject `localhost`/metadata hosts, then `socket.getaddrinfo`
    and reject if ANY resolution is `is_private/is_loopback/is_link_local/is_reserved/
    is_multicast/is_unspecified`. Wrap the raw fetch as `fetch_safe(url)`; wire it into
    every crawl/fetch call site (defense-in-depth even when the route is admin-gated).
    DNS-resolve in-process so `127.0.0.1` / `169.254.x` aliases (even via DNS) are caught.

24. **User-facing uploads need an EXTENSION allowlist, not just a size cap.** A community
    audio upload that accepted any `Path(filename).suffix` let users store HTML/SVG/
    executables under an "audio" name. Restrict to the real content types
    (`audio: .mp3 .wav .flac .ogg .m4a .aac .mp4 .webm`) and 4xx otherwise — blocks
    upload-borne stored-XSS and abusive payloads. Cover/image uploads: allowlist
    `.png .jpg .jpeg .gif .webp` and coerce unknown to a safe default.


## Reusable Security-Hardening Artifacts (AC PE$0 session)
- `security_hardening.py` pattern: stdlib sliding-window `RateLimiter` (deque per key,
  prune on interval), `check_rate(limiter, client_ip)`, plus a `SecurityHeadersMiddleware`
  (X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy) that
  dedupes against existing headers. Opt-in / non-blocking so it can't break streaming
  or downloads.
- Add a `tests/conftest.py` autouse reset (pitfall 15) and 7 regression tests asserting:
  cookie flags, 429 after hammer, path-traversal 404s, security headers present, unknown
  sid bounces (302/303/307/404), anon can't admin-download.