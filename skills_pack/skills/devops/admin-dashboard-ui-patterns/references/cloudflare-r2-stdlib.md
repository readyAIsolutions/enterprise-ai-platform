# Cloudflare R2 via Pure Stdlib (AWS SigV4, no boto3)

Working client for AC PE$0 site (`r2.py` at `~/Desktop/ac pe$0/r2.py`). Reuse
the SigV4 core for any S3-compatible object store.

## Credential field order (from a pasted blob)
A pasted R2 "credentials" line is usually the order:
`CF-API-token  <account-id>  <32-hex-access-key-id>  <64-hex-secret-access-key>  <endpoint>`
BUT the account id in the API token line is NOT always the account id used by
the R2 S3 endpoint. The **R2 S3 endpoint subdomain IS the Cloudflare account id**:

```
endpoint = https://1420fa51d039274dcebc4ca81abe4bce.r2.cloudflarestorage.com
account_id = 1420fa51d039274dcebc4ca81abe4bce   # from the subdomain
access_key = 2e540cab9f45967c9a0d00b470813547    # 32 hex chars
secret_key = 4eba67f8...826da868                 # 64 hex chars
```
Wrong assignment → CF API returns `Authentication error` / `Invalid account
identifier`. Correct the GAP by reading the account id out of the endpoint
subdomain, which is guaranteed correct.

## Verify identity before wiring uploads
```python
import json, urllib.request, urllib.error
TOK="<cf token>"; ACC="<account id from endpoint subdomain>"
def api(path):
    req=urllib.request.Request("https://api.cloudflare.com/client/v4"+path)
    req.add_header("Authorization","Bearer "+TOK)
    try:
        with urllib.request.urlopen(req,timeout=20) as r: return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode())
api(f"/accounts/{ACC}")            # -> result.name = owner account, token valid
api(f"/accounts/{ACC}/r2/buckets") # -> success:false code 10042 => R2 NOT enabled yet
```
`10042 "Please enable R2 through the Cloudflare Dashboard."` = the account has
R2 disabled. The USER must click enable in the dashboard; no code/cred change
fixes it. Don't burn turns debugging.

## SigV4 signing core
```python
import hashlib, hmac, urllib.parse
from datetime import datetime, timezone

def _sign(key, msg): return hmac.new(key, msg.encode(), hashlib.sha256).digest()
def _sigkey(secret, ds, region, service):
    k=_sign(("AWS4"+secret).encode(), ds); k=_sign(k, region)
    k=_sign(k, service); return _sign(k, "aws4_request")

def sigv4_headers(method, url, cfg, payload_hash):
    region="auto"; service="s3"
    p=urllib.parse.urlparse(url); host=p.netloc
    now=datetime.now(timezone.utc)
    amz=now.strftime("%Y%m%dT%H%M%SZ"); ds=now.strftime("%Y%m%d")
    path=p.path or "/"; 
    canon_headers={"host":host,"x-amz-content-sha256":payload_hash,"x-amz-date":amz}
    keys=sorted(canon_headers)
    c_headers="".join(f"{k}:{canon_headers[k]}\n" for k in keys)
    signed=";".join(keys)
    creq="\n".join([method, path, p.query, c_headers, signed, payload_hash])
    scope=f"{ds}/{region}/{service}/aws4_request"
    sts="\n".join(["AWS4-HMAC-SHA256", amz, scope,
                   hashlib.sha256(creq.encode()).hexdigest()])
    sig=hmac.new(_sigkey(cfg["secret"],ds,region,service), sts.encode(), hashlib.sha256).hexdigest()
    auth=(f"AWS4-HMAC-SHA256 Credential={cfg['access']}/{scope}, "
          f"SignedHeaders={signed}, Signature={sig}")
    return auth, amz
```

## PUT object / create bucket
```python
# upload
url=f"{endpoint.rstrip('/')}/{bucket}/{quote(key)}"
payload_hash=hashlib.sha256(data).hexdigest()
auth,amz=sigv4_headers("PUT",url,cfg,payload_hash)
req=urllib.request.Request(url,data=data,method="PUT")
req.add_header("Authorization",auth)
req.add_header("x-amz-content-sha256",payload_hash)
req.add_header("x-amz-date",amz)
urllib.request.urlopen(req,timeout=30)

# create bucket = empty-body PUT to /bucket
create_req=urllib.request.Request(f"{endpoint}/{bucket}",method="PUT")
# ...same headers with payload_hash = sha256(b"")
```
Serve lossless files locally FIRST (fast, no round-trip), mirror to R2 best-effort;
in `_serve_release_audio`, stream the local raw file with the ORIGINAL filename.

## Storage layout convention
- `releases/{release_id}{ext}` — lossless raw masters (WAV/FLAC/MP3)
- `beatpacks/{beatpack_id}{ext}` — ZIP kits

Keep a `config_from(settings)` that reads keys `r2_account_id, r2_access_key,
r2_secret_key, r2_bucket, r2_endpoint, r2_public_url` and an `enabled(settings)`
guard so uploads degrade gracefully (local-only) until R2 is configured.
