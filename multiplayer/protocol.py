"""Multiplayer wire protocol.

Defines the JSON message schemas exchanged between coordination clients and the
multiplayer server, a `make_message` factory that builds validated message dicts,
and a `validate(message)` function used to vet incoming/outgoing messages.

Message types
-------------
    hello      client -> server   machine profile + capabilities
    welcome    server -> client   server identity + schedule
    task       server -> client   a unit of work to execute
    work_start client -> server   worker picked the task up
    work_log   client -> server   incremental stdout/log line from the worker
    artifact   client -> server   a file the worker produced (streamed back)
    work_result client -> server  final outcome of a task (success / failure)
    heartbeat  client -> server   liveness + running-task load snapshot
    ack        server -> client   acknowledgement of a submitted message
    requeue    server -> client   task was put back in the queue (state change)
    error      both              structured error notification

Task lifecycle (state machine)
------------------------------
    QUEUED -> ASSIGNED -> RUNNING -> COMPLETED | FAILED(retry once)
    FAILED with attempt counter 1 is re-inserted as QUEUED (requeue). A second
    FAILED (attempt 2) is terminal.

Every message is an ascii-safe JSON object. No binary channels are used. Client
code MUST NOT transmit secrets/API keys over these messages.
"""

from __future__ import annotations

import json
import time
from enum import Enum
from typing import Any, Dict, List, Optional

PROTOCOL_VERSION = 1

# State machine for task lifecycle.
class TaskState(str, Enum):
    QUEUED = "QUEUED"
    ASSIGNED = "ASSIGNED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

# Terminal + transitional states.
TERMINAL_STATES = (TaskState.COMPLETED, TaskState.FAILED)

# All valid transitions keyed by (current_state).
_ALLOWED_TRANSITIONS = {
    TaskState.QUEUED: {TaskState.ASSIGNED, TaskState.FAILED},
    TaskState.ASSIGNED: {TaskState.RUNNING, TaskState.QUEUED, TaskState.FAILED},
    TaskState.RUNNING: {TaskState.COMPLETED, TaskState.FAILED, TaskState.QUEUED},
    TaskState.COMPLETED: set(),
    TaskState.FAILED: {TaskState.QUEUED},  # one retry is allowed
}


# ---------------------------------------------------------------------------
# Schema definitions.
#
# Each entry lists REQUIRED keys and an OPTIONAL set. `validate` verifies the
# required set is present, every value has the documented type, and no encoding
# rule (e.g. no secrets) is violated.
# ---------------------------------------------------------------------------

_CAPABILITIES = {
    "max_concurrent_tasks": int,
    "models": list,
    "providers": list,
    "tags": list,
    "gpu": (bool, type(None)),
}

_MACHINE = {
    "cpus": (int, type(None)),
    "ram_gb": (float, int, type(None)),
    "gpu_name": (str, type(None)),
    "hostname": (str, type(None)),
}

SCHEMAS: Dict[str, Dict[str, Any]] = {
    "hello": {
        "required": {
            "type": str,
            "client_id": str,
            "capabilities": dict,
            "machine": dict,
        },
        "optional": set(),
    },
    "welcome": {
        "required": {
            "type": str,
            "server_id": str,
            "server_version": int,
        },
        "optional": {
            "assigned_client_id",
            "schedule",
            "note",
        },
    },
    "task": {
        "required": {
            "type": str,
            "task_id": str,
            "goal": str,
        },
        "optional": {
            "status",
            "repo",
            "prompt",
            "artifacts",
            "model_hint",
            "provider",
            "tags",
            "requeue_of",
            "attempt",
            "priority",
        },
    },
    "work_start": {
        "required": {"type": str, "task_id": str},
        "optional": {"started_at"},
    },
    "work_log": {
        "required": {"type": str, "task_id": str, "message": str},
        "optional": {"seq", "ts", "level"},
    },
    "artifact": {
        "required": {"type": str, "task_id": str, "path": str, "content": str},
        "optional": {"merge_mode"},
    },
    "work_result": {
        "required": {"type": str, "task_id": str, "status": str},
        "optional": {
            "summary",
            "stdout",
            "stderr",
            "exit_code",
            "duration",
            "artifacts",
            "diff",
            "error",
        },
    },
    "heartbeat": {
        "required": {"type": str, "client_id": str, "ts": (int, float)},
        "optional": {"running", "load"},
    },
    "ack": {
        "required": {"type": str, "task_id": str, "ok": bool},
        "optional": {"note"},
    },
    "requeue": {
        "required": {"type": str, "task_id": str, "reason": str},
        "optional": {"attempt"},
    },
    "error": {
        "required": {"type": str, "message": str},
        "optional": {"code", "task_id"},
    },
}

_VALID_RESULT_STATUS = {"completed", "failed"}


def _type_ok(value: Any, expected) -> bool:
    """Check a value against a type or tuple of types from a schema."""
    if expected is None:
        return value is None
    if isinstance(expected, tuple):
        return any(_type_ok(value, e) for e in expected)
    if expected is list:  # element type; treat as any list
        return isinstance(value, list)
    if expected is dict:  # any mapping
        return isinstance(value, dict)
    return isinstance(value, expected)


def validate(message: Any):
    """Validate a message dict; return (is_valid, error_reason_or_None).

    Returns a tuple ``(ok, reason)`` where ``ok`` is True/False. When valid,
    ``reason`` is None; otherwise it is a human-readable string describing the
    first rule that failed.
    """
    if not isinstance(message, dict):
        return False, "message must be a dict"
    mtype = message.get("type")
    if mtype not in SCHEMAS:
        return False, f"unknown message type: {mtype!r}"

    schema = SCHEMAS[mtype]
    for key, expected in schema["required"].items():
        if key == "type":
            continue
        if key not in message:
            return False, f"missing required field '{key}' for type {mtype}"
        if not _type_ok(message[key], expected):
            return False, f"field '{key}' has wrong type: {type(message[key]).__name__}"

    for key, expected in (schema["optional"].items()
                          if isinstance(schema["optional"], dict) else ()):
        if key in message:
            if not _type_ok(message[key], expected):
                return False, f"optional field '{key}' has wrong type"

    # Type-specific cross-field rules.
    if mtype == "hello":
        caps = message.get("capabilities") or {}
        mc = caps.get("max_concurrent_tasks")
        if mc is not None and (not isinstance(mc, int) or mc < 1):
            return False, "capabilities.max_concurrent_tasks must be a positive int"
    if mtype == "work_result":
        if message["status"] not in _VALID_RESULT_STATUS:
            return False, "work_result.status must be 'completed' or 'failed'"
    if mtype == "artifact":
        path = message.get("path") or ""
        if not path or ".." in path or path.startswith("/"):
            return False, "artifact.path must be a relative safe path"
    if mtype == "task":
        artifacts = message.get("artifacts") or []
        if not isinstance(artifacts, list):
            return False, "task.artifacts must be a list"

    # Anti-secret guard: refuse common credential keywords in payload fields.
    _guarded_fields = ("prompt", "content", "summary", "stdout", "message")
    _secret_keywords = ("api_key", "apikey", "secret", "authorization", "bearer ",
                        "password", "token=")
    for field in _guarded_fields:
        val = str(message.get(field, "")).lower()
        if any(k in val for k in _secret_keywords):
            return False, f"refusing message: field '{field}' may contain a secret"

    return True, None


def check(message: Any) -> None:
    """Like validate() but raises ValueError on invalid input."""
    ok, reason = validate(message)
    if not ok:
        raise ValueError(f"invalid protocol message: {reason}")


def make_message(mtype: str, **fields) -> Dict[str, Any]:
    """Build a validated message dict of the given type.

    Raises ValueError if the resulting message fails validation.
    """
    message: Dict[str, Any] = {"type": mtype}
    for k, v in fields.items():
        message[k] = v
    check(message)
    return message


def now() -> float:
    """Monotonic-free wall clock used by timestamps across protocol messages."""
    return time.time()


def encode(message: Dict[str, Any]) -> bytes:
    """Serialize a validated protocol message to utf-8 JSON bytes."""
    check(message)
    return json.dumps(message, separators=(",", ":")).encode("utf-8")


def decode(data: Any) -> Dict[str, Any]:
    """Decode bytes or str into a validated protocol message dict."""
    if isinstance(data, (bytes, bytearray)):
        data = bytes(data).decode("utf-8")
    message = json.loads(data)
    check(message)
    return message