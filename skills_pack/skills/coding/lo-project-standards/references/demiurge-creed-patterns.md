# Demiurge Creed Architecture Patterns

## Single-File Python Web App (stdlib only)

Pattern for building zero-dependency web dashboards:

```python
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json, os, subprocess, re, shutil, time, logging

class App(BaseHTTPRequestHandler):
    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/": self._html()
        elif p == "/api": self._json({"data": ...})
    
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        # handle POST
    
    def _html(self):
        b = HTML.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

if __name__ == "__main__":
    HTTPServer(("0.0.0.0", PORT), App).serve_forever()
```

## Multipart File Upload (stdlib only)

Reliable multipart parsing without external libraries:

```python
def parse_multipart(data, boundary):
    """Parse multipart/form-data, return list of (filename, content) tuples."""
    parts = data.split(f"--{boundary}".encode())
    results = []
    for part in parts:
        if b"filename=" not in part: continue
        header_end = part.find(b"\r\n\r\n")
        if header_end == -1: continue
        hdr = part[:header_end].decode(errors='ignore')
        fn_match = re.search(r'filename="([^"]*)"', hdr)
        if not fn_match: continue
        raw_name = fn_match.group(1)
        content = part[header_end+4:]
        if content.endswith(b"\r\n"): content = content[:-2]
        if not content: continue
        results.append((raw_name, content))
    return results
```

Key pitfalls:
- `os.path.basename()` strips directory paths — use `raw_name` directly for folder uploads
- Folder uploads from `webkitdirectory` send paths like `"folder/sub/file.py"` 
- Zip uploads should auto-extract preserving directory structure
- Empty content should be skipped (`if not content: continue`)

## Folder Upload Preserving Structure

```python
if '/' in raw_name:
    fname = raw_name  # preserve "myproject/src/main.py"
else:
    fname = os.path.basename(raw_name)  # just "file.py"

fpath = os.path.join(FILES_DIR, fname)
os.makedirs(os.path.dirname(fpath), exist_ok=True)
```

## Browser-Side Drag-and-Drop

Use `e.dataTransfer.files` directly — browsers populate this with all files
from dropped folders including `webkitRelativePath`:

```javascript
uploadArea.addEventListener('drop', function(e) {
    e.preventDefault();
    var files = e.dataTransfer.files;
    var fd = new FormData();
    for (var i = 0; i < files.length; i++) {
        fd.append('files', files[i], files[i].webkitRelativePath || files[i].name);
    }
    fetch('/files/upload', {method: 'POST', body: fd});
});
```

Do NOT use `webkitGetAsEntry()` with manual directory traversal —
the counter logic is fragile (directories counted as entries but not files).

## SSE Streaming from Subprocess

```python
def stream_chat(prompt):
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                            text=True, bufsize=1)
    for line in proc.stdout:
        yield {"event": "token", "data": line.strip()}
    proc.wait()
    yield {"event": "done", "data": json.dumps({"provider": name})}
```

HTTP response:
```python
self.send_response(200)
self.send_header("Content-Type", "text/event-stream")
self.send_header("Cache-Control", "no-cache")
self.send_header("Connection", "keep-alive")
self.end_headers()
for event in stream_chat(msg):
    self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
    self.wfile.flush()
```

## Swarm Dispatch via Control FIFOs

Write tasks to ENI builder control FIFOs:
```python
def dispatch_task(description):
    builders = scan_eni_builders()  # read from /tmp/eni_opt_logs/
    idle = [b for b in builders if b["state"] == "idle"]
    if idle:
        ctl_path = f"/tmp/eni_ctl_{idle[0]['name']}"
        with open(ctl_path, 'w') as ctl:
            ctl.write(f"NEW TASK: {description}\n")
```

Builders read from their FIFO via `eni_agent_term.py` which polls
`/tmp/eni_ctl_<NAME>` and forwards to the hermes REPL PTY.

## Port Management

Never assume `pkill` freed the port. Always:
```bash
fuser -k PORT/tcp 2>/dev/null
sleep 1
```

And clear Python bytecode caches to prevent stale code execution:
```bash
find . -name '__pycache__' -type d -exec rm -rf {} +
PYTHONDONTWRITEBYTECODE=1 python3 app.py
```

## JS Validation in CI-Style Flow

```bash
# Extract JS from HTML
python3 -c "
page = open('page.html').read()
js = page[page.find('<script>')+8:page.find('</script>')]
open('/tmp/check.js','w').write(js)
"
# Validate
node --check /tmp/check.js

# Check div balance
python3 -c "
page = open('page.html').read()
assert page.count('<div') == page.count('</div>'), 'Unbalanced divs!'
print('OK')
"
```
