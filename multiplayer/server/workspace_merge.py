"""Workspace merge engine.

Given a canonical workspace directory and a client's returned artifacts, apply
them back into the workspace. For v1 we accept whole-file artifact writes and
record a human-readable .MERGE ledger line.

Conflict handling
-----------------
A *3-way conflict* is detected when an artifact targets a file that already
exists in the canonical workspace with different content than the artifact
intends to write. In that case we DO NOT clobber the existing file, emit a
"resolver event" (recorded in the returned events list and dropped into the
.MERGE file as a CONFLICT line), and skip the write.

Git gate
--------
When the canonical directory is a git repository (a `.git` entry exists), we run
``git status --porcelain`` before and after applying and record both snapshots in
the result so coordinators can audit what changed.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import time
from typing import Any, Dict, List, Optional

MERGE_HEADER = "# multiplayer workspace merge ledger\n"


def _safe_join(canonical_dir: str, rel_path: str) -> Optional[str]:
    """Join a canonical dir to a relative artifact path, guarding traversal."""
    if rel_path.startswith("/") or ".." in rel_path.split("/"):
        return None
    return os.path.join(canonical_dir, rel_path)


def git_status(canonical_dir: str, timeout: float = 10.0) -> List[str]:
    """Return `git status --porcelain` output, or [] if not a git repo/available."""
    if not os.path.isdir(os.path.join(canonical_dir, ".git")):
        return []
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=canonical_dir, capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            return []
        return [ln for ln in proc.stdout.splitlines() if ln.strip()]
    except (OSError, subprocess.TimeoutExpired):  # pragma: no cover - best effort
        return []


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def apply_artifacts(canonical_dir: str,
                    artifacts: List[Dict[str, str]],
                    ledger_path: Optional[str] = None,
                    task_id: str = "",
                    client_id: str = "") -> Dict[str, Any]:
    """Apply client artifacts into the canonical workspace.

    Parameters
    ----------
    canonical_dir : existing directory to receive artifacts.
    artifacts     : list of {"path": str, "content": str}.
    ledger_path   : where to append the .MERGE ledger (defaults to
                    <canonical_dir>/.MERGE).
    task_id, client_id : attribution strings for the ledger.

    Returns a result dict:
        {
          "applied":  [relative paths written],
          "skipped":  [relative paths identical to existing],
          "conflicts": [{"path", "reason", "existing_hash", "incoming_hash"}],
          "events":   ["resolver event strings"],
          "git_before": [...], "git_after": [...],
          "workspace": canonical_dir,
        }
    """
    os.makedirs(canonical_dir, exist_ok=True)
    ledger_path = ledger_path or os.path.join(canonical_dir, ".MERGE")

    git_before = git_status(canonical_dir)
    applied: List[str] = []
    skipped: List[str] = []
    conflicts: List[Dict[str, str]] = []
    events: List[str] = []
    incoming: List[str] = []

    if not os.path.exists(ledger_path):
        with open(ledger_path, "a", encoding="utf-8") as fh:
            fh.write(MERGE_HEADER)

    for art in artifacts or []:
        rel = art.get("path") or ""
        content = art.get("content") or ""
        target = _safe_join(canonical_dir, rel)
        if target is None:
            conflicts.append({"path": rel,
                              "reason": "unsafe path (traversal or absolute)",
                              "existing_hash": "", "incoming_hash": ""})
            events.append(f"resolver: conflict on {rel}: unsafe path rejected")
            continue
        incoming.append(rel)
        os.makedirs(os.path.dirname(target) or canonical_dir, exist_ok=True)
        if os.path.exists(target):
            with open(target, "rb") as fh:
                existing = fh.read()
            if _hash(existing) == _hash(content.encode("utf-8")):
                skipped.append(rel)
                continue
            # 3-way conflict: target already differs from the incoming content.
            conflicts.append({"path": rel,
                              "reason": "existing file differs from incoming content",
                              "existing_hash": _hash(existing),
                              "incoming_hash": _hash(content.encode("utf-8"))})
            events.append(f"resolver: conflict on {rel}: NOT clobbered")
            continue
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(content)
        applied.append(rel)

    git_after = git_status(canonical_dir)

    # Append to the .MERGE ledger.
    ts = time.time()
    with open(ledger_path, "a", encoding="utf-8") as fh:
        if conflicts:
            for c in conflicts:
                fh.write(
                    f"[{ts:.3f}] CONFLICT task={task_id or '-'} client={client_id or '-'} "
                    f"path={c['path']} reason={c['reason']}\n")
        elif incoming:
            fh.write(
                f"[{ts:.3f}] APPLIED task={task_id or '-'} client={client_id or '-'} "
                f"applied={','.join(applied)} skipped={','.join(skipped)} "
                f"conflicts={len(conflicts)}\n")

    return {
        "applied": applied,
        "skipped": skipped,
        "conflicts": conflicts,
        "events": events,
        "git_before": git_before,
        "git_after": git_after,
        "workspace": canonical_dir,
    }


def read_merge_ledger(ledger_path: str, limit: int = 50) -> List[str]:
    """Return the most recent `limit` lines of a .MERGE ledger (for the API)."""
    if not os.path.exists(ledger_path):
        return []
    with open(ledger_path, "r", encoding="utf-8") as fh:
        lines = [ln.rstrip("\n") for ln in fh if ln.strip()]
    return lines[-limit:]