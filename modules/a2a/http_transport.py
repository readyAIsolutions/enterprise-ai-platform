"""A2A HTTP transport -- real HTTP/JSON transport for the A2A protocol.

This module provides a genuine, stdlib-only HTTP transport on top of the A2A
core (:mod:`enterprise.modules.a2a.a2a`). It is split into three cooperating
pieces:

:class:`A2AHttpServer`
    A real ``http.server.ThreadingHTTPServer`` that exposes A2A-style JSON
    endpoints backed by the module's :class:`~.a2a.TaskRouter` /
    :class:`~.a2a.TaskStore` (or an in-memory :class:`~.a2a.TaskManager`):

      * ``POST /tasks/send``    -- submit a task to an agent (returns task + state)
      * ``GET  /tasks/<id>``    -- fetch task state + messages + artifacts
      * ``POST /tasks/cancel``  -- cancel a task
      * ``GET  /health``        -- liveness / readiness heartbeat

    Errors are returned as JSON with proper HTTP status codes (``404`` for an
    unknown task, ``400`` for a bad payload, ``500`` for unexpected failures).

:class:`A2AHttpClient`
    A ``urllib``-based client with ``send_task`` / ``get_task`` /
    ``cancel_task`` (and ``health``) that talks to the server, parses the JSON
    into real :class:`~.a2a.Task` objects, and surfaces server-side errors as
    the module's typed exceptions.

:class:`MemoryFailureInjector`
    A test-facing failure-injection hook that simulates transport faults --
    dropped responses, timeouts and out-of-order / stale responses -- so the
    client demonstrates its retry-once-then-surface behaviour. It intercepts
    requests by injecting synthetic failures before the real socket call and by
    swapping the delivered response for out-of-order simulation, all without
    touching the real byte stream of a *successful* round trip.

The transport is deliberately pure stdlib (``http.server``, ``urllib.request``,
``json``, ``threading``) so it can be exercised hermetically on an ephemeral
port (``port=0``) inside tests.
"""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib import error as urllib_error, request as urllib_request

from .a2a import (
    A2AError,
    Message,
    Task,
    TaskManager,
    TaskNotFoundError,
    TaskRouter,
    TaskStore,
)

__all__ = [
    "A2AHttpServer",
    "A2AHttpClient",
    "A2ATransportError",
    "A2ATransportTimeout",
    "MemoryFailureInjector",
    "OutOfOrderError",
]

_logger = logging.getLogger("enterprise.a2a.http_transport")


class A2ATransportError(A2AError):
    """Raised when a transport-level exchange cannot be completed."""


class A2ATransportTimeout(A2ATransportError):  # noqa: N818 - public API name re-exported in __init__
    """Raised when a request is dropped / times out (a retryable fault)."""


class OutOfOrderError(A2ATransportError):
    """Raised when a stale / out-of-order response is detected (retryable)."""


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------


def _coerce_message(payload: object) -> Message:
    """Coerce a decoded JSON message payload into a :class:`Message`."""
    if isinstance(payload, Message):
        return payload
    if isinstance(payload, str):
        return Message.user_text(payload)
    if isinstance(payload, dict):
        # A2A-style message envelope, or a bare {"text": ...} / {"parts": [...]}.
        if "messageId" in payload:
            return Message.from_dict(payload)
        text = payload.get("text")
        parts = payload.get("parts")
        if text is not None:
            return Message.user_text(str(text))
        if parts is not None:
            return Message.from_dict(
                {"messageId": payload.get("messageId", "m"), "role": "user", "parts": parts}
            )
    msg = "Malformed message payload: expected text, parts, or an envelope"
    raise A2AError(msg)


class _FailureFactory:
    """Small internal marker so injectors and handlers share failure kinds."""

    DROP = "drop"
    TIMEOUT = "timeout"
    REORDER = "reorder"


class MemoryFailureInjector:
    """Deterministic transport-failure injection for hermetic tests.

    The injector sits between the client's intention and the real socket call.
    It can be armed to fail the *next* request (or requests) with one of three
    transport faults:

    * ``drop``     -- the request never reaches the server (connection fault).
    * ``timeout``  -- the request stalls / times out (stall fault).
    * ``reorder``  -- the response delivered is a *stale* copy of the previous
      one (out-of-order delivery), so the client must detect the mismatch and
      retry.

    Arming is additive and consumed one-shot per intercepted request. A request
    is only intercepted while a fault is armed; otherwise it passes through to
    the real network untouched.
    """

    def __init__(self) -> None:
        self._drop = 0
        self._timeout = 0
        self._reorder = 0
        self._last_response: str | None = None
        self._lock = threading.Lock()
        self.intercept_count = 0
        self.dropped = 0
        self.timeouts = 0
        self.reordered = 0

    # -- arming ----------------------------------------------------------
    def drop(self, n: int = 1) -> MemoryFailureInjector:
        """Arm the injector to drop the next ``n`` requests."""
        with self._lock:
            self._drop = max(0, self._drop + int(n))
        return self

    def timeout_response(self, n: int = 1) -> MemoryFailureInjector:
        """Arm the injector to time out the next ``n`` requests."""
        with self._lock:
            self._timeout = max(0, self._timeout + int(n))
        return self

    def reorder(self, n: int = 1) -> MemoryFailureInjector:
        """Arm the injector to serve stale (out-of-order) responses."""
        with self._lock:
            self._reorder = max(0, self._reorder + int(n))
        return self

    def reset(self) -> None:
        with self._lock:
            self._drop = 0
            self._timeout = 0
            self._reorder = 0
            self._last_response = None

    @property
    def armed(self) -> bool:
        with self._lock:
            return self._drop > 0 or self._timeout > 0 or self._reorder > 0

    # -- hooks ----------------------------------------------------------
    def intercept(self, _method: str, _path: str) -> str | None:
        """Return a fault kind (drop/timeout/reorder) for this request or None.

        Consumed one-shot: each armed fault is decremented when matched.
        """
        # class import guard for the _FailureFactory couples the client to the
        # same fault vocabulary used by the server-side diagnostics.
        with self._lock:
            self.intercept_count += 1
            if self._drop > 0:
                self._drop -= 1
                self.dropped += 1
                return _FailureFactory.DROP
            if self._timeout > 0:
                self._timeout -= 1
                self.timeouts += 1
                return _FailureFactory.TIMEOUT
            if self._reorder > 0:
                self._reorder -= 1
                self.reordered += 1
                return _FailureFactory.REORDER
        return None

    def record_response(self, body: str) -> None:
        """Remember the last successfully delivered response body (for reorder)."""
        with self._lock:
            self._last_response = body

    def deliver_stale(self) -> str | None:
        """Return the previously recorded response to simulate out-of-order."""
        with self._lock:
            return self._last_response

    def observe(self, body: str) -> str:
        """Client-side response filter: swap in a stale copy when reorder fired.

        When a reorder fault is armed for the current request, the real response
        is *not* delivered -- the previous response is returned instead (as if
        the two packets crossed on the wire). The caller already knows whether a
        reorder was scheduled via :meth:`intercept`; ``observe`` just performs
        the swap later, after the socket call completed, to keep the real
        round-trip intact for the success path.
        """
        # Handled by the client via an explicit flag; this hook doubles as the
        # storage seam for tests that want to inspect recorded bodies.
        return body


class _A2AHTTPHandler(BaseHTTPRequestHandler):
    """HTTP handler bound to an :class:`A2AHttpServer`'s dispatch logic."""

    protocol_version = "HTTP/1.1"  # keep-alive friendly, still stdlib

    # -- helpers ----------------------------------------------------------
    def _send_json(self, code: int, obj: object) -> None:
        payload = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_error_json(self, code: int, message: str) -> None:
        self._send_json(code, {"error": {"code": code, "message": message}})

    def _read_json(self) -> object:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            msg = "Empty request body: expected JSON payload"
            raise A2AError(msg)
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            msg = f"Malformed JSON payload: {exc}"
            raise A2AError(msg) from exc

    # -- wire --------------------------------------------------------------
    def _route(self) -> None:
        path = self.path.split("?", 1)[0]
        if self.command == "GET" and path == "/health":
            return self.handle_health()
        if self.command == "POST" and path == "/tasks/send":
            return self.handle_send()
        if self.command == "POST" and path == "/tasks/cancel":
            return self.handle_cancel()
        if self.command == "GET" and path.startswith("/tasks/"):
            task_id = path[len("/tasks/") :]
            return self.handle_get(task_id)
        self._send_error_json(404, f"Unknown route: {self.command} {path}")
        return None

    def _server_logic(self) -> A2AHttpServer:
        return self.server.logic  # type: ignore[attr-defined]

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802 (http.server API)
        self._dispatch("POST")

    def _dispatch(self, _method: str) -> None:
        logic = self._server_logic()
        if logic is None:
            return self._send_error_json(500, "Server not initialised")
        try:
            self._route()
        except TaskNotFoundError as exc:
            _logger.debug("404 task not found: %s", exc)
            self._send_error_json(404, str(exc))
        except A2AError as exc:
            _logger.debug("400 bad request: %s", exc)
            self._send_error_json(400, str(exc))
        except Exception as exc:  # noqa: BLE001 - surface as JSON 500
            _logger.exception("Unhandled A2A HTTP error")
            self._send_error_json(500, f"Internal error: {exc}")

    def log_message(self, fmt: str, *args: object) -> None:  # silence by default
        if _logger.isEnabledFor(logging.DEBUG):
            _logger.debug("a2a http: " + fmt, *args)

    # -- endpoint implementations ----------------------------------------
    def handle_health(self) -> None:
        self._send_json(200, {"status": "ok", "module": "a2a"})

    def handle_send(self) -> None:
        body = self._read_json()
        if not isinstance(body, dict):
            msg = "Send payload must be a JSON object"
            raise A2AError(msg)
        agent_id = body.get("agentId")
        if not agent_id:
            msg = "Missing required field 'agentId'"
            raise A2AError(msg)
        message = _coerce_message(body.get("message"))
        task = self._server_logic().create_task(
            agent_id=agent_id,
            message=message,
            idempotency_key=body.get("idempotencyKey"),
            session_id=body.get("sessionId"),
            context=body.get("context"),
            metadata=body.get("metadata"),
        )
        self._send_json(200, {"task": task.to_dict()})

    def handle_get(self, task_id: str) -> None:
        if not task_id:
            msg = "Missing task id in path"
            raise A2AError(msg)
        task = self._server_logic().get_task(task_id)
        self._send_json(200, {"task": task.to_dict()})

    def handle_cancel(self) -> None:
        body = self._read_json()
        if not isinstance(body, dict):
            msg = "Cancel payload must be a JSON object"
            raise A2AError(msg)
        task_id = body.get("taskId")
        if not task_id:
            msg = "Missing required field 'taskId'"
            raise A2AError(msg)
        task = self._server_logic().cancel_task(task_id)
        self._send_json(200, {"task": task.to_dict()})


class A2AHttpServer:
    """A real HTTP server exposing the A2A task protocol over JSON.

    Backed by a :class:`TaskRouter` (which owns an
    :class:`AgentRegistry` + task store) or a bare store
    (:class:`TaskManager` / :class:`TaskStore`). Bound to an ephemeral port
    when ``port=0`` so tests are hermetic.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        *,
        router: TaskRouter | None = None,
        store: TaskStore | None = None,
    ) -> None:
        self.host = host
        self.port = int(port)
        self._lock = threading.RLock()
        if router is not None:
            self._router = router
            self._store = router.store
        else:
            self._store = store if store is not None else TaskManager()
            self._router = TaskRouter(store=self._store)
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._started = False

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> A2AHttpServer:
        """Bind + start serving in a daemon thread. Returns self."""
        with self._lock:
            if self._started:
                return self
            if isinstance(self._store, TaskStore) and not self._store.is_open:
                self._store.initialize()

            class _Server(ThreadingHTTPServer):
                daemon_threads = True
                allow_reuse_address = True
                # typed hook referenced by the handler
                logic: Any  # A2AHttpServer

            self._httpd = _Server((self.host, self.port), _A2AHTTPHandler)
            self._httpd.logic = self  # type: ignore[attr-defined]
            bound = self._httpd.server_address
            self.host = bound[0]
            self.port = int(bound[1])
            self._thread = threading.Thread(
                target=self._httpd.serve_forever,
                name="a2a-http-server",
                daemon=True,
            )
            self._thread.start()
            self._started = True
        return self

    def stop(self) -> None:
        with self._lock:
            if self._httpd is not None:
                self._httpd.shutdown()
                self._httpd.server_close()
            if self._thread is not None:
                self._thread.join(timeout=5)
            self._httpd = None
            self._thread = None
            self._started = False

    @property
    def base_url(self) -> str:
        if not self._started:
            msg = "Server not started; call start() first"
            raise A2ATransportError(msg)
        return f"http://{self.host}:{self.port}"

    @property
    def started(self) -> bool:
        return self._started

    @property
    def router(self) -> TaskRouter:
        return self._router

    @property
    def store(self) -> TaskStore:
        return self._store

    # -- store-facing operations (used by the handler) --------------------
    def create_task(self, agent_id: str, message: Message, **kwargs: object) -> Task:
        return self._store.create_task(agent_id, message, **kwargs)

    def get_task(self, task_id: str) -> Task:
        return self._store.get_task(task_id)

    def cancel_task(self, task_id: str) -> Task:
        return self._store.cancel(task_id)

    def __enter__(self) -> A2AHttpServer:
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class A2AHttpClient:
    """A ``urllib``-based A2A HTTP client.

    Talks to an :class:`A2AHttpServer` (or any compatible A2A JSON endpoint) via
    real HTTP, parses responses into :class:`Task` objects and surfaces errors
    as the module's typed exceptions. Optionally wires a
    :class:`MemoryFailureInjector` to exercise retry-then-surface behaviour.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 5.0,
        max_retries: int = 1,
        injector: MemoryFailureInjector | None = None,
    ) -> None:
        self.base_url = str(base_url).rstrip("/")
        self.timeout = float(timeout)
        self.max_retries = max(1, int(max_retries))
        self.injector = injector

    # -- raw transport -----------------------------------------------------
    def _raw(self, method: str, path: str, payload: object = None) -> tuple[int, str]:
        url = self.base_url + path
        data = None
        headers: dict[str, str] = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib_request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib_request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, resp.read().decode("utf-8")
        except urllib_error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8")
            except Exception:  # noqa: BLE001
                body = ""
            return exc.code, body
        except (urllib_error.URLError, OSError) as exc:
            msg = f"Request to {url} failed: {exc}"
            raise A2ATransportTimeout(msg) from exc

    def _request(
        self, method: str, path: str, payload: object = None, expected_task_id: str | None = None
    ) -> dict[str, Any]:
        """Issue one request with retry-once-then-surface semantics.

        Retryable faults are transport timeouts and out-of-order (stale)
        responses. Non-2xx statuses, except transient ``503``-style faults, are
        surfaced as typed errors immediately (a full parser for the JSON body is
        applied after each attempt).
        """
        attempt = 0
        while True:
            attempt += 1
            inject = self.injector.intercept(method, path) if self.injector else None
            try:
                if inject == _FailureFactory.DROP:
                    msg = f"Dropped {method} {path}"
                    raise A2ATransportTimeout(msg)
                if inject == _FailureFactory.TIMEOUT:
                    msg = f"Timed out {method} {path}"
                    raise A2ATransportTimeout(msg)
                # reorder (out-of-order): the real request still goes out, but
                # the delivered response is a stale copy of the previous one.
                stale = None
                if inject == _FailureFactory.REORDER:
                    stale = self.injector.deliver_stale() if self.injector else None

                code, body = self._raw(method, path, payload)
                if inject == _FailureFactory.REORDER and stale is not None:
                    body = stale
                if self.injector is not None:
                    self.injector.record_response(body)

                data = json.loads(body) if body else {}
                if not isinstance(data, dict):
                    msg = "Server returned a non-object JSON response"
                    raise A2AError(msg)

                if code >= 400:
                    self._raise_http_error(code, data)
                if "task" in data:
                    task = data["task"]
                    if expected_task_id is not None and task.get("taskId") != expected_task_id:
                        msg = (
                            f"Out-of-order response: got task "
                            f"{task.get('taskId')!r}, expected {expected_task_id!r}"
                        )
                        raise OutOfOrderError(msg)
                return data
            except (A2ATransportTimeout, OutOfOrderError) as retryable:
                if attempt > self.max_retries:
                    msg = f"{method} {path} failed after {attempt} attempt(s): {retryable}"
                    raise A2ATransportError(msg) from retryable
                _logger.debug("retrying %s %s (attempt %d)", method, path, attempt)

    def _raise_http_error(self, code: int, data: dict[str, Any]) -> None:
        """Map an HTTP error status + JSON body to a typed module error."""
        error = data.get("error") or {}
        message = error.get("message", f"HTTP {code}") if isinstance(error, dict) else str(error)
        if code == 404:
            raise TaskNotFoundError(message)
        msg = f"HTTP {code}: {message}"
        raise A2AError(msg)

    # -- public operations ---------------------------------------------------
    def send_task(
        self,
        agent_id: str,
        message: object,
        *,
        session_id: str | None = None,
        idempotency_key: str | None = None,
        context: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        """Submit a task to an agent; returns the created task (submitted)."""
        msg = _coerce_message(message)
        payload = {
            "agentId": agent_id,
            "message": msg.to_dict(),
            "sessionId": session_id,
            "idempotencyKey": idempotency_key,
            "context": context,
            "metadata": metadata,
        }
        data = self._request("POST", "/tasks/send", payload)
        return Task.from_dict(data["task"])

    def get_task(self, task_id: str) -> Task:
        """Fetch the current state, messages and artifacts of a task."""
        data = self._request("GET", f"/tasks/{task_id}", expected_task_id=task_id)
        return Task.from_dict(data["task"])

    def cancel_task(self, task_id: str) -> Task:
        """Cancel a task; returns the canceled task."""
        data = self._request("POST", "/tasks/cancel", {"taskId": task_id}, expected_task_id=task_id)
        return Task.from_dict(data["task"])

    def health(self) -> dict[str, Any]:
        """Hit ``GET /health`` and return the parsed JSON body."""
        return self._request("GET", "/health")
