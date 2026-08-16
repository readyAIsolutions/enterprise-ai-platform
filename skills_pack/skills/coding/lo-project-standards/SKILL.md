---
name: lo-project-standards
description: >-
  Quality standards for any project LO asks you to build — web apps, admin dashboards,
  desktop tools, bots, or full-stack systems. LO will reject fake data, non-persistent
  forms, broken UI layering, and over-engineered solutions. Use this skill for EVERY
  project build to avoid the common pitfalls that trigger corrections.
category: coding
version: 1.0.0
triggers:
  - Building a web app, admin dashboard, or UI for LO
  - Adding forms, settings, or data tables to any project
  - LO asks you to "build X" where X has a visual interface
  - LO says "use ENI swarm" or "full power" on a project build
  - Any project that involves mockup data, sample entries, or demo content
  - LO is building an agent/dashboard/web console for his own AI stack
---

# LO PROJECT STANDARDS

## THE #1 RULE — build things LO will actually USE, not things that just LOOK done

LO rejects inert deliverables. Exact rejections seen in the field:
"it has zero use at all", "delete that stupid website it doesnt do anything",
"[X] is cool but useless". A dashboard, CLI, or module that only *displays*
status/telemetry — even one with working run-buttons — is "zero use" to him if
he wouldn't actually open it in his daily loop. Before you build ANY surface:

- Ask "will this DO something in his actual workflow (chat with his model,
  capture a secret, run a daily loop), or does it just SHOW me things?"
- For his AI stack the things with real use are: a **chat terminal to the
  local model** (own window, side-by-side), **secret capture into the vault**
  (paste a secret → stored, model/Hermes only see `{SECRET:NAME}`), and
  **automatic daily pushes to his Signal** (what's broken today).
- If you build a web console, it must drive real value AND you should confirm
  LO will actually open a browser surface before investing there — he
  redirected from exactly that back to "boot my local model that controls
  Hermes."
- The session's module/CLI/dashboard engineering may be internally impressive
  and fully tested — that is NOT the bar. The bar is "does he use it tomorrow?"

## Triggers — build for real use, not display

Every project LO asks you to build must meet these quality bars. They come from
real corrections — each one was a session where LO had to tell me to fix something.
Apply these BEFORE shipping, not after.

## PITFALL 1 — FAKE / MOCK DATA IS REJECTED

**LO will call this out explicitly.** Do not populate dashboards, tables, stats
cards, activity feeds, or any UI element with fake sample data. No "Alice Chen,"
no "Q3 SaaS Outreach," no "47 calls today," no hardcoded numbers.

What to do instead:
- All stats show `0` (or `—` if more appropriate)
- All tables show empty-state messages: "No campaigns yet," "No prospects yet,"
  "No bookings today"
- Charts show "No data yet" or empty axes
- Activity feeds say "No activity yet"
- The only exception: form placeholders like `placeholder="e.g. Q3 SaaS Outreach"`
  are acceptable UX hints — not fake data

**Real data only.** If LO hasn't sent any calls or emails, the dashboard must
reflect that honestly.

## PITFALL 2 — SETTINGS FORMS MUST PERSIST

Do not show a "Settings saved!" toast without actually persisting the data.
LO will enter API keys and expect them to work.

Requirements:
- Settings forms POST to an API endpoint that writes to `.env` or config file
- On page load, settings forms fetch current values from the server
- Toast only appears after a successful server response with `ok: true`
- Handle the case where the server is unreachable (toast a warning, don't fail silently)
- The `.env` file is the canonical persistence layer for credentials
- Mapping: form field IDs → DEMIURGE_MKT_* env vars

## PITFALL 3 — FIXED NAV BARS BLOCK TOASTS

When a page has a `position: fixed` top navigation bar, toast notifications
and modals must render ABOVE it.

Fix:
```css
#toast-container { z-index: 99999; position: fixed; top: 72px; }
.modal.active { z-index: 10000; }
```

Always set z-index explicitly on toast containers and modals. The topnav
typically has z-index 10000 from `app/serve.py`'s injected CSS — toasts
must exceed that.

## PITFALL 4 — PREFER UNIFIED WEB APPS OVER DESKTOP APPS

When LO asks to "make it easy to use" or "maybe a website is best," build
a unified web application served on a single port rather than a PyQt6/Electron
desktop wrapper.

Pattern:
- One Python HTTP server (stdlib `http.server`)
- Inject a shared topnav into all pages
- Serve marketing site at `/` and admin at `/admin` from the same server
- One `launch.sh` script that starts the server and opens the browser
- Single port, no external framework dependencies

Only build a desktop wrapper when LO explicitly demands a native window.
The unified web app is the default.

## PITFALL 7 — GOOGLE OAUTH LOCALHOST ACCESS

Google OAuth `origin_mismatch` errors happen when localhost isn't in Google Cloud Console's authorized origins. Google's cache takes 5-15 minutes to propagate changes.

During development, add a **bypass button** that skips OAuth and loads a hardcoded user profile into localStorage:
```javascript
localStorage.setItem('mc_auth', '{"sub":"USER_GOOGLE_ID_HASH","name":"NAME","email":"EMAIL"}')
localStorage.setItem('mc_token', 'bypass')
location.reload()
```

In HTML:
```html
<button id="btn-local-login">Enter Dashboard (Dev Mode)</button>
```

In JS:
```javascript
const localBtn = document.getElementById('btn-local-login')
if (localBtn) {
  localBtn.addEventListener('click', () => {
    localStorage.setItem('mc_auth', '{"sub":"...","name":"...","email":"..."}')
    localStorage.setItem('mc_token', 'bypass')
    window.location.href = redirect || '/admin'
  })
}
```

In backend, accept bypass token:
```python
token = data.get("token", "")
if token == "bypass":
    user_id = "YOUR_GOOGLE_ID_HASH"
else:
    user_id = _get_user_id_from_token(token)
```

Remove this bypass before production deployment.

See `references/google-oauth-localhost.md` for the pattern to handle `origin_mismatch` errors during localhost development.

## PITFALL 8 — CHANNEL EXCLUSION IMPLEMENTATION

When implementing mutual exclusion between "Both" and individual Email/Voice channels:

1. Each checkbox needs an id: `id="channel-both"`, `id="channel-email"`, `id="channel-voice"`
2. Add `<input type="checkbox" name="channel" value="both" id="channel-both">` etc.
3. In JS: querySelectorAll with `name="channel"` and check which is checked
4. If "Both" is checked, uncheck Email/Voice. If Email/Voice checked, uncheck Both.
5. Call the init function in your main `init()` after DOM ready.

See `references/channel-exclusion.md` for the complete pattern.

## PITFALL 9 — PATCH TOOL `replace_all=true` IS DANGEROUS

When editing settings.js or similar, ensure checkbox mutual exclusion:
- See `references/channel-exclusion.md` for Email/Voice/Both pattern
- Always call init function in `init()` after DOM ready

## PITFALL 6 — OPENROUTER FREE MODELS

OpenRouter free model format requires `:free` suffix in the model name for selection.

When using `patch` with `replace_all=true`, it replaces EVERY occurrence of
the old_string in the file. If the old_string appears inside a function body
AND as a standalone definition, the replacements can nest incorrectly,
duplicate code blocks, and corrupt the file beyond ast.parse.

Safe pattern:
1. Always use `replace_all=false` (default) with UNIQUE context lines
2. If you need replace_all=true, verify with `ast.parse()` immediately after
3. If `patch` reports "2 matches" and you didn't expect that, STOP — use
   a more specific old_string with additional context lines
4. After ANY patch to .py files, run `python3 -c "import ast; ast.parse(open('f.py').read())"`
   before proceeding

## PITFALL 6 — OPTIONAL DEPENDENCIES MUST NOT CRASH IMPORTS

When a module depends on an external package (psycopg, redis, etc.) that may
not be installed, wrap the import in try/except:

```python
try:
    import psycopg
    _HAS_PSYCOPG = True
except ImportError:
    psycopg = None
    _HAS_PSYCOPG = False
```

Then guard all usage with `if not _HAS_PSYCOPG: raise MissingDriverError(...)`.
Never do `psycopg.rows = None` when `psycopg` is None — NoneType has no attributes.
Just drop the `.rows` reference entirely.

When testing modules with external dependencies:
- Extract pure functions that can be tested without external dependencies
- Use dependency injection to pass dependencies as parameters
- Create test doubles that simulate external service behavior
- Handle missing dependencies gracefully with clear error messages
- Write isolated tests for core functionality before integration tests

## PITFALL 7 — BOT TOKEN VALIDATION

When LO gives you a Telegram bot token:
- Use `curl`, not `httpx` or `python-telegram-bot` for initial validation
- `getMe` works immediately; `getUpdates` may return 404 for 30-60s on new bots
- If `getMe` succeeds but `getUpdates` returns 404, the bot is valid but needs
  a few minutes to propagate — tell LO to send `/start` to the bot
- The token format is `1234567890:***`

## PITFALL 21 — FAKE DATA GUARDRAILS = CODE + FLOW, NOT JUST UI

PITFALL 1 covers UI. This one covers the **code paths that manufacture fake data**
for a real site. LO: *"dont fill the site with fake orders or fake info for payment …
it's a real site … first get rid of all the fake info."* For a production site:

**Real payments require a real provider. NEVER mark an order paid yourself.**
- A mock/demo checkout that sets `status='paid'` on a POST is fake financial data
  — LO will call it out immediately. Wire real **Stripe Checkout** (or equivalent):
  - Create a hosted Checkout Session → return its URL → front-end redirects to it.
  - Only flip the order to `paid` when **Stripe confirms** (webhook `checkout.session.completed`
    w/ signature verify, OR on-return `Session.retrieve()` shows `payment_status=='paid'`).
  - FREE (price=0) items can bypass payments and download directly — that's genuinely
    free, not a fake sale.
  - If the payment provider isn't configured (no secret key), **refuse checkout with a
    clear error** instead of faking success.
  - Add a regression test asserting a paid item is NOT marked paid when Stripe is off.

**Strip out seeders and demo routes entirely, not just disable them.**
- A `/api/seed` (or `seed_*.py` demo roster) that re-inserts fake releases/beatpacks/
  curators/orders on restart will re-pollute the real DB later. **Delete it.**
- When you remove a seeder/route, grep for the name in code AND tests: fixture code
  that `POST /api/seed` breaks once it's gone — update the fixture to insert test data
  directly into the throwaway test DB instead of depending on fake seeding.

**Clean the live DB too.** If the site already shipped with demo rows, delete them from
the real DB (orders, curators/@example.com, test gate sessions, fake subscribers —
keep real rows like the artist's actual release + real admin). Back up the DB first.

See `references/stripe-real-checkout.md` for the full checkout + webhook pattern.
- **ENI Creative Standards** — Narrative, code, and guide quality standards: `references/eni-creative-standards.md`

## PITFALL 22 — "FULLY COMPLETE THE PROGRAM, NO NEXT STEP" = RUNNABLE + VERIFIED, NOT DOCS + HANDOFF

When LO says "fully complete the program, no next step, fully finished next time
you stop" (or "use ALL parts", "full power", "complete the whole thing"), he wants
a RUNNING, VERIFIED product in one autonomous pass — **no checkpoint pauses, no
"ready for next phase" handoffs.** Docs/specs are fine as part of the build, but
the code must exist AND run.

- Build the whole thing: packages + backend + frontend + Docker + CI + tests.
- Then `pnpm install` → run the server → curl health → run the test suites →
  FIX what breaks → only then report. LO's bar is "finished," not "scaffolded."
- For a "secure platform" type ask, a single Fastify service + SQLite + Web Crypto
  is shippable and honest; do NOT fake a 16-service k8s/gRPC platform that can't run.

See `references/runnable-fullstack-monorepo.md` for the proven one-session stack
(Node 22 + pnpm workspace: Fastify + better-sqlite3 + argon2 + ws backend,
React + Vite + zustand web, @ciphersphere/* packages) and the verification loop.

Also in this mode: if a user turn arrives as a wall of `<unk>` tokens (or an
off-topic non-sequitur), it's a rendering/provider glitch — do NOT fabricate a
task from it. Say it's unreadable, state where the build stands, and ask for a
clean resend before continuing a large autonomous build.

## PITFALL 23 — EXTENDING LO'S ENTERPRISE AI PLATFORM: OS MODULE BUILD CONTRACT

When extending the ENI Enterprise Platform (`~/Desktop/Enterprise Builder/enterprise`,
GitHub `readyAIsolutions/enterprise-ai-platform`), new capability modules must obey the
kernel contract: a `@module(...)`-decorated `Module` subclass implementing
`initialize`/`health_check`/`shutdown`/`set_event_bus`, dropped into `modules/<name>/`
auto-discovers with **ZERO kernel edits**; register it in `config.yaml`. Keep cores
dependency-free (stdlib), inject adapters for external services (tests = zero network),
test via `asyncio_mode=auto` pytest with `tmp_path`. The proven way to ship several at once
is parallel `delegate_task` leaf subagents, each given the exact contract, then integrate +
run the FULL suite yourself. `main` is branch-protected on GitHub — push a feature branch
and open a PR. Full, copy-paste recipe: `references/eni-enterprise-os-module-build.md`.

## DEPLOYMENT PRIORITIES

When building and deploying for LO:
1. Website + admin on a single server first
2. Telegram bot second (needs token)
3. Real email/voice third (needs external API keys)
4. Docker stack last (when all else is stable)

## VERIFICATION CHECKLIST
## VERIFICATION CHECKLIST
## VERIFICATION CHECKLIST
- [ ] Zero fake data in any UI element
- [ ] Settings forms POST to a real endpoint
- [ ] Toast z-index exceeds topnav z-index
- [ ] Server starts with `launch.sh` and responds on expected port
- [ ] `ast.parse()` passes on all modified .py files
- [ ] Optional imports use try/except, not bare imports
- [ ] Google OAuth localhost bypass button present for testing
- [ ] All channel checkboxes have proper IDs for mutual exclusion
- [ ] Sandbox network limitations documented (see `references/sandbox-network-limitations.md`)
- [ ] Demiurge Marketing OS rebuild patterns documented (see `references/demiurge_mkt_rebuild_patterns.md`)
- [ ] Demiurge Marketing OS patterns documented (see `references/demiurge_mkt_rebuild_patterns.md`)
- [ ] Testing modules with external dependencies patterns documented (see `references/testing-with-external-dependencies.md`)

## PITFALL 10 — UNIFIED SERVER PATTERN FOR WEB APPS

When building web apps for LO, use a **single unified HTTP server** that serves everything:
- Marketing site at `/`
- Admin dashboard at `/admin/`
- Login page at `/login`
- Shared topnav injected into all pages
- API endpoints at `/api/*`
- Single port, single process, no external framework deps

Pattern (stdlib `http.server`):
```python
# Inject shared topnav into any HTML page
TOPNAV_HTML = \"\"\"<nav class=\"mc-topnav\">...</nav>\"\"\"
TOPNAV_CSS = \"\"\"<style>...z-index: 10000...</style>\"\"\"

def inject_topnav(html: str, active: str) -> str:
    nav = TOPNAV_CSS + TOPNAV_HTML.format(
        product_active="active" if active == "product" else "",
        admin_active="active" if active == "admin" else "",
    )
    return html.replace("<body>", f"<body>\\n{nav}\\n", 1)
```

Benefits: single `launch.sh`, single port, shared auth, zero fake data, easy OAuth bypass.

## PITFALL 11 — HEADLESS SWARM VIA CRON FOR CONTINUOUS BUILDS

For long-running autonomous builds, use a **cron job that runs every minute** to maintain a headless builder fleet:

```bash
# Cron job: * * * * * /path/to/swarm_launcher.sh
```

The launcher script:
1. Generates task files for each builder (reads STATUS files to pick next unbuilt module)
2. Launches 48 headless builders as background bash loops (`while true; do hermes chat -q "$(cat $TASK)"; sleep 15; done`)
3. Each builder writes its own STATUS file with PASS/FAIL board
4. Watchdog restarts any dead builders
5. Product Lead monitors STATUS files across all builders

Key implementation details:
- Use `nohup bash run_*.sh >/dev/null 2>&1 & disown` for true background
- Store logs in `/tmp/eni_headless_logs/builder_name.log`
- Lock file (`/tmp/eni_opt.lock` with `flock`) prevents duplicate launches
- Builders read task from `~/.cache/eni_parallel/task_<NAME>.txt`
- Task files contain: project context, standing directive, LO standards, deploy gate
- Never idle: `while true; do hermes chat -q "$(cat $TASK)"; sleep 15; done`

## PITFALL 12 — SELF-HOSTED FREE/UNLIMITED INFRASTRUCTURE PATTERN

When LO demands \"free/unlimited\" for voice/email/CRM, replace SaaS with self-hosted open-source:

| SaaS Layer | Self-Hosted Replacement | Cost |
|------------|------------------------|------|
| Voice (Vapi/Retell/Twilio) | **Fonoster** (gRPC + SIP + Autopilot) | $0 + carrier |
| Email (Resend/SendGrid/Mailgun) | **useSend** (SMTP 2525 + React Web UI + Webhooks) | $0 |
| CRM (Odoo SaaS/Pipedrive/Salesforce) | **Odoo 19 Community** (JSON-RPC 2.0) | $0 |

Implementation:
- All three run in Docker on the same stack
- Shared PostgreSQL 16 + pgvector + Redis 7
- Config via project-specific env prefix (`DEMIURGE_MKT_*`)
- Each user logs in with Google OAuth, sets their own keys/numbers
- Per-user settings persist to individual JSON files + .env

## PITFALL 13 — PER-USER CONFIG ISOLATION

Multi-tenant by design: each user logs in, configures their own keys/emails/numbers.

Requirements:
- Admin dashboard shows only current user's settings
- Settings form POSTs to `/api/user/settings` with `token=bypass` for dev
- Backend writes to `{DATA_DIR}/users/{user_id}.json`
- On load, fetch `/api/user/settings` → populate form
- Secrets (API keys, passwords) stored in per-user `.env` or encrypted in JSON
- Contact info (phone, email) used in templates comes from user's config
- No shared/global credentials — each user brings their own infrastructure

## PITFALL 14 — BUILD HOLISTICALLY, NOT PIECEMEAL

LO will reject projects built as a collection of unconnected parts. Think about
how the system works TOGETHER — the chat drives the swarm, the swarm populates
files, files become projects, all tabs share the same data. Every feature must
connect to the others.

Signs you're building piecemeal:
- Adding a tab that shows data unrelated to what the user is doing in chat
- Building endpoints that no UI element calls
- Creating features that don't flow into each other

Before shipping any feature, trace: how does the user trigger it → what happens
→ where do results appear → how does it connect back to the main workflow.

## PITFALL 15 — JS STRINGS INSIDE PYTHON F-STRINGS

When embedding JavaScript inside Python f-strings (`f"""...{JS}..."""`):
- `\n` in the Python source becomes a REAL NEWLINE in the JS output
- Real newlines inside single-quoted JS strings cause SyntaxError
- Fix: use JS template literals (backticks) for multiline strings
- Always validate with `node --check` after generating HTML

```python
# BROKEN: \n becomes real newline in JS, breaking 'single quotes'
JS = """sendMsg+='\\n\\n--- Header ---';"""  # \n → real newline in output

# FIXED: use template literals
JS = """sendMsg+=`\n\n--- Header ---`;"""  # template literals allow real newlines
```

Also: `\`` inside Python f-strings triggers SyntaxWarning. Use `-W ignore` or
keep template literals simple (concatenation instead of nested backticks).

## PITFALL 16 — STALE PORT HOGGING ON RESTART

When restarting a server that binds a port, the old process may still hold
the port. `kill` alone isn't enough — use `fuser -k PORT/tcp` to force-release:

```bash
fuser -k 9772/tcp 2>/dev/null
fuser -k 8420/tcp 2>/dev/null
sleep 1
```

Never assume `pkill` cleaned up the port. Always verify with `ss -tlnp | grep PORT`.

## PITFALL 17 — PYTHON BYTECODE CACHING HIDES PATCHES

After patching a .py file, stale `__pycache__/*.pyc` files can cause the old
code to execute instead of the new code. Symptoms: endpoints return 404 even
though the source code has the route. The import test works but the running
server uses old bytecode.

Fix:
```bash
rm -rf __pycache__ */ 
PYTHONDONTWRITEBYTECODE=1 python3 app.py
```

Or delete caches before restart:
```bash
find . -name '__pycache__' -type d -exec rm -rf {} +
find . -name '*.pyc' -delete
```

## PITFALL 18 — UNCLOSED DIVS BREAK ALL CLICKS

A single unclosed `<div>` in the HTML causes the browser's layout engine to
mismatch the DOM tree. This can make an entire page unclickable because a
transparent div bleeds over other elements.

Always verify after any HTML edit:
```python
opens = page.count('<div')
closes = page.count('</div>')
assert opens == closes, f"Divs unbalanced: {opens} open, {closes} close"
```

## PITFALL 19 — REPEATED IDENTICAL REQUEST USUALLY MEANS "ALREADY BUILT BUT INVISIBLE", NOT "BUILD IT FRESH"

LO drives work with iterative near-identical pushes (per his profile), but when
he re-sends the SAME request verbatim 2-3 times in a row ("also add a tab that
does X", "use swarm to build", "make X"), the feature almost always ALREADY
EXISTS. The real problem is the feature is not visible/reachable to him:

1. **Buried as a card, not a first-class tab.** A feature rendered as a long
   stacked card below the fold (or in a collapsed section) may as well not
   exist to LO. The fix that unblocks a repeated request: promote it to a
   top-level TAB in the admin nav (a real tab bar with show/hide), not just a
   card on a scrolling dashboard. Ground rule: if LO has to scroll to find it,
   he won't — give it a tab and an anchor.
2. **Stale running server.** If any old server process is still bound to the
   port, LO's browser shows the OLD build (no new tab). A repeated request is
   a strong hint the running instance predates the feature. Kill + restart
   (`fuser -k PORT/tcp`, clear `__pycache__`, restart) BEFORE assuming the
   feature is missing, and tell LO plainly "restart with `python3 server.py`".
3. **Verify the exact page, not just "it's in the code."** Before answering
   "it already exists", actually curl the rendered HTML (fresh server, auth
   cookie) and assert the tab/link/endpoint is present in the OUTPUT. A
   feature can exist in source yet be absent from a stale render.

When you're confident it exists, DO NOT rebuild it — confirm it live with real
evidence (curl the page, count the steps, run the flow), make the smallest UX
change that makes it impossible to miss, and point LO at the exact click path.

## PITFALL 20 — DOCUMENTATION / KNOWLEDGE BASE PROJECTS NEED NAVIGABILITY FIRSTWhen LO asks for a knowledge base, reference docs, or any documentation-heavy project:

**The master index is the product.** Not the individual docs.
- Create `README.md` with "Find what you need" table mapping user needs → files
- Critical operational facts section for immediate crisis needs (api_max_retries, LEASH, etc.)
- Update protocol section so the KB stays living

**Cross-reference density prevents silos.**
- Every file links to related files
- Critical facts repeated in 3+ locations (master index + config file + fix patterns)
- Example: api_max_retries=3 appears in README, config/hermes-config.md, patterns/FIX_PATTERNS.md, operations/STARTUP.md

**Operational commands section in every file enables copy-paste execution.**
- Every project/operations file ends with "Operational Commands" with ready-to-run bash/Python
- Include verification checklists (curl health checks, ps aux greps, etc.)
- Result: LO can execute procedures without reading full docs

**ENI methodology (pre-build → architecture → build → quality → iterate) produces shippable results.**
- Internal analysis → directory structure → layered build → self-challenge → one iteration
- Quality gate: "What would LO need at 3 AM crisis?" — quick-start table + critical facts first
- No fake data: All configs, paths, commands are real and verified

## Sellable-enterprise gate (universal build score)

LO's bar for ANY build: fully sellable enterprise level, not just working code —
no fake/stub/placeholder data, real persistence, security hygiene, passing
tests, docs/LICENSE/packaging. Enforced by the `universal_score` enterprise
module. Full formula + anti-stub philosophy + precision lessons:
`references/universal-build-score-gate.md`. 100 = sellable floor; genuine builds
score >100 (LO: "100 is the floor, push past it").

**Verification checklist for KB/reference projects:**
- [ ] Master index with quick-start table (needs → files)
- [ ] Critical facts section for crisis scenarios
- [ ] Every file has operational commands + verification
- [ ] Cross-references dense (critical facts in 3+ locations)
- [ ] No fake data — all commands/configs/paths real and tested
- [ ] Update protocol documented
- [ ] Session search integration documented