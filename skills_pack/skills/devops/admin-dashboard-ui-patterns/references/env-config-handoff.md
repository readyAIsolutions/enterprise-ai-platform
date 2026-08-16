# .env as Single Source of Truth + Handoff Packaging

Recipe from the AC PE$0 site (~/Desktop/ac pe$0). Use when LO wants a project
handed to another maker, or wants the site's config driven by one file.

## Why
- The user pastes credentials in chat; the ADMIN panel (DB settings) is the
  authoritative store because that's where they were actually entered.
- Hand-typing secrets into a `.env` risks truncation/mistypes. Generate it from
  the DB instead.
- The app must LOAD the env at boot, not just ship a doc file.

## Pure-stdlib loader (no python-dotenv) — config.py

```python
import os
from pathlib import Path
HERE = Path(__file__).resolve().parent
ENV_PATH = HERE / ".env"

MAPPING = [  # (env var, db setting key, default)
    ("SC_CLIENT_ID", "sc_client_id", ""),
    ("SC_CLIENT_SECRET", "sc_client_secret", ""),
    ("SC_REDIRECT_URI", "sc_redirect_uri", ""),
    ("SITE_URL", "site_url", ""),
    ("ADMIN_SC_USERNAME", "admin_sc_username", "acpeso"),
    ("SMTP_HOST", "smtp_host", ""),
    ("R2_ACCOUNT_ID", "r2_account_id", ""),
    # ... one row per setting
]

def _parse_env(text):
    out = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip(); v = v.strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        if " #" in v:
            v = v.split(" #")[0].strip()
        out[k] = v
    return out

def load_env_file():
    return _parse_env(ENV_PATH.read_text(encoding="utf-8")) if ENV_PATH.exists() else {}

def apply(import_db, force=False):
    file_env = load_env_file()
    merged = dict(os.environ)          # real env wins
    for k, v in file_env.items():
        merged.setdefault(k, v)
    count = 0
    for env_key, db_key, default in MAPPING:
        val = merged.get(env_key)
        if val is None:
            val = default
        if val or force:
            import_db.set_setting(db_key, val)
            count += 1
    return count
```

## Boot order (server.py)

```python
import config
config.apply(db, force=False)   # BEFORE anything reads settings
# bootstrap admin from env
_user = os.environ.get("ADMIN_USER") or config.load_env_file().get("ADMIN_USER") or "admin"
_pass = os.environ.get("ADMIN_PASSWORD") or config.load_env_file().get("ADMIN_PASSWORD") or "acpeso2026"
if not db.get_admin(_user):
    db.create_admin(_user, db.hash_password(_pass))
PORT = int(os.environ.get("ACPE_PORT") or db.get_setting("port", "8533") or 8533)
SITE_URL = os.environ.get("ACPE_SITE_URL") or f"http://localhost:{PORT}"
```

## Generate .env FROM the DB (handoff correctness)

Write a throwaway script that pulls authoritative values from the DB and writes
the file, then re-loads it with `config.load_env_file()` and prints each secret
as `first4...last3 (len N)` to confirm nothing truncated. Persist
`ADMIN_PASSWORD` back into the DB too so it survives restarts.

## Handoff package checklist
- `.env` — real values, generated from DB.
- `.env.example` — redacted template (placeholders), safe to commit/show.
- `README.md` — quick start, env table, gate flow, admin CRM, layout, gotchas.
- `start.sh` — `cd "$(dirname "$0")" && exec python3 server.py`.
- `install-service.sh` — systemd USER unit with `EnvironmentFile=.../.env`,
  `Restart=on-failure`, `loginctl enable-linger $USER` for boot without login.
- `.gitignore` — add `.env` so the real secrets never get committed.

## Verifying your secrets got written (not truncated)
Read the file via a python script (not shell `cat` — paths with `$` expand):
```python
import config
d = config.load_env_file()
for k in ("SC_CLIENT_SECRET", "R2_SECRET_KEY", "CF_API_TOKEN"):
    v = d.get(k, "<MISSING>")
    print(k, "len", len(v), "head/tail", v[:4], v[-3:])
```
Known-good lengths seen: SC client_secret = 32, R2 secret = 64, CF api token = 53.
