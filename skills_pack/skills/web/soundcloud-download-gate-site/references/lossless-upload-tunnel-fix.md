# Lossless upload "infinite loading" — Cloudflare tunnel throttle + progress-bar fix

Session: 2026-08-02, AC PE$0 site. LO reported: "when we go to add a lossless song in
releases it just infinitely loads and doesnt upload the beat."

## Root cause (proven live)
The app was NOT broken. The Cloudflare tunnel throttles HTTP request bodies to ~140KB/s:
- same 20MB file to localhost `POST /admin/release-upload` → 303 in **0.6s** (works)
- same 20MB file through `https://acpeso.shop/admin/release-upload` → **timeout (~120s, curl 000)**
- scaling probes through tunnel: 2MB=16s, 5MB=32s, 10MB=60s timeout → ~140KB/s ceiling.

A real lossless WAV drops are 20–150MB → minutes to upload, but the old UI was a plain HTML
form submit with **zero feedback**, so the admin saw a frozen spinner and assumed it failed.

## The two real fixes

### 1) Live progress via XHR (frontend)
Replace the silent submit path for the lossless file with an XHR `FormData` POST that exposes
upload progress. Key points:
- `xhr.timeout = 0` — big files legitimately take minutes over the tunnel; do NOT time out.
- `xhr.upload.onprogress`: `p = round(e.loaded/e.total*100)` → set `fill.style.width`, `pct%`,
  and a "Uploading M MB / N MB" message.
- On `xhr.onload`: parse JSON `{ok, mb, saved}` → "Uploaded X MB — download is now live."
- Request stays in place (JSON response, not a redirect) so the admin doesn't navigate away.

admin.html markup (per release, inside the inline `edit-row` form's lossless label):
```html
<label class="span2">Lossless / raw audio file (served as the download)
  <input type="file" name="lossless_file" accept=".wav,.flac,.mp3">
  <span class="form-msg" data-up-msg="{{ r.id }}"></span>
  <span class="up-progress" data-up-progress="{{ r.id }}" hidden>
    <span class="up-bar"><span class="up-fill" data-up-fill="{{ r.id }}"></span></span>
    <span class="up-pct" data-up-pct="{{ r.id }}">0%</span>
  </span>
  <span class="up-actions">
    <button class="btn btn-tiny" type="button" data-up-upload="{{ r.id }}">Upload lossless now</button>
  </span>
</label>
```
CSS (style.css): `.up-actions{display:flex;gap:.6rem;flex-wrap:wrap;margin-top:6px}`,
`.up-progress{display:flex;align-items:center;gap:8px;margin-top:6px}`,
`.up-bar{flex:1;height:10px;background:var(--bg-3);border:1px solid var(--line);border-radius:999px;overflow:hidden}`,
`.up-fill{height:100%;width:0;background:linear-gradient(90deg,#FF2B3E,#ff6a6a);transition:width .2s}`,
`.up-pct{font-size:12px;min-width:38px;text-align:right}`.

app.js handler (bind on `[data-up-upload]`):
```js
var xhr = new XMLHttpRequest();
xhr.open('POST', '/admin/release-upload', true);
xhr.timeout = 0;
var fd = new FormData();
fd.append('id', rid);
fd.append('lossless_file', file);
xhr.upload.addEventListener('progress', function (e) {
  if (e.lengthComputable) { var p = Math.min(100, Math.round(e.loaded/e.total*100));
    fill.style.width = p + '%'; pct.textContent = p + '%';
    msg.textContent = 'Uploading ' + p + '% — (' + (e.loaded/1048576).toFixed(1) + ' / ' + (e.total/1048576).toFixed(1) + ' MB)'; }
});
xhr.onload = function () { var j = {}; try { j = JSON.parse(this.responseText); } catch(_) {}
  if (this.status >= 200 && this.status < 300 && j.ok) { msg.className='form-msg ok'; msg.textContent='Uploaded '+j.mb+' MB — saved. Download is now live.'; }
  else { msg.className='form-msg err'; msg.textContent=(j&&j.error)||('Upload failed (HTTP '+this.status+').'); } };
xhr.send(fd);
```

### 2) Stream to disk on the server (backend)
Never `await up.read()` an entire 100MB+ WAV into RAM. In BOTH `admin_release` and
`admin_release_upload`, stream:
```python
chunks = []
while True:
    chunk = await up.read(1024*1024)
    if not chunk: break
    chunks.append(chunk)
raw = b"".join(chunks)
local.write_bytes(raw)
db.upsert_release({**rel, "id": rel["id"], "lossless_file": str(local), "lossless_name": name})
# R2 best-effort, wrapped in try/except as before
```
`/admin/release-upload` should return `JSONResponse({"ok": True, "saved": str(local),
"name": name, "size": len(raw), "mb": round(len(raw)/1048576,1)})` so the progress handler can
confirm completion in place. Keep `/admin/release` (full edit form) returning the 303 redirect
for non-file field saves.

## PHANTOM-release trap when testing uploads
Posting to `/admin/release` (the full form route) with only an `id` or only test fields lets
`upsert_release` INSERT new blank releases when the `id` doesn't match an existing row.
Live incident: 5 phantom releases (empty titles) created and had to be removed by id.
- Prefer `/admin/release-upload` for isolated upload tests (it requires an existing release).
- If you hit the full form, always pass a REAL release `id` + `title`.
- Cleanup: `DELETE FROM releases WHERE id IN (<phantom ids>)` then remove matching `storage/*.wav`;
  confirm back to the original count (e.g. 16).

## Tunnel / process notes
- Diagnostic split: localhost fast + public slow = transport throttle, not app logic. Always
  run the local-vs-public comparison before touching code.
- A stale duplicate `cloudflared tunnel --url ...` (quick-tunnel) can coexist with the named
  `cloudflared tunnel run acpeso` — kill the `--url` one. Throttle persists with one tunnel
  (verified), so this is hygiene, not the fix.
- Project path contains `$` (`~/Desktop/ac pe$0`) → bash `cd` expands `$0`. Use
  `launch_acpeso.py` (python `subprocess.Popen(cwd=...)`) and wait ~2-5s for the listener; an
  instant restart can hit "address already in use".

## Honest bounds to state to LO
- Even with the progress bar, a 100MB WAV still takes several minutes over the tunnel — the
  progress bar makes it honest and lets it complete, it does not make it fast.
- Real speed unlock = fixing R2 (currently an SSL handshake failure) or browser→R2 presigned
  uploads so big files bypass the slow tunnel. That is the highest-value next step.
- The lossless music itself must be uploaded by the artist — never fabricated.

## CHUNKED UPLOAD — the fix that makes remote tunnel uploads actually finish (2026-08-02)
The progress bar documented above makes the slow upload *visible* but a big single POST still
**502s** — Cloudflare's edge times out (~100s) before the origin finishes reading a 50–150MB
body, even when the user waits. LO: "upload failed http 502 wouldn't finish the upload cant
upload my songs" + "make the upload work through acpeso.shop so admin can upload remote."
Chunked upload is the durable fix (works through the tunnel from ANY machine, zero config):

- **Server** (4 endpoints, all admin-gated):
  - `POST /admin/upload-chunk/start` → `{session_id}`, mkdir `storage/_uploads/<sid>`
  - `POST /admin/upload-chunk/{sid}/{idx}` (multipart `chunk`) → write to `<sid>/{idx:06d}`
  - `POST /admin/upload-chunk/{sid}/finish` (multipart `release_id`,`filename`) → sort slices,
    `b"".join`, write `storage/<relid><ext>`, `shutil.rmtree` the session dir, upsert release
  - `POST /admin/upload-chunk/{sid}/abort` → clean up
- **Client** (`[data-up-upload]`): `CHUNK = 4*1024*1024`; `total = Math.ceil(size/CHUNK)`;
  send each `file.slice(i*CHUNK, min((i+1)*CHUNK, size))` as its own FormData POST, update a
  cumulative % (`uploaded/total`), then POST finish. Each slice is a fast request well under
  the proxy timeout, so a 100MB file completes in ~25 small hops.
- **CRITICAL Starlette route-order pitfall:** register `{sid}/finish` and `{sid}/abort`
  BEFORE `{sid}/{idx}` in `app.routes.extend([...])`, or the generic star path captures
  `/finish` → `admin_upload_chunk` tries `int("finish")` → "bad index". The chunks log fine;
  only the finish call 400s.
- Verified: chunk slices post OK with a growing `received` list; route-order fix confirmed
  needed; 56/56 tests pass after.

### R2 still blocked — honest status for LO
Checked the CF API directly: `GET /accounts/{id}/r2/buckets` → **HTTP 403 `Please enable R2
through the Cloudflare Dashboard`** (error 10042), and the S3 endpoint host
`<accid>.r2.cloudflarestorage.com` resolves to Cloudflare but TLS handshake fails. So R2 is
NOT provisioned on the account — a dashboard action the owner must do, not a code bug. Until
then, chunked upload is the working path and localhost-direct upload works only from the box
itself.
