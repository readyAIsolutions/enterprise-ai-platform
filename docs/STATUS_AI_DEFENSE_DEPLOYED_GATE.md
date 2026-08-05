# STATUS_AI_DEFENSE_DEPLOYED_GATE.md

Deployed-AI-gate layer — TriadForge adversary engine verifies the AdversaryGate
actually defends LIVE sites over HTTP (not just in-process). Wave completed
2026-08-04 on branch `upgrade/gold-picks`.

## What was built

1. **`modules/ai_defense/gate_http.py`** — deployable WSGI middleware wrapping the
   fail-closed `AdversaryGate` in front of a real app. Block -> `429 Too Many
   Requests` + JSON body (facet/reason/profile) + `X-Adversary-Gate: blocked` +
   `Retry-After`. Per-path hooks: auth (`/login`...) -> credential-stuffing guard,
   model (`/api/complete`...) -> extraction shield, content (`/submit`...) ->
   indirect-injection guard, else anomaly+bot. IGNORE_PREFIXES for static/health.
   Also `make_gate_server` (wsgiref daemon) + `AdversaryGateMiddleware` (wrap any
   WSGI app) + `defend_site.py` one-command launcher with `--verify`.

2. **`~/Desktop/TriadForge/triadforge/engines/adversary.py`** — TriadForge engine
   (kind="adversary") that attacks a LIVE URL with the 4 AI/agent vectors over
   real HTTP and reports block-vs-leak + gate-header reactions. Emits a leak
   finding ONLY when reachable attack traffic leaks (deployed-vs-source drift).
   Rate-limited, LOCAL-only, scope_ok-gated.

3. **Fixtures + e2e proof** (`tests/sample/e2e`) — identical app UNDEFENDED vs
   gate-wrapped. Proven funnel below.

## PASS/FAIL board (real run numbers)

| Check | Result |
|-------|--------|
| Undefended site -> leak findings | PASS — 5 findings (flood/bot/stuffing/extraction/injection all 100% leak), 4 high + 1 medium |
| Defended site (aggressive) -> confirmed blocked | PASS — 0 leak findings; all 5 vectors blocked 100% w/ gate header (bot 25/25, stuffing 30/30, flood 40/40, injection 20/20, extraction 50/50) |
| Defend_site.py --verify self-flood | PASS — 30/30 flood blocked (100%) |
| TriadForge full suite | PASS — 19 passed (16 original + 3 adversary) |
| Enterprise full suite | PASS — 2828 passed, 0 failed (+123 incl. gate_http + adversary integration) |
| gate_http enterprise tests | PASS — 5/5 |
| Git | PASS — committed `9f6e013`, pushed to `upgrade/gold-picks` |
| Hermes bridge CLI | PASS — `scan-adversary --help` parses; enterprise facade integration returns real leaks/blocks |

## What adds R / what to drop

- **ADD**: Deploy the `AdversaryGateMiddleware` in front of any LO-owned site that
  exposes auth/model/content endpoints (acpeso, TriadForge dashboard, future
  products). It closes the class of gap TriadForge exists to catch — the in-process
  gate isn't enough; the deployed enforcement is what matters.
- **ADD**: Run `triadforge.py scan-adversary --url <site>` in the pre-launch /
  CI gate of any LO site to prove the deployed defense reacts before shipping.
- **DROP**: nothing — this is pure additive.

## UNVALIDATED

- _Defended vs undefended on a REAL production site_ (e.g. acpeso) — the e2e
  proves the mechanism on fixtures; a real-site run post-deploy would confirm the
  default `balanced` profile holds under realistic traffic, not just the fixture's
  `aggressive` setting.
- _Whether `balanced` profile catches slow, distributed AI attacks_ — the fixture
  uses aggressive + single-IP; distributed/botnet pacing tuning is untested here.

## Residual risk (honest)

Deploying the middleware adds a dependency on `enterprise.modules.ai_defense`
(enterprise repo) to the site's runtime. For non-enterprise sites this is a
coupling consideration; a standalone copy of the gate could be inlined if needed.
The gate never sees secrets (ENI Rule 0) — only request metadata + content for
injection scanning.
