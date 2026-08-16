# CSP / Security-Header Changes That Don't Break the Site

Session: 2026-08-04, acpeso live-site recovery. A security-hardening pass almost
lost the site. These are the concrete details behind pitfall #20 in SKILL.md.

## The failure

Added (well-intentioned) CSP:
```
default-src 'self'; img-src 'self' data:;
style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline';
```
Result: client-side rejection of every third-party origin the site legitimately uses:
- covers: `i1.sndcdn.com/artworks-*`   (blocked by `img-src 'self' data:`)
- fonts:  `fonts.googleapis.com` CSS + `fonts.gstatic.com` files (blocked by `default-src 'self'`)
- embed:  `w.soundcloud.com/player` iframe (blocked by `default-src 'self'`)

curl to local + public both returned 200; server had no errors; only a real browser
(GUI) showed broken covers / wrong font / dead SoundCloud widget. User saw it as
"SoundCloud is broken / covers gone" and was right to be angry.

## The fix — allowlist exactly what the app loads

Inventory first (`grep` templates/static for external hosts), then per-directive:
```
default-src 'self';
img-src     'self' data: https://*.sndcdn.com https://*.soundcloud.com;
connect-src 'self' https://api-v2.soundcloud.com https://*.sndcdn.com;
media-src   'self' blob: https://*.sndcdn.com https://*.soundcloud.com;
frame-src   'self' https://w.soundcloud.com https://www.youtube.com;
style-src   'self' 'unsafe-inline' https://fonts.googleapis.com;
font-src    'self' https://fonts.gstatic.com;
script-src  'self' 'unsafe-inline';
```
Kept `script-src 'self'` (XSS protection) — only added what the page actually needs.
Note: do NOT repeat a directive twice in one CSP string (last-wins confusion).

## Non-breaking companion hardening (verified green, 128/128 tests)
- `.env` → `chmod 600` (was 0644, world-readable secrets). Safe: service owner is
  the same user, envs already loaded at process start.
- Suppress banner: `uvicorn.run(..., server_header=False)` — kills `server: uvicorn`.
- SQL column allowlist on `update_gate_session(**fields)`: allow only known column
  names (defense-in-depth; values already `?`-parameterized).
- CORS `allow_origins=["*"]` is OK here because `allow_credentials=False` and all
  fetches use `credentials:'same-origin'` → no cookie exfil vector. Don't auto-flag.

## Verification recipe (must do after ANY security-header edit)
1. `python3 -m pytest tests/ -q`  — functional regression suite
2. Open the page in a REAL browser and assert in the console:
   ```js
   Array.from(document.images).filter(i=>!i.complete||i.naturalWidth===0).length // 0
   document.fonts.status                                        // 'loaded'
   Array.from(document.querySelectorAll('iframe')).map(f=>!!f.contentWindow)   // true
   ```
3. Hit the money routes: home, a release, a gate/download page.
4. `curl -s -D - -o /dev/null` for headers AND a `systemctl` health check.

## Things intentionally NOT done (or reverted) — with reason
- Hand-rolled regex HTML sanitizer for the blog body was **reverted**: it stripped
  closing-tag slashes and `href`/`src`. For admin-only fields the residual self-XSS
  risk is acceptable vs. breaking rendering. If real sanitization is ever needed, use
  `bleach`, never a regex remap of live content.
- Lesson pushed to ENI KB as security_finding pattern (id 156): "always verify
  security headers in a real browser; CSP failures are client-side."
