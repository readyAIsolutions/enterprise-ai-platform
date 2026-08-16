---
name: self-hosted-security-testing
description: >-
  Build LO's self-hosted security "hacker box" — a full program that ATTACKS his own
  products (not third parties) from white/grey/black-box vantage points, verifies each
  break with real evidence, then funnels fixes back in and tracks them to closure. Covers
  the black/grey/white-box model, the ZAP/Burp/DefectDojo findings data model
  (severity + confidence + evidence + CWE + remediation), Nuclei-style rules-as-data YAML
  DAST, Bandit/regex SAST + secret scanning, LLM prompt-injection/jailbreak probes, SARIF
  2.1.0 export + auto-fix snippets + a fix queue, and a dark FastAPI dashboard. Use
  whenever LO asks to "test our own securities", "make a white black grey hacker box",
  "actually verify our shit is secure", "funnel findings back into the program", or build
  any vuln scanner / self-hardening security product.
---

# Self-Hosted Security Testing ("Hacker Box")

## What this is

LO's idea: a **full, self-hosted program that attacks HIS OWN products like a real
attacker**, verifies each break with evidence, then **forges the fixes back in** and
tracks remediation to closure. The working product is **TRIAD FORGE** at
`~/Desktop/TriadForge/` (FastAPI + sqlite + dark dashboard on `:8400`). This skill
captures the reusable architecture + the non-obvious pitfalls so the next scanner build
starts correct.

**Always frame the safety line**: this tests LO-OWNED / localhost targets only, every
target is acknowledged in-scope (`scope_ok`), scans are rate-limited, and it runs on
127.0.0.1. It's defensive self-hacking, never third-party scanning.

## The three boxes

| Mode | Input | Finds | Engine |
|------|-------|-------|--------|
| **BLACK-BOX** | URL (no creds) | reflected XSS, SQLi, cmd-inj, missing HSTS/X-Frame/CSP, cookie HttpOnly/Secure flags, server fingerprinting, dir listing | `engines/web.py` WebEngine |
| **GREY-BOX** | URL + auth token | black-box + authenticated surface (auth injected via header) | same WebEngine with token |
| **WHITE-BOX** | source dir | hardcoded secrets, os.system/shell=True, SQL concat, pickle, eval, verify=False, Bandit SAST, insecure dep pins | `engines/source.py` SourceEngine |

Plus an **AI-ADVERSARY box** (live-URL kind="adversary"): attacks a DEPLOYED site over
HTTP with the 4 AI/agent vectors (flood, bot-ua, credential-stuffing, model-extraction,
indirect-injection) and reports real block-vs-leak + `X-Adversary-Gate` header reactions.
Emits a leak finding only when reachable attack traffic leaks. This is the **deployed-gate
proof** — it closes deployed-vs-source drift for the AI Defense `AdversaryGate` (the
in-process AgentForceHarness only proves the gate OBJECT runs). Requires the gate be
deployed via `enterprise.modules.ai_defense.gate_http.AdversaryGateMiddleware` /
`make_gate_server`, or `defend_site.py`. Proven: undefended site → 5 leaks; gate-wrapped →
0 leaks.

Plus an **LLM box** (endpoint): prompt-injection / jailbreak / prompt-extraction /
sensitive-info probes with a local regex detector (optionally reuse the enterprise
`model_security` pipeline, but degrade gracefully to a self-contained detector).

## The funnel (the killer feature)

1. Findings carry full **evidence** (request + response + matched part), **severity**,
   **confidence**, **CWE**, and **remediation**.
2. **SARIF 2.1.0 export** — drop into any CI (GitHub/GitLab) as a gate.
3. **Auto-fix snippets** for common header/config findings (HSTS, X-Frame-Options, CSP,
   cookie flags).
4. **Fix queue**: open → mark_fixed → platform re-verifies → closed. PR stub for
   white-box + git targets.
5. **The proof pattern**: a deliberately-vulnerable sample fixture app → scan → find the
   intentional breaks; then a hardened copy → re-scan → **0 break-rules**. This proves the
   scanner actually fires AND the funnel closes. Do this before claiming "it works".

## Findings data model (industry standard — copy this)

```
finding_id, scan_id, rule_id, wstg_id, cwe_id,
severity (info/low/medium/high/critical), confidence (low/med/high/confirmed),
title, description, remediation, references[],
evidence {method, url, request_raw, response_raw, matched_part, timing_ms},
status (open/in_triage/accepted_risk/false_positive/fixed/verified),
created_at, fixed_at
```
Severity colors: critical `#d9534f`, high `#f0ad4e`, medium `#ffc107`, low `#5bc0de`,
info `#777`. This is the ZAP/Burp/DefectDojo model — every finding is provable and rated.

## Rules-as-data (Nuclei-style), not hard-coded checks

Each check = one YAML doc with `id, wstg_id, cwe_id, severity, mode, method, path, param,
payloads, matcher_words, matcher_status, matcher_negative, check_header, description,
remediation, references`. An evaluator runs them. Adding a check = adding a YAML file.
Three rule shapes:
- **HEADER rules** (`check_header` set): fetch `/`, inspect response headers. HSTS/CSP/
  X-Frame → `matcher_negative: true` (finding when the secure value is ABSENT).
- **WORD/BODY rules**: GET `path`, finding if a matcher word appears (dir listing).
- **ACTIVE injection** (`payloads` + `param`): send payloads into the param, finding on
  reflection / SQL-error / uid= markers.

## PITFALLS (bought with real pain this session)

1. **Respect severity vs confidence.** `confidence` ≠ `severity`. A **static pattern
   match** (regex SAST / secret scan / Bandit) is a *candidate*, not a confirmed exploit —
   give it **LOW/MEDIUM confidence**. Only a dynamic reproduction with real request+
   response evidence (DAST) earns HIGH. Failing this, a white-box scan reports hundreds of
   "high" findings that turn out to be harmless (`os.system('lsof -ti :8000')` = hardcoded
   constants, no injection; `API_KEY_MANAGE="webh...e"` = a permission-scope STRING, not a
   secret; a Shannon-entropy helper gets flagged as a "secret"). Triage before fix.
2. **Filter Bandit noise or the board is useless.** Bandit's B101 (assert), B104, B105/
   B106/B107 (hardcoded strings/http), B108 (tmp file), B110 (bare except), B311 (random),
   B303, B310 fire on every codebase and drown real findings. On the enterprise repo the
   white-box scan produced **5236 findings, 5005 of them B101**. Adding a `_BANDIT_NOISE`
   skip-set cut it to **85** (63 high, 4 med, 18 low) — the real signal. Skip these
   informational-grade codes before scanning.
3. **Multi-doc YAML rules need `yaml.safe_load_all`.** If rules are stored as multiple
   docs separated by `---` in one file, `yaml.safe_load` errors. Use `safe_load_all` and
   iterate. Also quote remediation strings containing `:` (e.g. header directives) or
   `yaml.safe_load` throws "mapping values are not allowed here".
4. **`references` is a SQL reserved word.** Naming a sqlite column `references` makes
   `CREATE TABLE` fail with a near-`references` syntax error. Use `refs_text` (or quote it)
   and keep the insert/select in lockstep.
5. **Wrap each rule in try/except inside the engine.** One bad/unreachable rule must not
   kill the scan. Also wrap the whole engine run in the API layer so an unreachable target
   returns a clean `{scan_id}` (scan marked `error`) instead of a 500.
6. **Thread/async hygiene in FastAPI scans.** Run async engines via `asyncio.to_thread`
   (+ an inner `asyncio.run` for sync engines) so a scan never blocks the endpoint.
   Re-persist findings ONLY for engines that don't persist their own (web/source persist
   via `persist_findings`; the LLM engine persisted itself — avoid double rows).
7. **`algo_id`/path de-dup white-box findings by (rule_id, file, line)** so Bandit +
   regex SAST don't double-report the same sink.
8. **A FixRequest body that duplicates a path param fails.** If the endpoint is
   `/api/findings/{id}/status` and the body model requires `finding_id`, path-only POSTs
   422. Make the body `finding_id` optional (the path is authoritative).
9. **LLM-box detections must test OFFLINE.** Inject a fake `responder` callable into the
   engine via ctx so tests control model responses deterministically (leaky response →
   finding; clean response → 0 findings). Don't gate tests on a live LLM endpoint.
6. **Deployed-vs-source drift is real and high-value — always check it.** After the
    fixture loop, run the black-box scan against the LIVE product (LO's own running
    service), not just the source. On acpeso (`:8533`) it returned 4 findings (missing
    X-Frame/HSTS/CSP + server banner). Root cause: the `SecurityHeadersMiddleware` had
    been written into `server.py` that day, but the systemd `acpeso.service` had started
    ~20h EARLIER and was never restarted — so the running box served OLD code with NONE
    of the headers. The fix existed on disk; the deployed target was still vulnerable.
    That is precisely the class of gap a scanner exists to catch. Fix = restart the
    service (`systemctl --user restart <svc>`), not just edit code.
11. **The in-process gate is NOT the deployed gate — verify the transport layer.** When
    proving the AI Defense `AdversaryGate`, the AgentForceHarness runs the gate against
    Python objects. That only shows the gate OBJECT would block. Use the TriadForge
    `adversary` engine against the LIVE URL to confirm the deployed site actually returns
    429/403 + `X-Adversary-Gate` for each vector. Two real bugs surfaced here: (a) a WSGI
    status string of `str(429)`="429" (3 chars) fails wsgiref's >=4-char validation →
    every 429 becomes a 500 → the scanner "sees" a leak; always emit "429 Too Many
    Requests". (b) the auth/credential-stuffing hook must call `gate.facade.check_auth()`
    (not `gate.check_auth`) and check `judgement.malicious` (not `.allowed`) — wrong attr
    = AttributeError → 500 → leaks. Count reachability separately from blocks: status 0
    (unreachable) is NOT a leak.

## Running against live targets (not just the fixture)

The fixture loop proves the scanner fires; it does NOT prove your real products are
shipped-secure. The verified live-target workflow (acpeso, 2026-08):

1. **Scan the live URL with the black-box engine** (`scan-web <url>`). Note the findings
   and, critically, the target's *current* headers.
2. **Trace the root cause before fixing.** For each missing header/finding, check WHEN the
   hardening code was written vs WHEN the service last started
   (`systemctl --user show <svc> -p ActiveEnterTimestamp`). If code-postdates-start,
   you have deployed-vs-source drift — the service needs a RESTART.
3. **Apply the fix to source** (e.g. add the missing `Strict-Transport-Security` +
   `Content-Security-Policy` directives — the header middleware often has an incomplete
   `HEADERS` dict).
4. **Restart the service** so the hardening actually ships.
5. **Verify with a live header check** (curl the headers: `x-content-type-options`,
   `x-frame-options`, `referrer-policy`, `strict-transport-security`,
   `content-security-policy`, `server`).
6. **Re-scan** → expect the count to drop (acpeso went 4 → 1; only the cosmetic
   `server: <framework>` banner leak remained, low/accept).
7. **Funnel the finding to the KB** (`kb-push --scan <id>`) so it persists as a
   `security_finding` pattern alongside memories/chats. The scan id in the KB shows the
   target URL + rule + CWE, making it searchable later.

This full loop (attack → root-cause → fix → restart → re-verify → KB) is the "funnel
back into the product" value LO wanted, proven on a real production box.

## Build order (proven)

1. **Core framework first** (models, db, severity, rules_loader, engine base) — everything
   depends on it. Smoke-test DB CRUD + rules load before parallelizing.
2. Then **parallel-delegate the independent engines** (web, source, llm) + UI with razor
   specs against the verified core (exact file paths, function signatures, import paths,
   test commands). Each subagent self-verifies with pytest then you re-run independently.
3. Remediation (SARIF + fix snippets) + FastAPI/UI.
4. **Prove with the vulnerable-fixture loop**, THEN run against real products.

## References

- `references/owasp-wstg-blackbox.md` — condensed OWASP WSTG v4.2 black-box test catalog
  (categories, ~30 core checks w/ WSTG IDs + CWEs), ZAP/Burp scanner model, Nuclei YAML
  template reference, and the research-backed severity/UX notes (CVSS, OWASP risk rating,
  dashboard layout). Use as the check list when writing rules.
- `references/triadforge-blueprint.md` — the working TRIAD FORGE build: file layout,
  engine contracts, API + dashboard endpoint map, SARIF shape, and the verified e2e funnel
  results (vulnerable→found→fixed→zero). Copy/modify for the next product.

## Load this skill when

- LO says "test our own securities", "make a white black grey hacker box", "verify our
  stuff is actually secure", "funnel findings back into the program", or wants any
  vulnerability scanner / self-hardening security product with a UI.
- Building DAST (web), SAST/secrets (source), LLM probes, SARIF export, or a security
  findings dashboard.
