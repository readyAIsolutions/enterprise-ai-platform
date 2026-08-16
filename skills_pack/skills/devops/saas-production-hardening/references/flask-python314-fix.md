# Flask + Python 3.14 Compatibility Fix & Static File Serving Pattern

**Session**: 2026-07-25 — Demiurge Marketing OS boot & website fix

---

## Problem: Flask 2.3.2 Incompatible with Python 3.14

### Error
```
AttributeError: module 'pkgutil' has no attribute 'get_loader'
```
Occurred in `flask.scaffold.find_package()` → `pkgutil.get_loader(root_mod_name)`

### Root Cause
Python 3.14 removed `pkgutil.get_loader()` (deprecated since 3.12). Flask 2.3.x still uses it.

### Fix
Upgrade Flask to 3.x:
```bash
pip install --upgrade flask==3.1.3
```

### Updated requirements.txt
```txt
flask==3.1.3
requests==2.31.0
python-dotenv==1.0.0
```

> **Rule**: Always pin Flask >= 3.0 for Python 3.12+ projects. Flask 2.x is EOL for modern Python.

---

## Problem: Website Static Files Not Served

### Symptom
Website at `/` loaded raw HTML without CSS/JS — browser showed "bunch of text" (unstyled).

### Root Cause
`app/serve.py` configured Flask with:
```python
app = Flask(__name__, static_folder='../admin', static_url_path='/admin')
```
This only serves `/admin/*` from the admin folder. The website at `/` loads `../website/index.html` but its `<link rel="stylesheet" href="styles.css">` requests `/styles.css` which 404s.

### Fix: Add explicit static routes for website assets
```python
# Serve website static files (CSS, JS, images)
@app.route('/styles.css')
def website_styles():
    return send_from_directory('../website', 'styles.css')

@app.route('/scripts.js')
def website_scripts():
    return send_from_directory('../website', 'scripts.js')

@app.route('/<path:filename>')
def website_static(filename):
    if filename.endswith(('.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2')):
        return send_from_directory('../website', filename)
    return send_from_directory('../admin', filename)
```

### Pattern: Multi-folder static serving in Flask
| Route | Serves From | URL Prefix |
|-------|-------------|------------|
| `/admin/*` | `../admin` | `/admin` (via `static_url_path`) |
| `/styles.css` | `../website` | explicit route |
| `/scripts.js` | `../website` | explicit route |
| `/*.css|.js|.png...` | `../website` | catch-all fallback |
| `/<other>` | `../admin` | fallback for admin SPA routes |

### Alternative (cleaner for production): Use a reverse proxy
```nginx
# nginx.conf
location /admin/ {
    proxy_pass http://app:8000/admin/;
}
location / {
    proxy_pass http://app:8000/;
    # Or serve static directly:
    # root /app/website;
    # try_files $uri $uri/ /index.html;
}
```

---

## Docker Compose Stack Status

### Services defined in `docker/docker-compose.yml`
| Service | Image | Internal Port | External Port | Health Check |
|---------|-------|---------------|---------------|--------------|
| postgres | postgres:16-alpine | 5432 | — | pg_isready |
| redis | redis:7-alpine | 6379 | — | redis-cli ping |
| fonoster | fonoster/fonoster:latest | 50051, 8080 | — | service_started |
| usesend | usesend/usesend:latest | 3000, 2525 | — | service_started |
| odoo19 | odoo:19.0 | 8069 | — | service_started |
| app | build: .. | 8000, 8200, 9090 | 8000 | curl /health |

### Launch command
```bash
cd /home/hunter/Desktop/Demiurge\ Marketing
docker compose -f docker/docker-compose.yml up -d
```

### Environment file required
Copy `.env.example` → `.env` and fill in:
- `FONOSTER_API_KEY`, `FONOSTER_API_SECRET`, `FONOSTER_ACCESS_KEY_ID`, `FONOSTER_APP_REF`, `FONOSTER_FROM_NUMBER`
- `USESEND_API_KEY`, `USESEND_SMTP_USER`, `USESEND_SMTP_PASS`, `USESEND_WEBHOOK_SECRET`
- `ODOO_API_KEY` (plus POSTGRES_PASSWORD for db)
- `OPENROUTER_API_KEY`, `XAI_API_KEY`
- `DEMIURGE_MKT_ENCRYPTION_KEY`, `DEMIURGE_MKT_JWT_SECRET`

---

## Key Files Modified This Session

| File | Change |
|------|--------|
| `requirements.txt` | `flask==2.3.2` → `flask==3.1.3` |
| `app/serve.py` | Added 3 static file routes for website assets |

---

## Pitfall Checklist for Next Session

- [ ] Docker daemon permissions: user must be in `docker` group or use `sudo`
- [ ] Fonoster gRPC port 50051 needs to be reachable from app container
- [ ] useSend SMTP port 2525 for outbound mail
- [ ] Odoo 19 needs initial setup via web UI at `http://localhost:8069` before API key works
- [ ] `.env` must exist before `docker compose up` (validated in launch.sh)
- [ ] Health endpoints: `/health` on app, `/metrics` on :9090

---

*Added to saas-production-hardening skill references — 2026-07-25*