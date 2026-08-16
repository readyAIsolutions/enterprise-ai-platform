# File-Aware Chat + Auto-Project Pattern (Demiurge Creed v4.0)

## Problem
User uploads files/folders but the chat doesn't know about them. User has to manually describe what files exist. When working on a folder of code, there's no project context linking files to the conversation.

## Solution: File Sidebar + Context Chips + Auto-Project

Three interconnected features:
1. **File sidebar** — left panel in chat showing all uploaded files. Click to select as context.
2. **Context chips** — selected files appear as green chips above the chat input. Content auto-attached to prompt.
3. **Auto-project** — when a folder is uploaded (paths contain `/`), a project is auto-created.

## File Sidebar CSS

```css
.chat-sidebar{width:220px;background:var(--panel);border-right:1px solid var(--border);overflow-y:auto;padding:10px;flex-shrink:0}
.chat-sidebar .file-chip{background:var(--card);border:1px solid var(--border);padding:5px 8px;border-radius:4px;margin-bottom:3px;cursor:pointer;font-size:10px}
.chat-sidebar .file-chip:hover{border-color:var(--green)}
.chat-sidebar .file-chip.selected{background:#0d2d1a;border-color:var(--green);color:var(--green)}
```

## File Sidebar HTML

```html
<div class="chat-layout">
  <div class="chat-sidebar" id="chat-sidebar">
    <h3>📁 Working Files</h3>
    <div id="sidebar-files"><!-- populated by JS --></div>
    <button onclick="refreshSidebar()">🔄 Refresh</button>
  </div>
  <div class="chat-main">
    <div class="chat-messages" id="chat-msgs">...</div>
    <div class="file-ctx" id="file-ctx"></div>  <!-- context chips -->
    <div class="chat-input">...</div>
  </div>
</div>
```

## JS: File selection + context chips

```javascript
var selectedFiles = [], activeProject = '';

async function refreshSidebar() {
    var d = await (await fetch('/files/list')).json();
    var fl = '';
    d.files.forEach(function(f) {
        if (f.type === 'dir') {
            fl += '<div class="file-chip" onclick="openProjectChat(\'' + f.name + '\')">📦 ' + f.name + '</div>';
        } else {
            var isSel = selectedFiles.indexOf(f.name) >= 0;
            fl += '<div class="file-chip' + (isSel ? ' selected' : '') + '" onclick="toggleFileCtx(\'' + f.name + '\')">📄 ' + f.name + '</div>';
        }
    });
    document.getElementById('sidebar-files').innerHTML = fl;
}

function toggleFileCtx(fname) {
    var idx = selectedFiles.indexOf(fname);
    if (idx >= 0) selectedFiles.splice(idx, 1);
    else selectedFiles.push(fname);
    renderFileCtx();
    refreshSidebar();
}

function renderFileCtx() {
    var el = document.getElementById('file-ctx');
    if (!selectedFiles.length) { el.innerHTML = ''; return; }
    el.innerHTML = selectedFiles.map(function(f) {
        return '<span class="ctx-chip">📄 ' + f + ' <span class="rm" onclick="toggleFileCtx(\'' + f + '\')">✕</span></span>';
    }).join('');
}
```

## JS: Auto-attach file content to prompt

When sending a chat message with selected files, fetch each file's content and append to the prompt:

```javascript
async function sendChat() {
    var msg = inp.value.trim();
    var sendMsg = msg;

    // Project context
    if (activeProject) sendMsg = '[Working in project: ' + activeProject + ']\n' + sendMsg;

    // Attach file contents
    if (selectedFiles.length) {
        sendMsg += '\n\n--- Attached Files ---';
        for (var f of selectedFiles) {
            var fr = await fetch('/file_content/' + encodeURIComponent(f));
            var fd = await fr.json();
            if (fd.content) sendMsg += '\n\n### File: ' + f + '\n```\n' + fd.content + '\n```';
        }
    }
    // ... continue with streaming ...
}
```

## Python: /file_content endpoint

```python
elif p.startswith("/file_content/"):
    rel = p.split("/file_content/", 1)[1]
    fp = os.path.join(FILES_DIR, os.path.normpath(rel))
    if not fp.startswith(FILES_DIR):
        self._json({"error": "invalid path"}, 403); return
    if os.path.isfile(fp):
        try:
            with open(fp, 'r', errors='ignore') as f: content = f.read(50000)
        except:
            with open(fp, 'rb') as f: content = f.read(50000).decode(errors='ignore')
        self._json({"name": os.path.basename(fp), "content": content, "size": os.path.getsize(fp)})
    else:
        self._json({"error": "not found"}, 404)
```

## Auto-Project on Folder Upload

When a multipart upload filename contains `/`, the top-level directory becomes a project:

```python
if '/' in raw_name:
    fname = raw_name  # preserve path: "myproject/src/main.py"
    # Auto-create project from top-level folder name
    proj_name = fname.split('/')[0]
    proj_dir = os.path.join(PROJECTS_DIR, proj_name)
    if not os.path.exists(proj_dir):
        os.makedirs(proj_dir, exist_ok=True)
        uploaded.append(f"📦 Created project: {proj_name}")
else:
    fname = os.path.basename(raw_name)  # single file
```

## Project Chat Context

Clicking a folder in the sidebar opens it as the active project:

```javascript
function openProjectChat(pname) {
    activeProject = pname;
    selectedFiles = [];
    switchTab('files');
    refreshFiles('projects/' + pname);
    // Show project badge in chat
    document.getElementById('file-ctx').innerHTML =
        '<span class="proj-badge">📦 Project: ' + pname + '</span>' +
        '<span class="ctx-chip" onclick="activeProject=\'\';clearCtx()">✕ close</span>';
}
```

## Pitfalls
- **Content size**: Files up to 50KB are read server-side. Larger files would blow up the prompt context. Cap at a reasonable limit.
- **Binary files**: The `/file_content` endpoint tries text mode first, falls back to binary decode. Non-text files will produce garbage in the prompt — the user should only select text/code files.
- **Encoding**: Uses `errors='ignore'` which silently drops undecodable bytes. For code files, this is fine; for other content, the model gets partial data.
- **Prompt overflow**: Too many selected files can exceed the model's context window. Consider adding a character count warning or auto-trimming.
