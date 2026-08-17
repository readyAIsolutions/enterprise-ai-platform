# ENI Desktop — Hermes + Local (side by side)

Native GTK3 + WebKit2 two-pane chat: **Hermes** on the left, **Local** on the
right, in one window.

```
├── app.py         GTK app (two WebKit panes + header bar)
├── bridge.py      local HTTP bridge (serves the chat UI + proxies chat)
├── run.sh         launcher
└── ui/            chat.html / app.js / style.css  (embedded chat frontend)
```

## Run
```bash
bash run.sh                 # needs a graphical session (X11/Wayland + GTK3 + WebKit2)
```
On launch the app auto-starts the bridge (port `ENI_DESKTOP_PORT`, default
8765) if it isn't already running.

## What each pane talks to (OpenAI-compatible /v1/chat/completions)
- **Left = Hermes** — default `http://127.0.0.1:8920/v1` (the free-router /
  Hermes brain). Model picker loads the available list.
- **Right = Local** — auto-detects a local model server (tries 8000, 8080,
  11434/ollama, 8913); override via config in `bridge.py` `DEFAULTS`.

Both panes are fully configurable (base URL + model), so you can point either
side at any OpenAI-compatible backend. Streams if the backend supports SSE,
else falls back to JSON.

## Endpoints on the bridge (port 8765)
```
GET  /chat/left, /chat/right   -> chat UI for that pane
GET  /api/<pane>/models        -> available models for that pane
POST /api/<pane>/chat          -> {messages, model, stream} -> chat/completions
```

## Test the bridge headlessly (no GUI)
```bash
cd enterprise/desktop/eni_chat
ENI_DESKTOP_PORT=8769 python3 bridge.py &        # in one shell
curl -s localhost:8769/chat/left -o /dev/null -w "%{http_code}\n"            # 200
curl -s localhost:8769/api/left/models | head -c 200
curl -s -XPOST localhost:8769/api/left/chat -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"say pong"}],"stream":false}'
```
