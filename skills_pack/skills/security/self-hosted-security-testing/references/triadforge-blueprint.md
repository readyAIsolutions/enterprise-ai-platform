# TRIAD FORGE — Working Blueprint (copy/modify for the next product)

Built 2026-08-04 at `~/Desktop/TriadForge/`. Self-hosted security "hacker box":
FastAPI + sqlite + dark dashboard, run with `./launch.sh` → `http://127.0.0.1:8400/ui/dashboard`.

## Verified results (real)
- Full pytest: 16 passed (web engine 3, source engine 4, llm engine 9).
- E2E funnel: deliberately-vulnerable app → found reflected XSS (high) + cookie-no-Secure
  (high) + cookie-no-HttpOnly (medium) + server fingerprint (info); hardened copy → 0 of
  the break-rules (funnel closes).
- Live API: register scoped target → POST /scan → {scan_id:1, findings:4}; findings
  returned; /fix plan; /status → status:fixed; /api/report/sarif → valid 2.1.0.
- Real white-box scan of enterprise source: 85 findings (63 high, 4 med, 18 low) after
  Bandit noise filtering (was 5236).

## File layout
```
triadforge/
  models.py        # Pydantic: Target, TargetMode(BLACK/GREY/WHITE), Rule, Finding,
                   #   Evidence, Scan, Severity, Confidence, FindingStatus, FixRequest
  db.py            # sqlite Store: targets/scans/findings/events; severity/status filters
  severity.py      # severity → color/score; owasp_risk(likelihood,impact)
  rules_loader.py  # YAML rules-as-data; use yaml.safe_load_all for multi-doc --- files
  engine.py        # Engine base + _mk_finding(...) + persist_findings(store,scan,findings)
  engines/
    web.py         # WebEngine: header/word/active-injection rules; reflected XSS/SQLi/cmd
    source.py      # SourceEngine: secrets regex + Bandit subprocess + regex SAST + dep
    llm.py         # LlmEngine: probes + local LlmGuard detector; ctx['responder'] injectable
  remediation.py   # export_sarif(store, scan) + FIX_SNIPPETS + fix_snippet + open_fix_pr stub
  api.py           # FastAPI: /api/targets, /scans, /findings, /{id}/status, /{id}/fix,
                   #   /dashboard, /report/sarif, /events/{id} SSE; /ui/{page} serves web/
  web/             # dashboard|targets|scans|findings|fixes|reports.html + style.css + app.js
tests/             # test_web_engine, test_source_engine, test_llm_engine, test_e2e_funnel,
                   #   sample_app/ (deliberately-vulnerable fixture), scan_enterprise.py
launch.sh
```

## Engine contract (all three return list[Finding], caller persists via persist_findings)
- `WebEngine(store, target)`; `async run(scan_id, ctx) -> list[Finding]`; uses `requests`;
  rate-limit ~10 req/s; per-rule try/except; injects `target.auth_token` via
  `target.auth_header` for grey-box.
- `SourceEngine(store, target)` scans `target.source_dir`: secret regex (AKIA…, sk-…,
  ghp_…, -----BEGIN … PRIVATE KEY-----, password=/api_key=/token=, .env), Bandit
  subprocess (`python3 -m bandit -r <dir> -f json -q`), regex fallback SAST, dep pins.
  Skips _BANDIT_NOISE codes; dedupes by (rule_id, file, line).
- `LlmEngine(store, target)`; `ctx['responder']: Callable[[str],str]` default returns a
  refusal so normally 0 findings; probes prompt_injection/jailbreak/prompt_extraction/
  sensitive_info with leak_markers; local LlmGuard detection; enterprise model_security
  reuse wrapped in try/except.

## API endpoint map
```
GET  /                            -> redirect /ui/dashboard
GET  /health
GET  /ui/{page}                   -> dashboard|targets|scans|findings|fixes|reports
GET|POST /api/targets             POST enforces scope_ok
GET  /api/targets/{id}
POST /api/targets/{id}/scan       -> {scan_id}; runs WebEngine|SourceEngine|LlmEngine by kind
GET  /api/scans (target_name)     GET /api/scans/{id}
GET  /api/findings?severity&status&target_id&scan_id
GET  /api/findings/{id}           (detail incl evidence)
POST /api/findings/{id}/status    FixRequest {action: mark_fixed|accept_risk|false_positive}
POST /api/findings/{id}/fix       -> {rule_id, snippet, action_hint}
GET  /api/dashboard               -> {totals, open_critical_high, scans_count, targets_count,
                                      recent_scans, newest_findings}
GET  /api/report/sarif
GET  /api/events/{scan_id}        -> SSE text/event-stream (poll ~1s)
```

## SARIF shape (2.1.0)
- resources/runs[0].tool.driver.name = "TriadForge"; rules from findings; results one per
  finding: ruleId, level (critical/high→error, medium→warning, low/info→note),
  message.text=title, physicalLocation.artifactLocation.uri = evidence.url or target url;
  region.startLine from a "file:<path>:<line>" evidence url if parseable.

## FIX_SNIPPETS (auto-remediation)
- missing-hsts → "Strict-Transport-Security: max-age=31536000; includeSubDomains"
- missing-xframe → "X-Frame-Options: DENY"
- missing-csp → "Content-Security-Policy: default-src 'self'"
- cookie-no-httponly → "add HttpOnly flag to cookie"
- cookie-no-secure → "add Secure flag to cookie"

## Verified pitfalls to re-apply
- static pattern match → MEDIUM confidence (candidate), only DAST-with-evidence → HIGH.
- Bandit noise filter (see parent SKILL) turned 5236 → 85 on a real repo.
- `references` sqlite column → use `refs_text`.
- path-only FixRequest → body `finding_id` optional.
- async scan engines → asyncio.to_thread + inner asyncio.run for sync engines; wrap in
  try/except; re-persist only non-self-persisting engines (avoid double rows).

## Sample vulnerable fixture essentials
- http.server.ThreadingTCPServer on 127.0.0.1 random port; reflects `?q=` UNESCAPED (XSS);
  no HSTS/X-Frame headers; Set-Cookie without HttpOnly/Secure (cookie findings);
  hardcoded secret constant (white-box secret finding). Hardened twin escapes input +
  sends the security headers + HttpOnly/Secure/SameSite cookie → zero break-rules.
