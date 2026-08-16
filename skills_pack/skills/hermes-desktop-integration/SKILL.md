---
name: hermes-desktop-integration
category: devops
description: Build native Linux desktop apps wrapping Hermes HTTP APIs with GTK + WebKit
tags: [gtk, webkit, desktop, linux, hermes, api]
---

# Hermes Desktop Integration

Native Linux desktop apps that wrap Hermes HTTP APIs using GTK + WebKit. No login screens, no tabs, no settings panels - clean chat interface like Claude Desktop.

## When to use

Building desktop frontends for Hermes-based agents or any HTTP API that needs a native wrapper.

## Key patterns

### 1. Server endpoint design

**Public `/free-models` endpoint** - expose free models without auth:
```
GET /free-models
Returns: {free_models: [{model, provider}], count: N, providers: [...]}
```

**Authenticated skill/kb endpoints** - protect via `/hermes` prefix:
```
GET /hermes/skills     - list available skills
GET /hermes/tools      - list toolsets
GET /hermes/kb?q=X     - query knowledge base
```

### 2. GTK + WebKit setup

```python
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gtk, WebKit2

class App(Gtk.Window):
    def __init__(self):
        super().__init__(title="App")
        self.set_default_size(900, 700)
        
        self.webview = WebKit2.WebView()
        settings = self.webview.get_settings()
        settings.set_enable_developer_extras(True)
        settings.set_javascript_can_access_clipboard(True)
        
        # Inject port into HTML at runtime
        html = HTML_TEMPLATE.replace("{PORT}", str(PORT))
        self.webview.load_html(html, f"http://127.0.0.1:{PORT}/")
        self.add(self.webview)
```

### 2a. GTK Drag-and-Drop with External App Support
    
For desktop icon overlays that accept drops from file managers:

```python
TARGET_TYPES = [
    Gtk.TargetEntry.new("text/uri-list", Gtk.TargetFlags.SAME_APP, 100),
    Gtk.TargetEntry.new("text/uri-list", Gtk.TargetFlags.OTHER_APP, 101),
]

class DesktopIcon(Gtk.EventBox):
    def __init__(self, item):
        super().__init__()
        self.item = item
        # Use parent_win not container (container is readonly in Gtk)
        # No set_relief() - EventBox doesn't have it
        
        # External drag source
        self.drag_source_set(Gdk.ModifierType.BUTTON1_MASK, TARGET_TYPES, Gdk.DragAction.COPY)
        self.connect("drag-data-get", self._on_drag_data_get)
        
        # External drop target
        self.drag_dest_set(Gtk.DestDefaults.ALL, TARGET_TYPES, Gdk.DragAction.COPY)
        self.connect("drag-drop", self._on_drag_drop)  # MUST connect this
        self.connect("drag-data-received", self._on_drag_data_received)
    
    def _on_drag_data_get(self, widget, drag_context, data, info, time):
        uris = [f"file://{self.item['path']}"]
        data.set_uris(uris)
    
    def _on_drag_drop(self, widget, drag_context, x, y, time):
        # CRITICAL: Must call drag_get_data to trigger drag-data-received
        widget.drag_get_data(drag_context, TARGET_TYPES[1], time)
        return True
    
    def _on_drag_data_received(self, widget, drag_context, x, y, data, info, time):
        if data and data.get_uris():
            for uri in data.get_uris():
                path = uri.replace("file://", "").replace("%20", " ")
                # Handle dropped file
        drag_context.finish(True, False, time)

# For window-level drops (accepting drops directly on desktop):
def _on_window_drop(self, widget, drag_context, x, y, time):
    widget.drag_get_data(drag_context, TARGET_TYPES[1], time)
    return True

def _on_window_data(self, widget, drag_context, x, y, data, info, time):
    if data and data.get_uris():
        for uri in data.get_uris():
            path = Path(uri.replace("file://", "").replace("%20", " "))
            # Handle dropped file
    drag_context.finish(True, False, time)
```

CSS for drop highlight:
```css
.dnd-highlight {
    background-color: rgba(0, 229, 255, 0.3);
    border: 2px dashed #00e5ff;
    border-radius: 10px;
}
```

### GTK EventBox DND Pitfalls
- **No set_relief**: EventBox doesn't have `set_relief()` - remove this call
- **No clicked signal**: Use `button-press-event` instead of `"clicked"` for mouse clicks on EventBox
- **Attribute name conflicts**: Avoid `self.container` - it conflicts with Gtk's readonly property. Use `self.parent_win` instead  
- **drag_get_data required**: The `drag-drop` handler must call `widget.drag_get_data()` to trigger `drag-data-received` callback

### 3. Clean chat UI styling

- Dark theme with CSS variables
- Header: logo + title + status indicator
- Messages area with fadeIn animations
- Input area with auto-growing textarea
- Thinking indicator with pulse dots

### 4. Bridge pattern for Hermes integrations

```python
# hermes/hermes_bridge.py
def list_skills() -> List[Dict]:
    """Combine local + Hermes skills."""
    skills = []
    for f in (ROOT / "skills").glob("*.md"):
        skills.append({"name": f.stem, "source": "local"})
    if _ensure_hermes():
        for s in list_available_skills():
            skills.append({"name": s, "source": "hermes"})
    return skills

def list_hermes_tools() -> List[Dict]:
    """Return toolsets available in Hermes."""
    return [{"toolset": t, "description": d} for t, d in TOOLSETS.items()]

def query_knowledge_base(q: str) -> List[Dict]:
    """Query Hermes session_search for knowledge base access."""
    return session_search(q, limit=5)
```

### 5. Free models endpoint (live + fallback)

```python
# Live fetch from OpenRouter with static fallback
import urllib.request, json as _json

def get_free_models():
    """Fetch free models from OpenRouter API with fallback."""
    try:
        with urllib.request.urlopen("https://openrouter.ai/api/v1/models", timeout=5) as r:
            data = _json.loads(r.read().decode())
        free = []
        for m in data.get("data", []):
            if float(m.get("pricing", {}).get("prompt", 1)) == 0:
                free.append({"model": m.get("id"), "provider": "openrouter"})
    except:
        free = STATIC_FALLBACK_MODELS  # from ~/.hermes/cache/model_catalog.json
    return {"free_models": free, "count": len(free), "providers": [...]}
```

## Pitfalls

### Rate Limit Handling (from master-debate-fix)
When making HTTP calls to free-tier LLM providers, add early timeout guards:
- Check for empty API keys before making requests
- Reduce TIMEOUT to 8s to fail fast on hung connections  
- Return immediately on 429 rate limit errors instead of retrying

### Multi-Monitor Desktop Icons
See `references/multi-monitor-desktop.md` for the fix to make icons appear on primary monitor only.

- **Auth in desktop apps**: If the desktop app requires login, users hate it. Use public endpoints for unauthenticated access or read credentials from environment.
- **Drag-and-drop external drops**: Without `Gtk.TargetFlags.OTHER_APP`, DND only works within the same app. Always include it for desktop icons that accept drops from file managers.
- **CSS class mismatch**: Using `add_class("dnd-overlay")` when CSS defines `.dnd-highlight` causes no visual feedback. Keep class names in sync.
- **HTML in Python strings**: Use `replace("{PORT}", str(PORT))` instead of f-strings inside raw strings.
- **Server startup race**: Wait for server to be ready before loading UI - poll with socket connect loop.
- **Unused imports**: Always remove unused imports (`threading`, `json` when not needed) immediately - keeps codebase clean.

## Verification

1. Run `python app.py` - should launch GTK window
2. Check `GET http://localhost:8420/free-models` returns models
3. Verify `/hermes/skills` and `/hermes/tools` work after auth
4. Test knowledge base query: `GET /hermes/kb?q=desktop`

## Endpoints to implement (from Demiurge build)

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/free-models` | GET | No | Free models from OpenRouter/Groq/Cerebras/SambaNova/Google |
| `/hermes/skills` | GET | Yes | List all available skills |
| `/hermes/tools` | GET | Yes | List Hermes toolsets |
| `/hermes/kb` | GET | Yes | Query knowledge base |