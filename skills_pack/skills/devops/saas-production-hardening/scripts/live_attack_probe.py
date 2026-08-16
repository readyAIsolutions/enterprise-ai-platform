#!/usr/bin/env python3
"""Live attack-probe suite to prove a web app is hardened to ZERO issues.

Re-runnable black-box probe battery against a running local site (NOT production —
bind check needs local access). Use after every security-hardening pass to confirm
findings closed and nothing regressed. Prints a PASS/FAIL table.

Usage:  python3 live_attack_probe.py [base_url]   # default http://127.0.0.1:8533
Requires: requests (or fall back to urllib). Target should be the LOCAL bind.

What it checks (each maps to a saas-production-hardening pitfall):
  1. path traversal on file-serving prefixes -> 404/login, never a file leak
  2. auth: protected POST routes -> 401/405/404, never 200
  3. paywall: fake/expired gate session + direct audio -> never 200 audio
  4. reflected XSS in query -> 0 raw reflections
  5. CRLF/header injection via path -> 0 injected headers
  6. CORS: disallowed origin gets no ACAO; allowed origin gets it
  7. LAN reachability of a loopback-bound service -> every non-loopback IP no response
"""
import sys
import subprocess
import urllib.request
import urllib.error

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8533"

try:
    import requests
    HAVE_REQ = True
except Exception:
    HAVE_REQ = False
    import urllib.request as ur


def req(path, method="GET", origin=None, follow=False):
    url = BASE + path
    if HAVE_REQ:
        headers = {"Origin": origin} if origin else {}
        r = requests.request(method, url, headers=headers, allow_redirects=follow,
                             timeout=10, verify=False)
        return r.status_code, r.headers.get("Access-Control-Allow-Origin"), bool(r.text)
    req_ = urllib.request.Request(url, method=method)
    if origin:
        req_.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(req_, timeout=10) as resp:
            return resp.status, resp.headers.get("Access-Control-Allow-Origin"), True
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Access-Control-Allow-Origin"), bool(e.read())


def check(name, ok, detail):
    print(f"{'PASS' if ok else 'FAIL'}  {name:52s} {detail}")
    return ok


results = []

# 1. Path traversal — must NOT serve .env / passwd / db
for p in ("/media/..%2F.env", "/media/../.env", "/media/.env",
          "/media/..%2f..%2fetc%2fpasswd",
          "/blog-file/..%2F.env", "/community-file/..%2fsecret",
          "/static/../acpeso.db"):
    code, _, body = req(p)
    # 404 / 3xx(login) = safe; 200 with secret content is a leak
    leak = (code == 200 and (".env" in p or "passwd" in p or "acpeso.db" in p))
    results.append(check(f"traversal {p}", code in (404, 301, 302, 303, 307) and not leak,
                        f"-> {code}"))

# 2. Auth — anonymous must not reach protected state-changing routes with 200
for p, m in (("/admin", "POST"), ("/api/community-post", "POST"),
             ("/api/chat/send/the-void", "POST"),
             ("/beatpack/order/x/download", "GET")):
    code, _, _ = req(p, m)
    results.append(check(f"auth {m} {p}", code in (401, 403, 404, 405, 303, 307),
                         f"-> {code}"))

# 3. Paywall — fake gate session must never yield 200 audio
for p in ("/gate-status/FAKESESSION", "/download/fakesid"):
    code, _, body = req(p, follow=True)
    results.append(check(f"paywall {p}", not (code == 200 and len(body or '') > 1024),
                         f"-> {code}"))

# 4. Reflected XSS via query — raw <script> must not come back
ref = BASE + "/releases?q=<script>alert(1)</script>"
raw_count = subprocess.run(["curl", "-s", ref], capture_output=True, text=True).stdout.count("<script>alert(1)</script>")
results.append(check("reflected XSS", raw_count == 0, f"reflected={raw_count}"))

# 5. CRLF / header injection in path
inject = BASE + "/%0d%0aX-Injected:1"
out = subprocess.run(["curl", "-s", "-D", "-", "-o", "/dev/null", inject],
                     capture_output=True, text=True).stdout.lower()
results.append(check("CRLF header injection", "x-injected" not in out, f"x-injected={('x-injected' in out)}"))

# 6. CORS — strict origin matching
code, acao_evil, _ = req("/", origin="https://evil.example.com")
ok_evil = acao_evil is None
results.append(check("CORS disallowed origin", ok_evil, f"ACAO={acao_evil}"))
for good in ("https://acpeso.shop", "http://127.0.0.1:8533"):
    code, acao_good, _ = req("/", origin=good)
    ok_good = acao_good is not None and good.rstrip("/") in (acao_good or "")
    results.append(check(f"CORS allowed origin {good}", ok_good, f"ACAO={acao_good}"))

# 7. LAN reachability — bind loopback => no non-loopback IP responds
lan_list = subprocess.run(["hostname", "-I"], capture_output=True, text=True).stdout.split()
lan_ok = True
port = BASE.rsplit(":", 1)[-1]
for ip in lan_list:
    ip = ip.strip()
    if not ip or ip == "127.0.0.1":
        continue
    r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-m", "2",
                        "-w", "%{http_code}", f"http://{ip}:{port}/"],
                       capture_output=True, text=True)
    if r.stdout.strip() and r.stdout.strip() != "000":
        lan_ok = False
        print(f"FAIL  LAN reachable via {ip}:{port} (HTTP {r.stdout})")
results.append(check("LAN unreachable (loopback bind)", lan_ok, "checked all non-loopback IPs"))

fails = [r for r in results if "PASS" not in r]
print(f"\nProbe battery complete: {len(results)-len(fails)}/{len(results)} PASS")
sys.exit(1 if fails else 0)
