# Demiurge Marketing — Project Reference

LO's AI sales platform at `/home/hunter/Desktop/Projects/Demiurge_Trading/demiurge_os/`.

## Quick Start
```bash
cd /home/hunter/Desktop/Projects/Demiurge_Trading/demiurge_os
docker compose up -d  # postgres, redis, piper, app on :8000
```

## Key URLs
- App: `http://localhost:8000`
- Google OAuth: hunter.laidlaw.work@gmail.com = admin (ADMIN_EMAILS in .env)
- Admin email bypass: POST `/login/email` works for admin emails when ADMIN_LOCAL_MODE=1
- Tests: `cd /home/hunter/Desktop/Projects/Demiurge_Trading/demiurge_os && .venv/bin/python -m pytest tests/ -v`
- 16 tests (all must pass)

## Architecture
- Flask app factory at `demiurge_os/web/app_factory.py`
- Blueprints: auth, dashboard, billing, voice, engines, agents, crm
- Models in `demiurge_os/app/models.py` (Client, User, VoiceAgent, Call, Email, Lead, CreditTransaction, UsageLog)
- Call engine: `demiurge_os/engines/caller.py` — baresip SIP dialing, users bring their own VoIP.ms sub-account creds
- Piper TTS at `:5001` — free local voice generation
- XTTS at `:5002` — voice cloning (model ~2GB, first call downloads, pin transformers==4.38.2)

## LO's Design Preferences for Demiurge
- Real calls and emails (not simulated campaigns)
- CRM must be a visible TAB in nav, not hidden in "Calls · Email · CRM"
- Agent selector dropdown in Calls/Email forms — must be able to choose which agent does the work
- No tech stack leaks in UI (no mention of Fonoster/Piper/free-router/open source)
- Dashboard must show CRM pipeline with stage filters
- Voice agents page must show multiple agents with descriptions
- Templates must have emoji + clear descriptions + setup time estimates

## Common Issues
- SIP calling needs baresip on host: `sudo apt install baresip baresip-ffmpeg baresip-gstreamer`
- VoIP.ms new accounts take 1-2 business days for manual verification
- users configure their own VoIP.ms sub-account credentials in the app settings
- caller.py generates temp baresip config per call, cleans up after
- XTTS model download takes 5+ minutes on first launch
- Tests need Google OAuth disabled (`GOOGLE_CLIENT_ID=*** in conftest)
- Login returns 405 if `-L` flag used (redirect changes POST to GET) — don't follow redirects on POST
