# Demiurge 3D — backend architecture & DB

## Two backends
- `backend/server.py` — the SPA's live backend (FastAPI). Serves the built UI from
  `STATIC_DIR = frontend/dist` and all `/api/*` the frontend uses. **Extend this file.**
- `backend/demiurge/webapp/` — separate FastAPI app (`main.py`, `routes.py`) with routers:
  spools CRUD, files upload/list, print profiles, printer settings, plus `auth_required`
  (Bearer from `Authorization` header; login via `/api/auth/login`). **Not mounted in
  `server.py`** (auth mismatch). Reuse its `db.py` only.

## server.py live route inventory (as of 2026-07)
- Forge: `/api/forge/understand` (POST `{text|request}`), `/api/forge/build`,
  `/api/forge/parts`, `/api/forge/status`, ...
- Printer: `/api/printer/connect` (POST `{printer_url}` or `{ip}`), `/api/printer/status`
  (GET), `/api/printer/command` (gcode), `/api/printer/ws`, `/api/printer/calibrate`.
- Filaments/files/settings (added this session): `/api/spools` (GET/POST/PUT/DELETE
  `/api/spools/{id}`), `/api/files/upload` (POST multipart `file`), `/api/files` (GET),
  `/api/printer/settings` (GET `?printer_id=` / POST `{printer_id, settings}`),
  `/api/filament-presets` (GET → `list_filament_profiles()`),
  `/api/printer/select` (POST `{printer_id}` → connect that printer).
- Misc: `/api/account` (returns `{printers:[{id,name,url}], ...}`), `/api/queue/*`,
  `/api/store/*`, `/api/chat/*`.

## Database
- Path: `Path.home()/".cali-agent"/"webapp.db"` (`DEFAULT_DB_PATH` in `demiurge/webapp/db.py`).
- Tables: `users`, `printers` (cols incl `moonraker_url`, `name`, `print_settings_json`),
  `spools` (cols incl `filament_type`, `color_hex`, `brand`, `material`, `remaining_m`,
  `total_m`, `cost`, `notes`, `print_settings_json`), `files` (cols incl `original_name`,
  `stored_path`, `file_type`, `print_type`).
- Helpers (`demiurge/webapp/db.py`): `get_conn(db_path=DEFAULT_DB_PATH)`,
  `add_spool(user_id, printer_id, slot_id, filament_type, color_hex, brand, material,
  remaining_m, total_m, cost, notes)`, `list_spools(user_id)`,
  `update_spool(spool_id, user_id, **kwargs)` (only writes cols in `_ALLOWED_SPOOL_COLS` —
  add new cols there), `delete_spool(spool_id, user_id)`,
  `add_file(user_id, original_name, stored_path, file_type)`, `list_files(user_id)`,
  `list_printers()`, `add_printer(...)`.
- Seeded data: `users` id=16 ('test'); `printers` rows for `K2 Plus P1` at
  `http://192.168.1.65:4408`, `K2 Plus P2` at `http://192.168.1.66:4408`
  (live Moonraker also answers on `:7125`).

## Adding a feature (recipe)
1. In `server.py`, add the route(s) using `_default_user_id()` (first users row) + the
   `db.py` helpers above.
2. For any new column, add an `_ensure_*_schema()` that runs
   `ALTER TABLE ... ADD COLUMN ...` inside `try/except sqlite3.OperationalError`
   (ignore "duplicate column").
3. Return JSON; for file upload use `UploadFile = File(...)` from fastapi and save under
   `~/.cali-agent/uploads/`.
4. Build the matching frontend component (see `references/frontend-contract.md`) and wire a
   tab in `App.tsx`.
5. Verify with `npm run build` + `pytest tests/` — do NOT rely on live curl probes
   (user blocks them).

## Filament / settings / files API contract (built this session)
- `GET /api/spools` → `[{id, filament_type, color_hex, brand, material, remaining_m,
  total_m, cost, notes, print_settings_json}]`
- `POST /api/spools` body `{filament_type, color_hex, brand?, material?, remaining_m?,
  total_m?, cost?, notes?, print_settings?}` → `{id, ok}`
- `PUT /api/spools/{id}` same body; `DELETE /api/spools/{id}` → `{ok}`
- `POST /api/files/upload` multipart field `file` (ext in stl,obj,3mf,gcode,g,step,stp,amf,
  png,jpg,jpeg) → `{id, ok, name, file_type}`
- `GET /api/files` → `[{id, original_name, file_type, print_type, created_at}]`
- `GET /api/printer/settings?printer_id=N` → settings object (may be `{}`);
  `POST /api/printer/settings` body `{printer_id, settings}` → `{ok}`
