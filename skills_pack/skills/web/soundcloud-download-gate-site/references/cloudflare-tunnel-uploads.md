# Cloudflare named-tunnel uploads: 502 on big files → dual upload path

Applies to ANY site served behind a `cloudflared` named tunnel (the acpeso.shop
architecture) that lets a browser upload lossless audio from a remote machine.

## The failure
Cloudflare tunnels time out a single large HTTP POST (~100s read timeout). A
100MB+ WAV sent in one request dies with a 502 / connection reset, and the free
tunnel also throttles throughput (~140KB/s observed on this box), so even
"slow but works" is impractical for real lossless files.

## The fix: two-path upload, auto-selected
1. **PATH A — direct-to-R2 (ideal).** The server returns a SigV4 *presigned PUT
   URL* (`r2.presign_put`). The browser PUTs the file **straight to the
   Cloudflare edge / R2** — no tunnel involved, no timeout, no 502, works from
   any machine. Server just records the object key on a `/confirm` endpoint
   (and may also pull a local copy so `/download` keeps working without R2
   calls). Proper endpoints:
   `/admin/upload-r2-presign` + `/admin/upload-r2-confirm`.
2. **PATH B — chunked fallback (works even without R2).** Client slices the
   file into ~4MB parts and sends each as its own fast request (each well under
   the tunnel timeout) via `start/{sid}/{idx}/finish/abort`; the server
   reassembles and saves. This works TODAY through the tunnel from any machine.

**JS handler:** try PATH A first; if the presigned PUT fails, transparently
fall back to PATH B. Progress bar driven by real bytes-sent over the XHR, not a
spinner.

## R2 prerequisite gotcha (capture the enable step, not "R2 broken")
The direct-to-R2 path only works if R2 is **enabled at the Cloudflare ACCOUNT
level** (dashboard → R2 → Get started). Having `account_id` / `bucket` /
`endpoint` / `access_key` / `secret` filled in is NOT enough — if the service
isn't provisioned, the presigned URL points at a dead endpoint and the PUT
fails at SSL handshake. Detect it via the Cloudflare API (it returns "Please
enable R2 through the Cloudflare Dashboard") or by simply trying the PUT and
falling back. Enabling R2 is a **user dashboard action the agent cannot do** —
hand the user the exact click path. Chunked fallback keeps uploads working
until they do.

## What I implemented live (verified end-to-end, 2026-08-02)
`r2.py` gained `presign_put()`, `get_object()`, `delete_object()` (pure-stdlib
SigV4). `server.py` gained the chunk `start/idx/finish/abort` endpoints
(4MB slices) and the R2 presign/confirm endpoints. `app.js` gained `putToUrl`
+ automatic A→B fallback. Verified a 0.6MB file through chunked: start → 4
parts → finish → assembled+saved. R2 harden path complete but R2 itself was
still disabled on the account at the time → browser routes through chunked.

## Reusable design pointers
- Every upload endpoint must finish far under the tunnel timeout so each request
  succeeds; never block the handler on a long file.
- Return only the *key* to the browser, never a server filesystem path.
- Keep R2 disabled/unavailable non-fatal: try local save so nothing dies.
