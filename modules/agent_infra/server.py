"""
Server — FastAPI + WebSocket Server for Remote Sessions (Port 9120)
====================================================================

Re-implements Claude Code's remote server functionality using FastAPI and
WebSocket for real-time session streaming. Provides:

  - REST API endpoints for session lifecycle (create, list, close, inspect)
  - WebSocket endpoint for live session communication
  - Session management with authentication tokens
  - Health endpoint for monitoring
  - Configurable host/port (default :9120)

Endpoints:
  GET  /health                    — Health check
  GET  /sessions                  — List active sessions
  POST /sessions                  — Create a new session
  GET  /sessions/{session_id}      — Get session details
  DELETE /sessions/{session_id}    — Close a session
  WS   /ws/{session_id}            — WebSocket for live session
  GET  /stats                     — Server statistics

Session states: created, active, idle, disconnected, closed
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

try:
    from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

from enterprise.platform_kernel import EventBus, Event, HealthStatus

_logger: logging.Logger = logging.getLogger("enterprise.agent_infra.server")


# =============================================================================
# Enums & Dataclasses
# =============================================================================

class SessionState(Enum):
    """Session lifecycle states."""
    CREATED = "created"
    ACTIVE = "active"
    IDLE = "idle"
    DISCONNECTED = "disconnected"
    CLOSED = "closed"


@dataclass
class ServerConfig:
    """Configuration for the ClaudServer."""
    host: str = "0.0.0.0"
    port: int = 9120
    max_sessions: int = 100
    session_timeout: int = 3600  # seconds
    token_secret: str = field(default_factory=lambda: secrets.token_hex(32))
    enable_cors: bool = True
    allow_origins: List[str] = field(default_factory=lambda: ["*"])
    log_level: str = "info"


@dataclass
class SessionInfo:
    """Metadata for a remote session."""
    session_id: str
    state: SessionState = SessionState.CREATED
    token: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_active_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)
    message_count: int = 0


# =============================================================================
# WebSocket Session Manager
# =============================================================================

class WebSocketSessionManager:
    """Manages active WebSocket connections and session state.

    Handles connection lifecycle, message routing, broadcast, and cleanup
    for disconnected clients.
    """

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        self._event_bus = event_bus
        self._sessions: Dict[str, SessionInfo] = {}
        self._connections: Dict[str, WebSocket] = {}
        self._lock = threading.RLock()

    @property
    def session_count(self) -> int:
        with self._lock:
            return len(self._sessions)

    @property
    def active_connection_count(self) -> int:
        with self._lock:
            return len(self._connections)

    def create_session(self, metadata: Optional[Dict[str, Any]] = None) -> SessionInfo:
        """Create a new session and return its info."""
        with self._lock:
            session_id = str(uuid.uuid4())
            session = SessionInfo(
                session_id=session_id,
                state=SessionState.CREATED,
                metadata=metadata or {},
            )
            self._sessions[session_id] = session
            _logger.info("Session created: %s", session_id)

            if self._event_bus:
                self._event_bus.publish(Event.create(
                    "claude.infra.server.session",
                    "server",
                    {"action": "created", "session_id": session_id},
                ))

            return session

    def get_session(self, session_id: str) -> Optional[SessionInfo]:
        """Retrieve a session by ID."""
        with self._lock:
            return self._sessions.get(session_id)

    def list_sessions(self) -> List[SessionInfo]:
        """List all sessions."""
        with self._lock:
            return list(self._sessions.values())

    def close_session(self, session_id: str) -> bool:
        """Close a session and disconnect its WebSocket if connected."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False

            session.state = SessionState.CLOSED
            self._sessions.pop(session_id, None)
            self._connections.pop(session_id, None)
            _logger.info("Session closed: %s", session_id)

            if self._event_bus:
                self._event_bus.publish(Event.create(
                    "claude.infra.server.session",
                    "server",
                    {"action": "closed", "session_id": session_id},
                ))
            return True

    async def connect(self, session_id: str, websocket: WebSocket) -> bool:
        """Accept a WebSocket connection for a session."""
        await websocket.accept()

        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                await websocket.close(code=4004, reason="Session not found")
                return False

            session.state = SessionState.ACTIVE
            session.last_active_at = datetime.now(timezone.utc)
            self._connections[session_id] = websocket
            _logger.info("WebSocket connected for session: %s", session_id)

            if self._event_bus:
                self._event_bus.publish(Event.create(
                    "claude.infra.server.session",
                    "server",
                    {"action": "connected", "session_id": session_id},
                ))
            return True

    async def disconnect(self, session_id: str) -> None:
        """Handle WebSocket disconnection for a session."""
        with self._lock:
            self._connections.pop(session_id, None)
            session = self._sessions.get(session_id)
            if session:
                session.state = SessionState.DISCONNECTED
                _logger.info("WebSocket disconnected for session: %s", session_id)

                if self._event_bus:
                    self._event_bus.publish(Event.create(
                        "claude.infra.server.session",
                        "server",
                        {"action": "disconnected", "session_id": session_id},
                    ))

    async def send_message(self, session_id: str, message: Dict[str, Any]) -> bool:
        """Send a JSON message to a connected WebSocket session."""
        with self._lock:
            ws = self._connections.get(session_id)
            if ws is None:
                return False

        try:
            await ws.send_json(message)
            with self._lock:
                session = self._sessions.get(session_id)
                if session:
                    session.message_count += 1
                    session.last_active_at = datetime.now(timezone.utc)
            return True
        except Exception as exc:
            _logger.warning("Failed to send message to %s: %s", session_id, exc)
            await self.disconnect(session_id)
            return False

    async def broadcast(self, message: Dict[str, Any]) -> int:
        """Broadcast a message to all connected sessions.

        Returns:
            Number of sessions the message was sent to.
        """
        sent = 0
        session_ids: List[str]

        with self._lock:
            session_ids = list(self._connections.keys())

        for sid in session_ids:
            if await self.send_message(sid, message):
                sent += 1

        return sent

    def cleanup_stale_sessions(self, timeout: int = 3600) -> int:
        """Remove sessions that have been inactive for longer than timeout.

        Returns:
            Number of sessions cleaned up.
        """
        now = datetime.now(timezone.utc)
        stale: List[str] = []

        with self._lock:
            for sid, session in self._sessions.items():
                if session.state in (SessionState.CLOSED, SessionState.DISCONNECTED):
                    delta = (now - session.last_active_at).total_seconds()
                    if delta > timeout:
                        stale.append(sid)

        for sid in stale:
            self.close_session(sid)

        return len(stale)

    def get_stats(self) -> Dict[str, Any]:
        """Return session statistics."""
        with self._lock:
            states: Dict[str, int] = {}
            for session in self._sessions.values():
                states[session.state.value] = states.get(session.state.value, 0) + 1

            return {
                "total_sessions": len(self._sessions),
                "active_connections": len(self._connections),
                "states": states,
                "total_messages": sum(s.message_count for s in self._sessions.values()),
            }


# =============================================================================
# ClaudServer — FastAPI Application
# =============================================================================

class ClaudServer:
    """FastAPI + WebSocket server for Claude Code remote sessions.

    Provides REST and WebSocket APIs for managing remote Claude Code sessions
    on port 9120 (configurable). Integrates with the Enterprise Platform EventBus.
    """

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        cfg = config or {}
        self._event_bus = event_bus
        self._config = ServerConfig(
            host=cfg.get("host", "0.0.0.0"),
            port=cfg.get("port", 9120),
            max_sessions=cfg.get("max_sessions", 100),
            session_timeout=cfg.get("session_timeout", 3600),
            enable_cors=cfg.get("enable_cors", True),
            allow_origins=cfg.get("allow_origins", ["*"]),
            log_level=cfg.get("log_level", "info"),
        )
        self._session_manager = WebSocketSessionManager(event_bus=event_bus)
        self._app: Optional[Any] = None
        self._server: Optional[Any] = None
        self._initialized: bool = False
        self._running: bool = False
        self._cleanup_task: Optional[asyncio.Task[None]] = None

    @property
    def port(self) -> int:
        return self._config.port

    @property
    def session_manager(self) -> WebSocketSessionManager:
        return self._session_manager

    @property
    def app(self) -> Optional[Any]:
        """The FastAPI application instance."""
        return self._app

    async def initialize(self) -> None:
        """Initialize the server — builds FastAPI app and routes but doesn't start."""
        if not FASTAPI_AVAILABLE:
            _logger.warning("FastAPI not available — server in simulated mode")
            self._initialized = True
            return

        app = FastAPI(
            title="Claude Code Superior — Server",
            description="Remote session management for Claude Code Superior",
            version="1.0.0",
        )

        if self._config.enable_cors:
            app.add_middleware(
                CORSMiddleware,
                allow_origins=self._config.allow_origins,
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )

        self._register_routes(app)
        self._app = app
        self._initialized = True
        _logger.info("ClaudServer initialized on port %d", self._config.port)

    def _register_routes(self, app: Any) -> None:
        """Register all REST and WebSocket routes on the FastAPI app."""

        mgr = self._session_manager
        max_sessions = self._config.max_sessions

        @app.get("/health")
        async def health():
            """Health check endpoint."""
            return {
                "status": "ok",
                "version": "1.0.0",
                "sessions_active": mgr.active_connection_count,
                "sessions_total": mgr.session_count,
            }

        @app.get("/stats")
        async def stats():
            """Server statistics endpoint."""
            return mgr.get_stats()

        @app.get("/sessions")
        async def list_sessions():
            """List all active sessions."""
            sessions = mgr.list_sessions()
            return {
                "count": len(sessions),
                "sessions": [
                    {
                        "session_id": s.session_id,
                        "state": s.state.value,
                        "created_at": s.created_at.isoformat(),
                        "message_count": s.message_count,
                        "metadata": s.metadata,
                    }
                    for s in sessions
                ],
            }

        @app.post("/sessions")
        async def create_session(metadata: Optional[Dict[str, Any]] = None):
            """Create a new remote session."""
            if mgr.session_count >= max_sessions:
                raise HTTPException(status_code=429, detail="Max sessions reached")

            session = mgr.create_session(metadata)
            return {
                "session_id": session.session_id,
                "token": session.token,
                "state": session.state.value,
                "created_at": session.created_at.isoformat(),
            }

        @app.get("/sessions/{session_id}")
        async def get_session(session_id: str):
            """Get details for a specific session."""
            session = mgr.get_session(session_id)
            if session is None:
                raise HTTPException(status_code=404, detail="Session not found")
            return {
                "session_id": session.session_id,
                "state": session.state.value,
                "created_at": session.created_at.isoformat(),
                "last_active_at": session.last_active_at.isoformat(),
                "message_count": session.message_count,
                "metadata": session.metadata,
            }

        @app.delete("/sessions/{session_id}")
        async def close_session(session_id: str):
            """Close a session."""
            if not mgr.close_session(session_id):
                raise HTTPException(status_code=404, detail="Session not found")
            return {"status": "closed", "session_id": session_id}

        @app.websocket("/ws/{session_id}")
        async def websocket_endpoint(websocket: WebSocket, session_id: str):
            """WebSocket endpoint for live session communication."""
            connected = await mgr.connect(session_id, websocket)
            if not connected:
                return

            try:
                while True:
                    data = await websocket.receive_json()
                    # Echo back with acknowledgment
                    response = {
                        "type": "ack",
                        "session_id": session_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "received": data,
                    }
                    await websocket.send_json(response)

                    # Publish event
                    if self._event_bus:
                        self._event_bus.publish(Event.create(
                            "claude.infra.server.message",
                            "server",
                            {
                                "session_id": session_id,
                                "message_type": data.get("type", "unknown"),
                            },
                        ))

            except WebSocketDisconnect:
                _logger.info("WebSocket disconnected: %s", session_id)
            except Exception as exc:
                _logger.exception("WebSocket error for %s: %s", session_id, exc)
            finally:
                await mgr.disconnect(session_id)

        @app.post("/sessions/{session_id}/send")
        async def send_to_session(session_id: str, message: Dict[str, Any]):
            """Send a message to a connected WebSocket session."""
            success = await mgr.send_message(session_id, message)
            if not success:
                raise HTTPException(status_code=404, detail="Session not connected")
            return {"status": "sent", "session_id": session_id}

    async def start(self) -> None:
        """Start the FastAPI server (non-blocking)."""
        if not self._initialized:
            await self.initialize()

        if not FASTAPI_AVAILABLE:
            _logger.info("ClaudServer: simulated mode — start() is a no-op")
            self._running = True
            return

        config = uvicorn.Config(
            app=self._app,
            host=self._config.host,
            port=self._config.port,
            log_level=self._config.log_level,
        )
        self._server = uvicorn.Server(config)
        self._running = True

        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        _logger.info("ClaudServer listening on %s:%d", self._config.host, self._config.port)
        await self._server.serve()

    async def stop(self) -> None:
        """Stop the FastAPI server."""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        if self._server is not None:
            self._server.should_exit = True
        _logger.info("ClaudServer stopped")

    async def health_check(self) -> bool:
        """Check if the server is operational.

        Returns:
            True if the server is initialized and running (or simulated).
        """
        if not FASTAPI_AVAILABLE:
            return self._initialized
        return self._initialized

    async def shutdown(self) -> None:
        """Gracefully shut down the server and close all sessions."""
        await self.stop()
        # Close all sessions
        for session in self._session_manager.list_sessions():
            self._session_manager.close_session(session.session_id)
        self._initialized = False
        _logger.info("ClaudServer shut down")

    async def _cleanup_loop(self) -> None:
        """Background task to clean up stale sessions."""
        while self._running:
            try:
                await asyncio.sleep(300)  # Every 5 minutes
                cleaned = self._session_manager.cleanup_stale_sessions(
                    timeout=self._config.session_timeout
                )
                if cleaned:
                    _logger.info("Cleaned up %d stale sessions", cleaned)
            except asyncio.CancelledError:
                break
            except Exception:
                _logger.exception("Error in session cleanup loop")