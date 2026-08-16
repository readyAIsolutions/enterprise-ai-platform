# Demiurge Marketing OS — Build Patterns

## Architecture
- Location: `/home/hunter/Desktop/Projects/Demiurge_Trading/demiurge_os/`
- Flask app on :8000, Postgres + Redis + Piper TTS + XTTS voice clone
- Docker Compose stack: app, postgres, redis, piper, xtts, odoo (CRM), usesend (email), fonoster (telephony)
- AI brain: google/gemini-3-flash-preview via OpenRouter + free-router fallback

## Key patterns discovered

### Google OAuth + admin email bypass
When Google OAuth is configured (GOOGLE_CLIENT_ID/SECRET set), email login is disabled.
For testing, allow admin emails to bypass via `/login/email` when ADMIN_LOCAL_MODE=1:
```python
if google_enabled():
    if _cfg.ADMIN_LOCAL_MODE:
        email = request.form.get("email").strip().lower()
        if email in _admin_emails():
            _login_or_create(email, name, None, None)
            return redirect(...)
    abort(404)
```

### Stripe credit purchasing with DEV fallback
`/billing/buy/<idx>` checks `stripe_gateway.enabled()`. When Stripe keys aren't set,
grants credits directly (DEV mode) so the flow is testable without real payments.

### XTTS voice clone dependencies (CRITICAL)
coqui-tts is fragile with version pins. Working combination:
```
torch==2.3.0
torchaudio==2.3.0  (CPU index)
coqpit==0.0.17
TTS==0.22.0
```
First clone call downloads ~2GB model — needs 5+ minute timeout.

### Multipart voice clone fix
XTTS server expects `speaker` as file part, `text` as form field:
```python
requests.post(url + "/clone", data={"text": text}, files={"speaker": (name, f)})
```
NOT `data=text.encode()` (causes "Data must not be a string").

### Test configuration
Set `GOOGLE_CLIENT_ID=""` and `GOOGLE_CLIENT_SECRET=""` in test conftest to enable email login.
Point `FREE_ROUTER_URL` to dead port for fast deterministic tests.
Use `SessionLocal.remove()` before TRUNCATE to avoid deadlocks.

### Agent builder interview flow
Templates define `interview_questions` list. Create form with `template_key`, `business_name`, and `q0`..`qN` fields.
AI auto-generates system_prompt for "any business" and outbound templates via `_ai_system_prompt()`.

### Call triage: AI + rules
`call_intelligence.analyze()` combines LLM classification with keyword rules.
Takes the MORE severe of the two — emergencies never under-ranked.
Priority order: EMERGENCY > HIGH > MEDIUM > LOW.
