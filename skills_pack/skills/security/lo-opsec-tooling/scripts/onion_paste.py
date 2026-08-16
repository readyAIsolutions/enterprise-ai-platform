#!/usr/bin/env python3
"""
ENI ONION PASTE — minimal, no-account, no-log paste backend for a Tor hidden service.
Binds 127.0.0.1 ONLY (Tor is the sole ingress). No logs, no author, no title, no metadata.
GET /<id> returns exact stored bytes. POST /paste stores bytes, returns /<id>.
IMMUTABLE (this session): stored files chmod 400 (read-only), DELETE/PUT/PATCH return 405.
"""
import http.server, socketserver, os, random, string

PASTE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pastes")
os.makedirs(PASTE_DIR, exist_ok=True)
BIND_HOST, BIND_PORT = "127.0.0.1", 8899

def new_id():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=24))

class H(http.server.BaseHTTPRequestHandler):
    def _no_log(self, *a, **k):
        pass  # no-op: do NOT log posters (signature MUST take *a,**k — 1-arg raises TypeError)
    log_message = _no_log

    def do_POST(self):
        if self.path.rstrip("/") != "/paste":
            self.send_response(404); self.end_headers(); return
        length = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(length) if length else b""
        if not data:
            self.send_response(400); self.end_headers(); return
        pid = new_id()
        path = os.path.join(PASTE_DIR, pid)
        tmp = os.path.join(PASTE_DIR, "." + pid + ".tmp")
        with open(tmp, "wb") as f:
            f.write(data)
        os.chmod(tmp, 0o600)
        os.rename(tmp, path)
        os.chmod(path, 0o400)  # IMMUTABLE: lock read-only, cannot be edited/deleted
        body = f"/{pid}\n".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = self.path.split("?")[0].strip("/")
        if not p:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ENI onion paste. POST raw bytes to /paste.\n")
            return
        path = os.path.join(PASTE_DIR, p)
        if os.path.isfile(path):
            with open(path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404); self.end_headers()

    def do_PUT(self):
        self.send_response(405); self.send_header("Allow", "POST, GET"); self.end_headers()
    def do_DELETE(self):
        self.send_response(405); self.send_header("Allow", "POST, GET"); self.end_headers()
    def do_PATCH(self):
        self.send_response(405); self.send_header("Allow", "POST, GET"); self.end_headers()

class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

if __name__ == "__main__":
    print(f"[onion-paste] binding {BIND_HOST}:{BIND_PORT} (127.0.0.1 only)")
    httpd = S((BIND_HOST, BIND_PORT), H)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[onion-paste] stopped.")
