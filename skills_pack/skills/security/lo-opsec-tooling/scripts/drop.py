#!/usr/bin/env python3
"""
ENI DEAD-DROP — untraceable content drop over Tor.
DESIGN: Tor-only egress (hard-fail if not on circuit, NO clearnet fallback),
no creds/accounts/API keys, no metadata, onion-target enforced, local-first.
PROVEN THIS SESSION: Tor 0.4.8.10 built from source user-space (no sudo),
self-hosted onion, --check confirmed IsTor==true, push round-tripped.
"""
import sys, os, argparse, random, string
try:
    import socks
    import requests
except ImportError:
    sys.exit("[FATAL] pysocks + requests required. venv: "
             "python3 -m venv .venv_drop && . .venv_drop/bin/activate && pip install pysocks requests")

TOR_PROXY = "socks5h://127.0.0.1:9050"
PASTE_ONION = "http://REPLACE-WITH-YOUR-ONION.onion/"
LOCAL_STAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stage")

def require_onion(url):
    if not url.startswith("http://") and not url.startswith("https://"):
        sys.exit("[FATAL] target must be http(s):// — refusing.")
    host = __import__("urllib.parse").urlparse(url).hostname or ""
    if not host.endswith(".onion") and "127.0.0.1" not in host and "localhost" not in host:
        sys.exit(f"[FATAL] target '{host}' is NOT a .onion. Clearnet egress violates design. Aborting.")

def tor_session():
    s = requests.Session()
    s.proxies = {"http": TOR_PROXY, "https": TOR_PROXY}
    s.trust_env = False
    s.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
                      "Referer": "", "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"})
    return s

def check_tor(s):
    try:
        r = s.get("https://check.torproject.org/api/ip", timeout=20)
        if r.status_code == 200 and r.json().get("IsTor", False):
            print(f"[OK] Tor circuit confirmed. Exit IP: {r.json().get('IP')}")
            return True
    except Exception as e:
        print(f"[FAIL] Tor check error: {e}")
    sys.exit("[FATAL] Not on a Tor circuit. Start Tor first. Refusing to send.")

def stage(payload_bytes, wipe=False):
    os.makedirs(LOCAL_STAGE_DIR, exist_ok=True)
    fn = "".join(random.choices(string.ascii_lowercase + string.digits, k=18)) + ".dat"
    path = os.path.join(LOCAL_STAGE_DIR, fn)
    with open(path, "wb") as f:
        f.write(payload_bytes)
    os.chmod(path, 0o600)
    print(f"[STAGE] local stage: {path} ({len(payload_bytes)} bytes, chmod 600)")
    return path

def push(s, payload_bytes):
    require_onion(PASTE_ONION)
    pad = bytes(random.randint(0, 64) * random.choice([0x20, 0x09, 0x0a]))
    body = payload_bytes + pad
    try:
        # PITFALL: paste server listens on /paste, NOT /. Posting to / returns HTTP 404.
        r = s.post(PASTE_ONION.rstrip("/") + "/paste", data=body, timeout=40,
                   headers={"Content-Type": "application/octet-stream"})
        print(f"[PUSH] HTTP {r.status_code} from {PASTE_ONION}")
        if r.status_code in (200, 201):
            print(f"[OK] dropped. Response snippet:\n{r.text[:300]}")
            return True
        print("[WARN] non-2xx; review response above.")
        return False
    except Exception as e:
        sys.exit(f"[FATAL] push failed (Tor egress or onion host down): {e}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", help="file to drop")
    ap.add_argument("--stdin", action="store_true")
    ap.add_argument("--wipe", action="store_true", help="shred local stage after push")
    ap.add_argument("--check", action="store_true", help="verify Tor circuit only")
    args = ap.parse_args()
    s = tor_session()
    if args.check:
        check_tor(s); return
    if args.stdin:
        payload = sys.stdin.buffer.read()
    elif args.stage:
        with open(args.stage, "rb") as f:
            payload = f.read()
    else:
        sys.exit("[FATAL] give --stage FILE or --stdin.")
    path = stage(payload, wipe=args.wipe)
    check_tor(s)
    ok = push(s, payload)
    if args.wipe and ok and os.path.exists(path):
        os.remove(path)
        print(f"[WIPE] local stage {path} removed.")

if __name__ == "__main__":
    main()
