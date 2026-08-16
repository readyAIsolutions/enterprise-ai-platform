# Dashboard Proxy & WebSocket Bridge

## Architecture

```
┌─────────────────┐      WebSocket       ┌──────────────────┐
│  Browser (JS)   │ ◀──────────────────▶ │  Dashboard WS    │
│  :8766          │   dashboard_update   │  Server :8766    │
└─────────────────┘                      └────────┬─────────┘
                                                   │
                              HTTP API Proxy       │
                                                   ▼
                                    ┌──────────────────────┐
                                    │  Creed Server :8765  │
                                    │  (Main Coordination) │
                                    └──────────────────────┘
```

## Server-Side WebSocket Subscription

```python
async def connect_to_server(self):
    while True:
        try:
            self.server_session = aiohttp.ClientSession()
            self.server_ws = await self.server_session.ws_connect(
                SERVER_WS_URL, heartbeat=30
            )
            self.connected = True
            
            # Subscribe to dashboard updates
            await self.server_ws.send_bytes(encode({
                "type": MessageType.DASHBOARD_SUBSCRIBE
            }))
            
            async for msg in self.server_ws:
                if msg.type == WSMsgType.BINARY:
                    await self._handle_server_msg(msg.data)
                elif msg.type == WSMsgType.TEXT:
                    await self._handle_server_msg(msg.data.encode())
        except Exception as e:
            log.warning(f"Dashboard server connection error: {e}")
        finally:
            self.connected = False
            if self.server_ws:
                await self.server_ws.close()
            if self.server_session:
                await self.server_session.close()
            await asyncio.sleep(5)
```

## State Merge & Broadcast

```python
def _merge_state(self, payload: dict):
    if "clients" in payload:
        self.state["clients"] = payload["clients"]
    if "active_tasks" in payload:
        self.state["tasks"]["active"] = payload["active_tasks"]
    if "queued_tasks" in payload:
        self.state["tasks"]["queued"] = payload["queued_tasks"]
    if "completed_tasks" in payload:
        existing = {t["task_id"] for t in self.state["tasks"]["done"]}
        for t in payload["completed_tasks"]:
            if t["task_id"] not in existing:
                self.state["tasks"]["done"].append(t)
        if len(self.state["tasks"]["done"]) > 100:
            self.state["tasks"]["done"] = self.state["tasks"]["done"][-100:]

async def _broadcast_to_dashboards(self, payload: dict):
    msg = encode({"type": "dashboard_update", "payload": payload})
    dead = []
    for ws in self.dashboard_ws_clients:
        try:
            await ws.send_bytes(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        self.dashboard_ws_clients.discard(ws)
```

## HTTP API Proxy (CORS-enabled)

```python
async def proxy_api(self, request):
    path = request.match_info.get("path", "")
    url = f"http://localhost:8765/api/{path}"
    
    method = request.method
    headers = dict(request.headers)
    headers.pop("host", None)
    
    body = None
    if method in ("POST", "PUT", "PATCH"):
        body = await request.read()
    
    # Ensure session exists
    if not self.server_session or self.server_session.closed:
        self.server_session = aiohttp.ClientSession()
    
    try:
        async with self.server_session.request(
            method, url, headers=headers, data=body
        ) as resp:
            data = await resp.read()
            return web.Response(
                body=data, 
                status=resp.status, 
                headers=resp.headers
            )
    except Exception as e:
        return web.json_response({"error": f"Proxy error: {e}"}, status=502)
```

## Route Setup (CORS only on non-proxy routes)

```python
def _setup_routes(self):
    app = web.Application()
    
    # Add routes FIRST
    app.router.add_get("/", self.handle_index)
    app.router.add_get("/ws", self.handle_dashboard_ws)
    app.router.add_route("*", "/api/{path:.*}", self.proxy_api)
    
    # Setup CORS ONLY for dashboard routes (not proxy catch-all)
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*",
        )
    })
    
    for route in list(app.router.routes()):
        if "/api/" not in str(route.resource):
            cors.add(route)
```

## Frontend WebSocket Client

```javascript
function connect() {
    ws = new WebSocket('ws://localhost:8765/ws');  // Direct to main server
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
        reconnectAttempts = 0;
        updateConnectionStatus(true);
        // Subscribe
        ws.send(new TextEncoder().encode(
            JSON.stringify({type: 'dashboard_subscribe'}) + '\n'
        ));
    };

    ws.onmessage = (event) => {
        let data = event.data instanceof ArrayBuffer 
            ? new TextDecoder().decode(event.data) 
            : event.data;
        try {
            const msg = JSON.parse(data.trim());
            handleMessage(msg);
        } catch (e) {
            console.warn('Parse error:', e, data);
        }
    };

    ws.onclose = () => {
        updateConnectionStatus(false);
        if (reconnectAttempts < maxReconnectAttempts) {
            setTimeout(connect, Math.min(1000 * 2**reconnectAttempts, 30000));
            reconnectAttempts++;
        }
    };
}

function handleMessage(msg) {
    switch (msg.type) {
        case 'dashboard_update':
            updateState(msg.payload);
            break;
        case 'swarm_status':
            updateState({
                clients: msg.clients,
                tasks: {queued: msg.queued_tasks, active: msg.active_tasks}
            });
            break;
    }
}

function updateState(payload) {
    if (payload.clients) state.clients = payload.clients;
    if (payload.tasks) state.tasks = payload.tasks;
    if (payload.artifacts) state.artifacts = payload.artifacts;
    if (payload.activity) state.activity = payload.activity;
    renderAll();
}
```

## CORS Gotchas

| Issue | Solution |
|-------|----------|
| `add_route("*", "/api/{path:.*}")` conflicts with CORS preflight | Add routes first, then only apply CORS to non-proxy routes |
| `aiohttp_cors` adds OPTIONS handler automatically | Don't add manual OPTIONS handler for proxy routes |
| Proxy needs separate session lifecycle | Create session on first request if closed |

## Authentication Flow (Dashboard → Server)

1. Browser opens `http://localhost:8766/`
2. JS connects WS to `ws://localhost:8765/ws` (direct to main server)
3. Sends `dashboard_subscribe` binary message
4. Server adds WS to `dashboards` set
5. Server immediately sends full state via `dashboard_update`
6. All subsequent state changes broadcast to all dashboard WS clients
7. HTTP API calls proxied via dashboard `:8766/api/*` → server `:8765/api/*`