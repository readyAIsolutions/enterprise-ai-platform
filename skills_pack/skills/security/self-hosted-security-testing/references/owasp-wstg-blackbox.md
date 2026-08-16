# OWASP WSTG v4.2 Black-Box Check Catalog (research-condensed)

Source: OWASP Web Security Testing Guide v4.2 (stable; v5 in draft).
Use as the checklist when writing black/grey-box web rules.

## Highest-value categories for an automated black-box scanner
1. Information Gathering (INFO), 2. Config/Deployment (CONF), 4. Auth (ATHN),
5. Authorization (ATZ), 6. Session (SESS), 7. Input Validation (INPV),
8. Error Handling (ERRH), 9. Weak Crypto (CRYP), 11. Client-side (CLNT),
12. API (APIT). Skip manual-only: Identity Mgmt, Business Logic.

## Core-30 black-box checks (WSTG ID → CWE)
1. INFO-03 robots/sitemap/security.txt → CWE-200 (feed crawler seeds)
2. INFO-02 server fingerprint → CWE-200
3. INFO-08 framework fingerprint → CWE-200 (tech→CVE)
4. INFO-05 content comments / hidden inputs → CWE-200
5. INFO-06 entry-point spider/crawler → CWE-200
6. CONF-03 backup/extension (.bak, ~, .swp, .old) → CWE-540 source disclosure
7. CONF-04 unreferenced files / dir-busting (/.git/HEAD, /backup, /admin) → CWE-530/538
8. CONF-05 admin interfaces → CWE-419
9. CONF-06 HTTP methods (TRACE=XS, PUT) → CWE-650
10. CONF-07 HSTS header → CWE-319
11. ATHN-01 creds over HTTP → CWE-319
12. ATHN-04 auth bypass (verb tamper, X-Original-URL, forced browse) → CWE-287
13. ATHN-06 cache by sensitive page → CWE-524
14. ATZ-02/04 IDOR (object-id tampering: id=1,2,3) → CWE-639 (highest-yield authed check)
15. SESS-02 cookie flags (Secure/HttpOnly/SameSite) → CWE-614/1004
16. SESS-06 logout invalidation → CWE-613
17. INPV-01 reflected XSS → CWE-79 (payload reflection in GET/POST)
18. INPV-02 stored XSS → CWE-79 (store-then-replay)
19. INPV-05 SQLi (error/boolean/time-based; `'` then `1 AND 1=1` vs `1=2`) → CWE-89
20. INPV-11 code injection LFI/RFI (`../../etc/passwd`, `php://filter`) → CWE-98
21. INPV-12 command injection (`;id`, `|id`, `$(id)`) → CWE-78
22. INPV-04 HTTP param pollution → CWE-235
23. ERRH-01/02 error page / stack trace info disclosure → CWE-209
24. CRYP-01 weak TLS (SSLv3/TLS1.0/1.1, RC4, CBC) → CWE-327
25. CLNT-07 CORS misconfiguration → CWE-942
26. CLNT-09 clickjacking (missing X-Frame-Options/CSP frame-ancestors) → CWE-1021
27. CLNT-04 open redirect → CWE-601
28. APIT-02 REST API enumeration + auth → (CWE)
29. CONF-11 cloud metadata SSRF probe (169.254.169.254) → CWE-918
30. INPV-19 SSRF → CWE-918

## ZAP / Burp scanner model (copy this)
- PASSIVE scan: non-intrusive, header/body/cookie inspection on real traffic, zero
  payloads. Runs always.
- ACTIVE scan: intrusive, payload injection into params, controlled by threshold
  (aggressiveness) + strength (payload count). Fuzzer inserts payloads.
- Alert model: Risk (Info/Low/Med/High) + Confidence (Low/Med/High/Confirmed) +
  CWE + Description + Solution + Reference + Evidence (exact req/resp snippet).
- Separate threshold from strength; make rules data-driven (Burp BChecks, Nuclei YAML).
- Evidence is the most important credibility field — always store raw request +
  response + matched part.

## Nuclei YAML template shape (author-to-copy)
```yaml
id: apache-detect
info: { name, author, severity: info|low|medium|high|critical,
        tags: tech,apache,detect, classification: { cve-id, cwe-id, cvss-score } }
http:
  - method: GET
    path: ["{{BaseURL}}"]
    matchers:
      - type: word
        words: ["Apache"]
        part: header
        negative: true/false   # negative = finding on ABSENCE (missing-HSTS style)
      - type: status; size; regex; dsl
    extractors: [regex/word/json]
```
Matchers: word / regex / status / size / binary / dsl. `dsl` lets you compute
(e.g. `status_code == 200 && contains(body,'admin')`).
Multi-step: multiple requests can flow values between them (login → use token → test).

## Severity systems
- CVSS v3.1: 0 None, 0.1–3.9 Low, 4.0–6.9 Medium, 7.0–8.9 High, 9.0–10 Critical.
- OWASP Risk Rating: Risk = Likelihood(1-9) x Impact(1-9), mapped Low/Med/High/Critical.
- Qualitative Low/Med/High/Critical + Info (ZAP/Burp/Nuclei shorthand).
- Colors: critical red #d9534f, high orange #f0ad4e, medium yellow #ffc107,
  low blue #5bc0de, info gray #777.

## Dashboard UX (ZAP/Burp/DefectDojo patterns)
- Dashboard: 4-6 KPI cards + severity donut (Chart.js) + findings-by-target bar +
  recent-scans table + newest-findings feed.
- Findings list → row click opens a right-side DRAWER (not new page): severity chip,
  evidence req/resp (match highlighted), remediation, status actions.
- Timeline: stacked severity-over-time bar + per-run cards.
- Status model: open / in_triage / accepted_risk / false_positive / fixed / verified;
  color status distinctly from severity; accessible (don't rely on color alone).

## Remediation feedback loops (from research)
- Snyk/Dependabot auto-open dependency fix PRs (advisory DB → fixed version).
- Semgrep carries a `fix:` key producing a one-line patch; LLM-assisted patches
  (Copilot Autofix) need human approval.
- SARIF (https://sarifweb.azurewebsites.net/) is the interchange standard every CI ingests.
- Tiers: deterministic (dep bumps/secret removal — safe auto-PR), rule-based autofix
  (review required), LLM patches (approval flow).
- NIST SSDF SP 800-218 formalizes feeding findings back into development.
