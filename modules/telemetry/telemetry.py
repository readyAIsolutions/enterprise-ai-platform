"""ENI Enterprise Build Telemetry recorder.

Lightweight, stdlib-only JSONL append-only log of *module usage* as builds happen.
The enterprise drop-in plugin calls ``record(...)`` from its hooks so the GUI can
show, per project/session, WHICH enterprise modules were engaged, on WHICH hook,
for WHICH tool step, and WHY (the module's real purpose).

Pure stdlib, fail-open: any error is swallowed — telemetry must never break a build.
"""
# ruff: noqa: PTH123  # stdlib-only JSONL writer stays on open() for portability
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

# Default store: under the enterprise repo data dir, next to build_sessions.
_default = os.environ.get(
    "ENI_TELEMETRY_FILE",
    str(
        Path(__file__).resolve().parent.parent.parent
        / "data" / "build_sessions" / "module_usage.jsonl"
    ),
)
_STORE = Path(_default)

# Current session/project being built, set by the plugin's on_session_start.
CURRENT_SESSION = ""
CURRENT_GOAL = ""


def set_context(session_id: str = "", goal: str = "") -> None:
    global CURRENT_SESSION, CURRENT_GOAL
    if session_id:
        CURRENT_SESSION = str(session_id)
    if goal:
        CURRENT_GOAL = str(goal)


def record(
    module: str,
    hook: str,
    tool: str = "",
    why: str = "",
    detail: str = "",
    session: str = "",
    goal: str = "",
) -> None:
    """Append one telemetry row (module used at a build step). Fail-open."""
    try:
        row = {
            "ts": time.time(),
            "id": uuid.uuid4().hex[:10],
            "session": session or CURRENT_SESSION,
            "goal": goal or CURRENT_GOAL,
            "module": module,
            "hook": hook,
            "tool": tool,
            "why": why,
            "detail": detail[:500],
        }
        _STORE.parent.mkdir(parents=True, exist_ok=True)
        with open(_STORE, "a") as fh:
            fh.write(json.dumps(row) + "\n")
    except Exception:
        pass


# --------------------------------------------------------------------------- read side
def read_all() -> list[dict]:
    """Read all telemetry rows (newest-last). Fail-open to [] ."""
    if not _STORE.exists():
        return []
    out = []
    try:
        for line in _STORE.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        pass
    return out


def sessions() -> list[str]:
    """Unique session ids seen in telemetry, newest-first."""
    seen = {}
    for r in read_all():
        seen[r.get("session") or "?"] = r.get("goal") or ""
    return sorted(seen, key=lambda s: s, reverse=True)
