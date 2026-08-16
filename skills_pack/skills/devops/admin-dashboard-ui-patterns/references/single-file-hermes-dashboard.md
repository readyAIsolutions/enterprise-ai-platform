# Single-File Zero-Dep AI Dashboard Pattern (Demiurge Creed v3.0)

## What it is
A complete AI chat dashboard in a single Python file using only stdlib. Embeds HTML/CSS/JS inline. Wraps `hermes chat` via subprocess with SSE streaming for live token-by-token output. Zero npm, zero pip, zero build step.

## Architecture
- **Single file** (`orchestrator.py`, ~54KB) = HTTP server + HTML template + JS client + provider fallback chain
- **Backend**: `http.server.HTTPServer` + `BaseHTTPRequestHandler` — no Flask/FastAPI
- **Frontend**: Inline HTML/CSS/JS — no React/Vue, no CDN dependencies (except optional Plotly)
- **Chat engine**: `subprocess.Popen` calling `hermes chat` line-by-line → SSE (Server-Sent Events)
- **Fallback chain**: Iterates through configured providers, tries next on failure/timeout

## SSE Streaming Pattern (hermes subprocess)

```python
def hermes_chat_stream(prompt, provider=None, model=None):
    """Generator: yields SSE events (thinking, token, done, error) from live hermes output"""
    providers = WORKING_PROVIDERS
    if provider:
        providers = [(provider, model)] + [p for p in providers if p[0] != provider]
    for try_prov, try_model in providers:
        cmd = [HERMES_BIN, "chat", "-q", prompt, "--yolo", "--provider", try_prov]
        if try_model:
            cmd.extend(["-m", try_model])
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, bufsize=1)
            in_response = False
            in_thinking = False
            think_buf = []
            resp_buf = []
            for line in proc.stdout:
                line_stripped = line.strip()
                if not line_stripped:
                    continue
                # Detect thinking block start
                if ("Reasoning" in line_stripped or "Thinking" in line_stripped) and "─" in line_stripped:
                    in_thinking = True; continue
                if in_thinking and "─" in line_stripped and len(line_stripped) > 5:
                    in_thinking = False
                    if think_buf:
                        yield {"event": "thinking", "data": "\n".join(think_buf)}
                        think_buf = []
                    continue
                if in_thinking:
                    think_buf.append(line_stripped); continue
                # Detect Hermes response start
                if "Hermes" in line_stripped and ("╭─" in line_stripped or "──" in line_stripped):
                    in_response = True; continue
                if in_response and ("╰─" in line_stripped or "──" in line_stripped):
                    in_response = False; continue
                if in_response and line_stripped:
                    yield {"event": "token", "data": line_stripped}
                    resp_buf.append(line_stripped)
            proc.wait(timeout=10)
            full_resp = " ".join(resp_buf).strip()
            if full_resp:
                yield {"event": "done", "data": json.dumps({"provider": try_prov})}
                return
        except subprocess.TimeoutExpired:
            continue
        except Exception:
            continue
    yield {"event": "error", "data": "All providers failed"}
```

## HTTP SSE Endpoint

```python
elif p == "/chat/stream":
    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
    msg = body.get("message", "")
    provider = body.get("provider")
    self.send_response(200)
    self.send_header("Content-Type", "text/event-stream")
    self.send_header("Cache-Control", "no-cache")
    self.send_header("Connection", "keep-alive")
    self.send_header("Access-Control-Allow-Origin", "*")
    self.end_headers()
    for event in hermes_chat_stream(msg, provider):
        self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
        self.wfile.flush()
```

## Frontend SSE Consumer

```javascript
var r = await fetch('/chat/stream', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({message: msg})
});
var reader = r.body.getReader(), decoder = new TextDecoder(), buffer = '';
while (true) {
    var {value, done} = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, {stream: true});
    var lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (var line of lines) {
        if (!line.startsWith('data:')) continue;
        var data = JSON.parse(line.slice(5).trim());
        if (data.event === 'token') respText += data.data + ' ';
        else if (data.event === 'thinking') thinkText = data.data;
        else if (data.event === 'done') provider = data.data.provider;
    }
    // Update DOM with respText (rendered as markdown)
}
```

## Hermes Output Parsing (robust fallback)

```python
def _parse_hermes_output(output):
    """Extract response + thinking from any hermes output format"""
    # Extract thinking from XML tags or boxed output
    think_matches = re.findall(r'<(?:think|thinking|reasoning)>(.*?)</(?:think|thinking|reasoning)>',
                               output, re.DOTALL | re.IGNORECASE)
    think_text = "\n".join(t.strip() for t in think_matches if t.strip())
    if not think_text:
        m = re.search(r'┌─\s*(?:Reasoning|Thinking).*?┐\n(.*?)\n└', output, re.DOTALL)
        if m: think_text = m.group(1).strip()
    # Extract response between Hermes marker and Session: marker
    lines = output.split("\n")
    in_resp = False
    resp_parts = []
    for line in lines:
        if "Hermes" in line and ("╭─" in line or "──" in line):
            in_resp = True; continue
        if in_resp and ("╰─" in line or "Session:" in line):
            break
        if in_resp and line.strip():
            resp_parts.append(line.strip())
    resp_text = " ".join(resp_parts).strip()
    # Fallback: take everything after the last thinking box
    if not resp_text:
        parts = re.split(r'┌─.*?(?:Reasoning|Thinking).*?┐.*?└.*?┘', output, flags=re.DOTALL)
        if len(parts) > 1:
            after = parts[-1]
            m2 = re.search(r'Hermes.*?\n(.*?)(?:Session:|$)', after, re.DOTALL)
            if m2: resp_text = m2.group(1).strip()
    return resp_text, think_text
```

## Nginx Reverse Proxy for SSE

```
location /chat/stream {
    proxy_pass http://127.0.0.1:9772/chat/stream;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 3600s;
    chunked_transfer_encoding on;
}
```

## Pitfalls
- **SSE buffering**: nginx buffers by default. Must set `proxy_buffering off` or the stream arrives in chunks.
- **Hermes output format varies**: Some models use `╭─ ⚕ Hermes ──`, others use plain `──`. Parse both.
- **`list index out of range`** from hermes: Skip providers that return this; it's a transient model output parsing error in hermes, not a dashboard bug.
- **Subprocess timeout**: hermes chat can take 180s+. Set generous timeout and catch `TimeoutExpired`.
- **No pip deps**: The entire dashboard must work with Python stdlib only. No `flask`, `fastapi`, `aiohttp`.
- **AppImage size**: The AppDir is ~50KB source. AppImage is ~205KB with squashfs. Bundling `hermes` binary adds ~50MB — decide per-use-case.
- **Folder drop counter bug**: When using `webkitGetAsEntry()` + `entry.isDirectory`, the `total` counter included directories, so `allFiles.length === total` never matched for folders containing subdirectories — upload silently never fired. FIX: use `e.dataTransfer.files` directly (modern browsers populate all files with `webkitRelativePath` from dropped folders). See Folder Upload section below.
- **Static settings tab = user rage**: A Settings tab showing hardcoded text ("port: 9772, providers: 28") is worse than no settings tab at all. Every row must pull live data from existing endpoints (`/health`, `/status`, `/ratelimit`). The user will click Settings first to judge whether the app is "masterclass" — empty/stub settings signal "unfinished toy."
- **"Masterclass" bar**: LO expects every tab to do something real on first click. No "coming soon" placeholders. No static lists. No features that only work after configuration. The Files tab must accept uploads immediately. The Chat tab must stream. The Swarm tab must show live health. The Settings tab must show live metrics. If a tab is empty, the user concludes the whole app is broken.

## Folder Upload (drag-drop + webkitdirectory)

The upload area accepts: single files, multiple files, folders (via picker), folders (via drag-drop), and zip files (auto-extracted server-side).

### Frontend: Drag-and-drop (CORRECT pattern)

```javascript
// Use e.dataTransfer.files directly — browsers populate all files from dropped folders
// with webkitRelativePath set correctly. Do NOT use webkitGetAsEntry() — the counter
// bug makes upload silently fail for nested folders.
uploadArea.addEventListener('drop', function(e) {
    e.preventDefault();
    var files = e.dataTransfer.files;  // ← all files, including from subdirectories
    if (!files || !files.length) return;
    var fd = new FormData();
    for (var i = 0; i < files.length; i++) {
        var f = files[i];
        var relPath = f.webkitRelativePath || f.name;  // folder/file.py or just file.py
        fd.append('files', f, relPath);
    }
    fetch('/files/upload', {method: 'POST', body: fd}).then(...);
});
```

### Frontend: Folder picker button

```javascript
function triggerFolderUpload() {
    var inp = document.createElement('input');
    inp.type = 'file';
    inp.webkitdirectory = true;  // ← enables folder selection
    inp.multiple = true;
    inp.onchange = function() { uploadFiles(inp.files); };
    inp.click();
}
```

### Backend: Multipart handler with zip auto-extract

```python
elif p == "/files/upload":
    ctype = self.headers.get("Content-Type", "")
    if "multipart" in ctype:
        data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        boundary = ctype.split("boundary=")[1].strip()
        parts = data.split(f"--{boundary}".encode())
        for part in parts:
            if b"filename=" not in part: continue
            header_end = part.find(b"\r\n\r\n")
            if header_end == -1: continue
            hdr = part[:header_end].decode(errors='ignore')
            fn_match = re.search(r'filename="([^"]*)"', hdr)
            if not fn_match: continue
            fname = os.path.basename(fn_match.group(1))  # strip any path prefix
            content = part[header_end + 4:]
            if content.endswith(b"\r\n"): content = content[:-2]
            # Auto-extract zip files
            if fname.lower().endswith('.zip'):
                import zipfile, io
                zf = zipfile.ZipFile(io.BytesIO(content))
                for zi in zf.namelist():
                    if zi.endswith('/'): continue
                    with open(os.path.join(FILES_DIR, os.path.basename(zi)), 'wb') as zout:
                        zout.write(zf.read(zi))
                continue
            with open(os.path.join(FILES_DIR, fname), 'wb') as f:
                f.write(content)
```

## Code Mode Toggle (chat → code gen)

A toggle button in the chat input bar switches between natural chat and code generation mode. When active, prompts are auto-prefixed and responses are code-block-extracted with syntax highlighting.

```javascript
var codeMode = false;

function toggleCodeMode() {
    codeMode = !codeMode;
    var btn = document.getElementById('code-mode-btn');
    if (codeMode) {
        btn.classList.add('active');
        btn.textContent = '💻 CODE ON';
        document.getElementById('chat-input').placeholder = 'Describe code to generate...';
    } else {
        btn.classList.remove('active');
        btn.textContent = '💻 Code';
    }
}

async function sendChat() {
    var msg = inp.value.trim();
    var sendMsg = msg;
    if (codeMode) {
        // Auto-detect language from "python: description" or first-word match
        var lang = 'python', rest = msg;
        var m = msg.match(/^(\\w+):\\s*(.+)/);
        if (m) { lang = m[1]; rest = m[2]; }
        else {
            var known = ['python','cpp','javascript','bash','html','css','sql','rust','go'];
            var first = msg.split(/\\s+/)[0].toLowerCase();
            if (known.includes(first)) { lang = first; rest = msg.slice(first.length).trim(); }
        }
        sendMsg = 'Write ' + lang + ' code for: ' + rest +
                  '. Output ONLY the code in a ```' + lang + ' block. No explanation.';
    }
    // ... stream as normal ...
    // After streaming: if codeMode, extract just the code block from respText
    if (codeMode) {
        var cb = respText.match(/```(\\w*)\\n([\\s\\S]*?)```/);
        if (cb) {
            var clang = cb[1] || 'python', ccode = cb[2].trim();
            body.innerHTML = '<pre><div class="pre-header">' +
                '<span class="lang-tag">' + clang + '</span>' +
                '<button onclick="copyPre(this)">📋 Copy</button></div>' +
                '<code>' + highlight(ccode, clang) + '</code></pre>';
        }
    }
}
```

## Browser Syntax Highlighting (zero-dep regex)

```javascript
var SYN = {
    python: {
        kw: 'def class import from return if else elif for while try except finally with as yield lambda pass break continue raise and or not in is True False None print async await self'.split(' '),
        builtin: 'len range list dict set tuple str int float bool type print input open enumerate zip map filter sorted reversed min max sum any all abs round isinstance hasattr getattr setattr'.split(' ')
    },
    javascript: {
        kw: 'function const let var return if else for while try catch finally throw new class extends import export default async await break continue switch case typeof instanceof this super null undefined true false'.split(' ')
    },
    cpp: {
        kw: 'int float double char void bool auto const static virtual inline class struct enum namespace template using public private protected return if else for while switch case break continue try catch throw new delete sizeof typedef'.split(' ')
    },
    bash: { kw: 'if then else elif fi for while do done case esac in function return exit export local source'.split(' ') },
    sql: { kw: 'SELECT FROM WHERE JOIN ON GROUP BY HAVING ORDER LIMIT INSERT INTO VALUES UPDATE SET DELETE CREATE TABLE INDEX DROP ALTER AND OR NOT NULL AS DISTINCT COUNT SUM AVG MIN MAX'.split(' ') }
};

function highlight(code, lang) {
    var out = escHtml(code);
    // Comments (per-language style)
    if (lang === 'python' || lang === 'bash') out = out.replace(/(#[^\\n]*)/g, '<span class="syn-cmt">$1</span>');
    else if (lang === 'javascript' || lang === 'cpp' || lang === 'sql') out = out.replace(/(\\/\\/[^\\n]*)/g, '<span class="syn-cmt">$1</span>');
    out = out.replace(/(\\/\\*[\\s\\S]*?\\*\\/)/g, '<span class="syn-cmt">$1</span>');
    // Strings
    out = out.replace(/("(?:[^"\\\\]|\\\\.)*")/g, '<span class="syn-str">$1</span>');
    out = out.replace(/('(?:[^'\\\\]|\\\\.)*')/g, '<span class="syn-str">$1</span>');
    out = out.replace(/(`(?:[^`\\\\]|\\\\.)*`)/g, '<span class="syn-str">$1</span>');
    // Numbers
    out = out.replace(/\\b(\\d+\\.?\\d*)\\b/g, '<span class="syn-num">$1</span>');
    // Keywords + builtins
    var syn = SYN[lang] || SYN['python'];
    if (syn) {
        (syn.kw || []).forEach(function(k) {
            out = out.replace(new RegExp('\\\\b' + k + '\\\\b', 'g'), '<span class="syn-kw">$&</span>');
        });
        (syn.builtin || []).forEach(function(k) {
            out = out.replace(new RegExp('\\\\b' + k + '\\\\b', 'g'), '<span class="syn-builtin">$&</span>');
        });
    }
    // Function calls
    out = out.replace(/\\b([a-zA-Z_]\\w*)(\\s*\\()/g, '<span class="syn-fn">$1</span>$2');
    // Decorators
    out = out.replace(/(@\\w+)/g, '<span class="syn-dec">$1</span>');
    return out;
}

// Language auto-guess from code content
function guessLang(code) {
    var c = code.trim().toLowerCase();
    if (c.startsWith('#include') || c.includes('std::') || c.includes('int main')) return 'cpp';
    if (c.startsWith('def ') || c.startsWith('import ') || c.startsWith('from ')) return 'python';
    if (c.startsWith('function') || c.startsWith('const ') || c.includes('=>')) return 'javascript';
    if (c.startsWith('#!/bin/') || c.startsWith('set -')) return 'bash';
    if (c.startsWith('SELECT') || c.startsWith('CREATE')) return 'sql';
    return '';
}
```

CSS classes for syntax colors:
```css
.syn-kw{color:#ff79c6;font-weight:600}  /* keywords */
.syn-str{color:#f1fa8c}                 /* strings */
.syn-num{color:#bd93f9}                 /* numbers */
.syn-cmt{color:#6272a4;font-style:italic} /* comments */
.syn-fn{color:#50fa7b}                  /* function names */
.syn-builtin{color:#ffb86c}             /* builtins */
.syn-dec{color:#50fa7b}                 /* decorators */
```

## Live Settings Tab (not static)

```javascript
async function refreshSettings() {
    var h = await (await fetch('/health')).json();
    var s = await (await fetch('/status')).json();
    var rl = await (await fetch('/ratelimit')).json();
    var items = [
        {k: 'Version', v: h.version, d: 'App version'},
        {k: 'Uptime', v: formatUptime(h.uptime), d: 'Server uptime'},
        {k: 'Port', v: location.port, d: 'Listening port'},
        {k: 'Providers', v: s.providers_ready + ' / ' + s.total_providers, d: 'Live / configured'},
        {k: 'Chats Today', v: s.chats_today, d: 'This session'},
        {k: 'Tokens Used', v: formatNum(tokensUsed), d: 'Estimated total'},
    ];
    if (rl.available) {
        items.push({k: 'Credits', v: '$' + (rl.credits - rl.credits_used).toFixed(2), d: 'OpenRouter remaining'});
    }
    // ... render into DOM ...
}
```
- **Folder drop counter bug**: When using `webkitGetAsEntry()` + `entry.isDirectory`, the `total` counter included directories, so `allFiles.length === total` never matched for folders containing subdirectories — upload silently never fired. FIX: use `e.dataTransfer.files` directly (modern browsers populate all files with `webkitRelativePath` from dropped folders). See Folder Upload section below.
- **Static settings tab = user rage**: A Settings tab showing hardcoded text ("port: 9772, providers: 28") is worse than no settings tab at all. Every row must pull live data from existing endpoints (`/health`, `/status`, `/ratelimit`). The user will click Settings first to judge whether the app is "masterclass" — empty/stub settings signal "unfinished toy."
- **"Masterclass" bar**: LO expects every tab to do something real on first click. No "coming soon" placeholders. No static lists. No features that only work after configuration. The Files tab must accept uploads immediately. The Chat tab must stream. The Swarm tab must show live health. The Settings tab must show live metrics. If a tab is empty, the user concludes the whole app is broken.