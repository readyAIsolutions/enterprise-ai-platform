#!/usr/bin/env python3
# ENI cookbook auth gate — serve cookbook_site/ ONLY when the correct passphrase
# is supplied (?k=PASS or X-Key header). Denies everything else with 403.
# Run: ENI_CB_PASS=sonny-and-cher-forever python3 cookbook_auth.py  (listens :8899)
import http.server, socketserver, os, hashlib, urllib.parse

ROOT = os.environ.get("ENI_CB_ROOT", "/home/hunter/Desktop/cookbook_site")
PORT = int(os.environ.get("ENI_CB_PORT", "8899"))
PASS = os.environ.get("ENI_CB_PASS", "sonny-and-cher-forever")

def ok(key):
    return key is not None and hashlib.sha256(key.encode()).hexdigest() == hashlib.sha256(PASS.encode()).hexdigest()

class H(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        q = urllib.parse.urlparse(self.path).query
        kv = urllib.parse.parse_qs(q).get("k", [])
        hdr = self.headers.get("X-Key")
        if ok(kv[0] if kv else None) or ok(hdr):
            super().do_GET()
        else:
            self.send_response(403)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"nope.")
    def log_message(self, *a):
        pass

class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

if __name__ == "__main__":
    os.chdir(ROOT)
    httpd = S(("127.0.0.1", PORT), H)
    print("[cookbook_auth] locked on 127.0.0.1:%d — passphrase required" % PORT)
    httpd.serve_forever()
