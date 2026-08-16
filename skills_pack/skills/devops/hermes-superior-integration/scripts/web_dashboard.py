#!/usr/bin/env python3
"""
Hermes Web Dashboard - Superior to Claude Code's lack of web UI
Full monitoring, control, and interaction via browser
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
from datetime import datetime
import asyncio
import json
import uuid
from pathlib import Path
import uvicorn
from contextlib import asynccontextmanager


# =============================================================================
# MODELS
# =============================================================================

class ChatMessage(BaseModel):
    role: str  # user, assistant, system, tool
    content: str
    timestamp: str = None
    tool_calls: List[Dict] = None
    tool_results: List[Dict] = None

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    model: Optional[str] = None
    toolsets: Optional[List[str]] = None
    max_turns: int = 20

class AgentTaskRequest(BaseModel):
    prompt: str
    agent_type: str = "subagent"
    agent_name: Optional[str] = None
    context: Dict = {}
    max_turns: int = 20

class LocalAgentCommand(BaseModel):
    command: str
    cwd: Optional[str] = None
    timeout: int = 120


# =============================================================================
# WEBSOCKET MANAGER
# =============================================================================

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.client_sessions: Dict[WebSocket, str] = {}
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        self.client_sessions.pop(websocket, None)
    
    async def send_personal(self, message: dict, websocket: WebSocket):
        try:
            await websocket.send_json(message)
        except:
            self.disconnect(websocket)
    
    async def broadcast(self, message: dict):
        for connection in self.active_connections[:]:
            try:
                await connection.send_json(message)
            except:
                self.disconnect(connection)


# =============================================================================
# SESSION MANAGER
# =============================================================================

class WebSessionManager:
    def __init__(self):
        self.sessions: Dict[str, Dict] = {}
    
    def create_session(self, session_id: str = None) -> str:
        sid = session_id or str(uuid.uuid4())[:8]
        self.sessions[sid] = {
            "id": sid,
            "created": datetime.now().isoformat(),
            "messages": [],
            "model": "free-router",
            "toolsets": [],
            "active": True
        }
        return sid
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        return self.sessions.get(session_id)
    
    def add_message(self, session_id: str, message: Dict):
        if session_id in self.sessions:
            msg = {
                "id": str(uuid.uuid4())[:8],
                "timestamp": datetime.now().isoformat(),
                **message
            }
            self.sessions[session_id]["messages"].append(msg)
            return msg
        return None
    
    def list_sessions(self) -> List[Dict]:
        return [
            {
                "id": s["id"],
                "created": s["created"],
                "message_count": len(s["messages"]),
                "model": s.get("model", "free-router"),
                "active": s.get("active", True)
            }
            for s in self.sessions.values()
        ]


# =============================================================================
# AGENT TASK MANAGER
# =============================================================================

class AgentTaskManager:
    def __init__(self):
        self.tasks: Dict[str, Dict] = {}
    
    def create_task(self, prompt: str, agent_type: str = "subagent", **kwargs) -> str:
        task_id = str(uuid.uuid4())[:8]
        self.tasks[task_id] = {
            "id": task_id,
            "prompt": prompt,
            "agent_type": agent_type,
            "status": "pending",
            "created": datetime.now().isoformat(),
            "result": None,
            "error": None,
            **kwargs
        }
        return task_id
    
    def get_task(self, task_id: str) -> Optional[Dict]:
        return self.tasks.get(task_id)
    
    def update_task(self, task_id: str, **updates):
        if task_id in self.tasks:
            self.tasks[task_id].update(updates)
    
    def list_tasks(self) -> List[Dict]:
        return list(self.tasks.values())


# =============================================================================
# LOCAL AGENT CLIENT
# =============================================================================

class LocalAgentClient:
    def __init__(self, base_url: str = "http://localhost:8765"):
        self.base_url = base_url
    
    async def execute(self, command: str, cwd: str = None, timeout: int = 120) -> Dict:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/command",
                json={"command": command, "cwd": cwd, "timeout": timeout}
            ) as resp:
                return await resp.json()
    
    async def read_file(self, path: str) -> Dict:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.base_url}/file/read", json={"path": path}) as resp:
                return await resp.json()
    
    async def write_file(self, path: str, content: str) -> Dict:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.base_url}/file/write", json={"path": path, "content": content}) as resp:
                return await resp.json()
    
    async def search(self, pattern: str, path: str = ".") -> Dict:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.base_url}/search", json={"pattern": pattern, "path": path}) as resp:
                return await resp.json()
    
    async def health_check(self) -> bool:
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/health") as resp:
                    return resp.status == 200
        except:
            return False


# =============================================================================
# FASTAPI APP
# =============================================================================

manager = ConnectionManager()
sessions = WebSessionManager()
tasks = AgentTaskManager()
local_agent = LocalAgentClient()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Starting Hermes Web Dashboard...")
    yield
    # Shutdown
    print("Shutting down...")


app = FastAPI(title="Hermes Web Dashboard", lifespan=lifespan)

# Static files and templates
static_dir = Path(__file__).parent.parent / "static"
templates_dir = Path(__file__).parent.parent / "templates"
static_dir.mkdir(parents=True, exist_ok=True)
templates_dir.mkdir(parents=True, exist_ok=True)

if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

templates = Jinja2Templates(directory=str(templates_dir))


# =============================================================================
# ROUTES
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/api/sessions")
async def list_sessions():
    return sessions.list_sessions()


@app.post("/api/sessions")
async def create_session():
    session_id = sessions.create_session()
    return {"session_id": session_id}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    session = sessions.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return session


@app.post("/api/sessions/{session_id}/chat")
async def chat(session_id: str, request: ChatRequest):
    session = sessions.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    
    # Add user message
    user_msg = sessions.add_message(session_id, {
        "role": "user",
        "content": request.message
    })
    
    # Broadcast to websockets
    await manager.broadcast({
        "type": "message",
        "session_id": session_id,
        "message": user_msg
    })
    
    # Here you'd call the actual Hermes agent
    # For now, simulate response
    async def simulate_response():
        await asyncio.sleep(0.5)
        response = f"Processing: {request.message}"
        assistant_msg = sessions.add_message(session_id, {
            "role": "assistant",
            "content": response
        })
        await manager.broadcast({
            "type": "message",
            "session_id": session_id,
            "message": assistant_msg
        })
    
    asyncio.create_task(simulate_response())
    
    return {"status": "processing", "message_id": user_msg["id"]}


@app.post("/api/agent/task")
async def create_agent_task(request: AgentTaskRequest):
    task_id = tasks.create_task(
        request.prompt,
        request.agent_type,
        agent_name=request.agent_name,
        context=request.context,
        max_turns=request.max_turns
    )
    return {"task_id": task_id, "status": "pending"}


@app.get("/api/agent/tasks")
async def list_agent_tasks():
    return tasks.list_tasks()


@app.get("/api/agent/tasks/{task_id}")
async def get_agent_task(task_id: str):
    task = tasks.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task


@app.post("/api/local/command")
async def local_command(request: LocalAgentCommand):
    result = await local_agent.execute(request.command, request.cwd, request.timeout)
    return result


@app.post("/api/local/file/read")
async def local_read_file(path: str):
    return await local_agent.read_file(path)


@app.post("/api/local/file/write")
async def local_write_file(path: str, content: str):
    return await local_agent.write_file(path, content)


@app.post("/api/local/search")
async def local_search(pattern: str, path: str = "."):
    return await local_agent.search(pattern, path)


@app.get("/api/local/health")
async def local_health():
    healthy = await local_agent.health_check()
    return {"healthy": healthy, "url": local_agent.base_url}


@app.get("/api/status")
async def system_status():
    local_healthy = await local_agent.health_check()
    return {
        "local_agent": "connected" if local_healthy else "disconnected",
        "sessions": len(sessions.sessions),
        "tasks": len(tasks.tasks),
        "connections": len(manager.active_connections),
        "timestamp": datetime.now().isoformat()
    }


# =============================================================================
# WEBSOCKET
# =============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            
            if msg_type == "subscribe":
                session_id = data.get("session_id")
                if session_id:
                    manager.client_sessions[websocket] = session_id
                    await websocket.send_json({"type": "subscribed", "session_id": session_id})
            
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})
    
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# =============================================================================
# RUN
# =============================================================================

def create_dashboard_html():
    """Generate dashboard HTML if template doesn't exist."""
    dashboard_html = """
<!DOCTYPE html>
<html>
<head>
    <title>Hermes Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', monospace; background: #1a1a2e; color: #eee; height: 100vh; display: flex; }
        .sidebar { width: 280px; background: #16213e; border-right: 1px solid #0f3460; display: flex; flex-direction: column; }
        .sidebar-header { padding: 20px; border-bottom: 1px solid #0f3460; }
        .sidebar-title { font-size: 1.2rem; font-weight: bold; color: #e94560; }
        .session-list { flex: 1; overflow-y: auto; padding: 10px; }
        .session-item { padding: 12px; background: #1a1a2e; border-radius: 8px; margin-bottom: 8px; cursor: pointer; transition: all 0.2s; border: 1px solid transparent; }
        .session-item:hover { background: #0f3460; border-color: #e94560; }
        .session-item.active { background: #0f3460; border-color: #e94560; }
        .session-name { font-weight: bold; color: #e94560; margin-bottom: 4px; }
        .session-meta { font-size: 0.75rem; color: #888; }
        .main { flex: 1; display: flex; flex-direction: column; background: #1a1a2e; }
        .header { padding: 15px 20px; background: #16213e; border-bottom: 1px solid #0f3460; display: flex; justify-content: space-between; align-items: center; }
        .model-selector { background: #0f3460; border: 1px solid #e94560; color: #eee; padding: 8px 16px; border-radius: 6px; }
        .chat-area { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 16px; }
        .message { max-width: 80%; padding: 12px 16px; border-radius: 12px; animation: fadeIn 0.3s; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .message.user { background: #0f3460; align-self: flex-end; border-bottom-right-radius: 4px; }
        .message.assistant { background: #16213e; align-self: flex-start; border-bottom-left-radius: 4px; }
        .message.tool { background: #e94560; align-self: flex-start; border-bottom-left-radius: 4px; color: #1a1a2e; font-family: monospace; font-size: 0.85rem; }
        .message.system { background: #e94560; color: #1a1a2e; font-size: 0.85rem; text-align: center; align-self: center; max-width: 60%; }
        .message-header { display: flex; gap: 8px; margin-bottom: 8px; font-size: 0.75rem; color: #888; }
        .message-content { white-space: pre-wrap; word-wrap: break-word; }
        .input-area { padding: 20px; background: #16213e; border-top: 1px solid #0f3460; }
        .input-wrapper { display: flex; gap: 12px; max-width: 900px; margin: 0 auto; }
        .input-field { flex: 1; background: #1a1a2e; border: 1px solid #0f3460; color: #eee; padding: 12px 16px; border-radius: 8px; font-family: inherit; font-size: 1rem; resize: none; min-height: 60px; max-height: 200px; }
        .input-field:focus { outline: none; border-color: #e94560; }
        .send-btn { background: #e94560; color: #eee; border: none; padding: 12px 24px; border-radius: 8px; cursor: pointer; font-weight: bold; align-self: flex-end; }
        .send-btn:hover { background: #d63450; }
        .status-bar { display: flex; gap: 20px; font-size: 0.8rem; color: #888; }
        .status-item { display: flex; gap: 6px; align-items: center; }
        .dot { width: 8px; height: 8px; border-radius: 50%; }
        .dot.connected { background: #4ade80; }
        .dot.disconnected { background: #f87171; }
        .new-session-btn { width: 100%; background: #0f3460; border: 1px solid #e94560; color: #e94560; padding: 12px; border-radius: 8px; cursor: pointer; margin-top: 10px; }
        .new-session-btn:hover { background: #e94560; color: #eee; }
        .tasks-panel { width: 300px; background: #16213e; border-left: 1px solid #0f3460; padding: 20px; overflow-y: auto; }
        .task-item { background: #1a1a2e; padding: 12px; border-radius: 8px; margin-bottom: 8px; border: 1px solid transparent; }
        .task-item.running { border-color: #fbbf24; }
        .task-item.completed { border-color: #4ade80; }
        .task-item.failed { border-color: #f87171; }
        .task-header { display: flex; justify-content: space-between; margin-bottom: 8px; }
        .task-prompt { font-size: 0.85rem; color: #aaa; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .status-badge { font-size: 0.7rem; padding: 2px 8px; border-radius: 12px; font-weight: bold; }
        .status-pending { background: #1a1a2e; color: #fbbf24; }
        .status-running { background: #1a1a2e; color: #fbbf24; }
        .status-completed { background: #1a1a2e; color: #4ade80; }
        .status-failed { background: #1a1a2e; color: #f87171; }
        .local-agent-panel { width: 300px; background: #16213e; border-left: 1px solid #0f3460; padding: 20px; }
        .command-input { background: #1a1a2e; border: 1px solid #0f3460; color: #eee; padding: 10px; border-radius: 6px; width: 100%; font-family: monospace; margin-bottom: 10px; }
        .command-output { background: #1a1a2e; border: 1px solid #0f3460; color: #4ade80; padding: 12px; border-radius: 6px; font-family: monospace; font-size: 0.8rem; max-height: 300px; overflow-y: auto; white-space: pre-wrap; }
    </style>
</head>
<body>
    <div class="sidebar">
        <div class="sidebar-header">
            <div class="sidebar-title">🤖 Hermes</div>
        </div>
        <div class="session-list" id="sessionList">
            <button class="new-session-btn" onclick="createSession()">+ New Session</button>
            <div id="sessions"></div>
        </div>
    </div>
    <div class="main">
        <div class="header">
            <div>
                <select class="model-selector" id="modelSelector">
                    <option value="free-router">🆓 Free Router (Auto)</option>
                    <option value="nemotron-3-ultra">⚡ Nemotron 3 Ultra</option>
                    <option value="deepseek-v3">🧠 DeepSeek V3</option>
                    <option value="solar-pro">☀️ Solar Pro</option>
                    <option value="glm-5.2">🌟 GLM 5.2</option>
                    <option value="local">🏠 Local Model</option>
                </select>
            </div>
            <div class="status-bar">
                <div class="status-item"><span class="dot connected" id="localAgentDot"></span><span>Local Agent</span></div>
                <div class="status-item"><span class="dot connected"></span><span>WebSocket</span></div>
            </div>
        </div>
        <div class="chat-area" id="chatArea"></div>
        <div class="input-area">
            <div class="input-wrapper">
                <textarea class="input-field" id="inputField" placeholder="Type your message... (Enter to send, Shift+Enter for newline)" rows="2"></textarea>
                <button class="send-btn" onclick="sendMessage()">Send</button>
            </div>
        </div>
    </div>
    <div class="tasks-panel">
        <h3 style="color: #e94560; margin-bottom: 16px;">🤖 Agent Tasks</h3>
        <div id="tasksList"></div>
    </div>
    <div class="local-agent-panel">
        <h3 style="color: #e94560; margin-bottom: 16px;">🖥️ Local Agent</h3>
        <input class="command-input" id="cmdInput" placeholder="shell command..." onkeypress="if(event.key==='Enter') runCommand()">
        <button onclick="runCommand()" style="width: 100%; background: #e94560; border: none; color: #eee; padding: 10px; border-radius: 6px; cursor: pointer;">Run Command</button>
        <div class="command-output" id="cmdOutput">Ready...</div>
    </div>

    <script>
        let currentSession = null;
        let ws = null;
        
        function connectWS() {
            ws = new WebSocket(`ws://${location.host}/ws`);
            ws.onopen = () => {
                document.getElementById('localAgentDot').className = 'dot connected';
                if (currentSession) ws.send(JSON.stringify({type: 'subscribe', session_id: currentSession}));
            };
            ws.onclose = () => {
                document.getElementById('localAgentDot').className = 'dot disconnected';
                setTimeout(connectWS, 3000);
            };
            ws.onmessage = (e) => {
                const msg = JSON.parse(e.data);
                if (msg.type === 'message' && msg.session_id === currentSession) {
                    addMessage(msg.message);
                } else if (msg.type === 'task_update') {
                    updateTask(msg.task);
                }
            };
        }
        
        function addMessage(msg) {
            const area = document.getElementById('chatArea');
            const div = document.createElement('div');
            div.className = `message ${msg.role}`;
            div.innerHTML = `
                <div class="message-header">
                    <span>${msg.role}</span>
                    <span>${new Date(msg.timestamp).toLocaleTimeString()}</span>
                </div>
                <div class="message-content">${escapeHtml(msg.content)}</div>
            `;
            area.appendChild(div);
            area.scrollTop = area.scrollHeight;
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML.replace(/\\n/g, '<br>');
        }
        
        async function createSession() {
            const res = await fetch('/api/sessions', {method: 'POST'});
            const data = await res.json();
            selectSession(data.session_id);
        }
        
        async function loadSessions() {
            const res = await fetch('/api/sessions');
            const sessions = await res.json();
            const container = document.getElementById('sessions');
            container.innerHTML = '';
            sessions.forEach(s => {
                const div = document.createElement('div');
                div.className = 'session-item' + (s.id === currentSession ? ' active' : '');
                div.onclick = () => selectSession(s.id);
                div.innerHTML = `
                    <div class="session-name">${s.id}</div>
                    <div class="session-meta">${s.message_count} messages · ${s.model}</div>
                `;
                container.appendChild(div);
            });
        }
        
        function selectSession(id) {
            currentSession = id;
            document.querySelectorAll('.session-item').forEach(el => el.classList.toggle('active', el.onclick.toString().includes(id)));
            loadSession(id);
            if (ws && ws.readyState === 1) ws.send(JSON.stringify({type: 'subscribe', session_id: id}));
        }
        
        async function loadSession(id) {
            const res = await fetch(`/api/sessions/${id}`);
            const session = await res.json();
            const area = document.getElementById('chatArea');
            area.innerHTML = '';
            session.messages.forEach(addMessage);
        }
        
        async function sendMessage() {
            const input = document.getElementById('inputField');
            const text = input.value.trim();
            if (!text || !currentSession) return;
            
            input.value = '';
            
            await fetch(`/api/sessions/${currentSession}/chat`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({message: text})
            });
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML.replace(/\\n/g, '<br>');
        }
        
        async function runCommand() {
            const input = document.getElementById('cmdInput');
            const cmd = input.value.trim();
            if (!cmd) return;
            
            const output = document.getElementById('cmdOutput');
            output.textContent = `$ ${cmd}\\nRunning...`;
            input.value = '';
            
            try {
                const res = await fetch('/api/local/command', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({command: cmd})
                });
                const data = await res.json();
                output.textContent = `$ ${cmd}\\n${data.stdout || ''}${data.stderr ? '\\n' + data.stderr : ''}\\nExit: ${data.returncode}`;
            } catch (e) {
                output.textContent = `Error: ${e}`;
            }
        }
        
        async function loadTasks() {
            const res = await fetch('/api/agent/tasks');
            const tasks = await res.json();
            const container = document.getElementById('tasksList');
            container.innerHTML = '';
            tasks.forEach(t => {
                const div = document.createElement('div');
                div.className = `task-item ${t.status}`;
                div.innerHTML = `
                    <div class="task-header">
                        <span>${t.id}</span>
                        <span class="status-badge status-${t.status}">${t.status.toUpperCase()}</span>
                    </div>
                    <div class="task-prompt">${t.prompt.substring(0, 60)}...</div>
                `;
                container.appendChild(div);
            });
        }
        
        // Init
        document.getElementById('inputField').addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
        
        connectWS();
        loadSessions();
        loadTasks();
        setInterval(loadTasks, 5000);
        
        // Check local agent
        fetch('/api/local/health').then(r => r.json()).then(d => {
            document.getElementById('localAgentDot').className = 'dot ' + (d.healthy ? 'connected' : 'disconnected');
        });
    </script>
</body>
</html>
"""
    (templates_dir / "dashboard.html").write_text(dashboard_html)
    return dashboard_html


if __name__ == "__main__":
    # Create dashboard template if not exists
    if not (templates_dir / "dashboard.html").exists():
        create_dashboard_html()
    
    uvicorn.run(app, host="0.0.0.0", port=9119)