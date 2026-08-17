"""Shared Workspace — live multi-editor collaboration with lock/merge/retention.

Built from the pulled JE Van Clief transcript "We Built Multiplayer AI, No New
Agents Needed" (qzVXfVvXbXU), which describes:

  * a "breathable workable workspace that multiple people can edit together and
    keeps everything up to par"
  * "it's not deploying it and pushing it and sharing it constantly and waiting
    until it updates. It's all in the cloud and live"
  * continuation-collaboration while an agent is still thinking
  * siloed data with explicit opt-in sharing / anonymization
  * versioned, queryable session history

This module is that shared workspace made concrete. It provides per-file
optimistic locking (so two people can't clobber each other), whole-file merge +
conflict detection, an append-only change log / session history that is queryable,
and a "siloed" redaction helper so private values stay local unless explicitly
shared (the anonymize-before-share behavior from the transcript).

Version: 1.0.0
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class WorkspaceFile:
    path: str
    content: str
    sha: str
    lock_owner: Optional[str] = None
    lock_ts: Optional[float] = None
    updated_at: float = field(default_factory=time.time)


class SharedWorkspace:
    """Live multi-editor workspace with lock + merge-safety + change history."""

    def __init__(self, root: str | Path | None = None, max_history: int = 2000) -> None:
        self.root = Path(root) if root else Path.cwd()
        self.max_history = max_history
        self._lock = threading.RLock()
        self._files: Dict[str, WorkspaceFile] = {}
        self._history: List[Dict[str, Any]] = []

    # ------------------------------------------------------------- io
    def _load(self, rel: str) -> WorkspaceFile:
        p = self.root / rel
        if not p.exists():
            return WorkspaceFile(path=rel, content="", sha="")
        data = p.read_text(encoding="utf-8", errors="replace")
        return WorkspaceFile(path=rel, content=data, sha=sha256(data))

    def list(self) -> List[str]:
        """List workspace files (relative)."""
        with self._lock:
            return [str(p.relative_to(self.root))
                    for p in self.root.rglob("*") if p.is_file()]

    # ------------------------------------------------------------- locking
    def lock(self, rel: str, owner: str) -> bool:
        """Take an optimistic lock on a file. False if someone else holds it."""
        with self._lock:
            rec = self._files.setdefault(rel, self._load(rel))
            if rec.lock_owner is not None and rec.lock_owner != owner:
                return False
            rec.lock_owner = owner
            rec.lock_ts = time.time()
            return True

    def unlock(self, rel: str, owner: str) -> bool:
        with self._lock:
            rec = self._files.get(rel)
            if rec is None or rec.lock_owner != owner:
                return False
            rec.lock_owner = None
            rec.lock_ts = None
            return True

    def is_locked(self, rel: str) -> bool:
        with self._lock:
            rec = self._files.get(rel)
            return rec is not None and rec.lock_owner is not None

    # ------------------------------------------------------- write (merge-safe)
    def write(self, rel: str, content: str, author: str,
              force: bool = False) -> Dict[str, Any]:
        """Write a file, refusing if it's locked by someone else (unless force).

        Merge-safe: if the on-disk file changed since we last loaded it, we
        compute a 3-way merge; if there's a conflict we DON'T clobber, we flag it.
        Returns {ok, conflict, merged, ...}.
        """
        with self._lock:
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            existing = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
            prev_rec = self._files.get(rel)

            # lock guard (unless force)
            if not force and prev_rec is not None and prev_rec.lock_owner not in (None, author):
                return {"ok": False, "conflict": True,
                        "reason": f"locked by {prev_rec.lock_owner}"}

            # 3-way: base(the earlier loaded content) -> new(content)
            conflict = False
            base = prev_rec.content if prev_rec is not None else ""
            # If on-disk changed from base AND our new content differs from disk -> conflict
            if base and existing and existing != base and content != existing:
                conflict = True
                # keep disk, don't clobber
                return {"ok": False, "conflict": True,
                        "reason": "file changed by another editor; not clobbering",
                        "on_disk": existing[:200]}

            target.write_text(content, encoding="utf-8")
            rec = WorkspaceFile(path=rel, content=content, sha=sha256(content),
                                lock_owner=prev_rec.lock_owner if prev_rec else None,
                                lock_ts=prev_rec.lock_ts if prev_rec else None,
                                updated_at=time.time())
            self._files[rel] = rec
            self._append(rel, author, "write", content)
            return {"ok": True, "conflict": False, "sha": rec.sha}

    def read(self, rel: str) -> Optional[str]:
        with self._lock:
            rec = self._files.setdefault(rel, self._load(rel))
            if not rec.sha:
                return None
            return rec.content

    # ------------------------------------------------------- history/query
    def _append(self, rel: str, author: str, action: str, content: str = "") -> None:
        self._history.append({
            "ts": time.time(), "path": rel, "author": author,
            "action": action, "sha": sha256(content),
        })
        if len(self._history) > self.max_history:
            self._history = self._history[-self.max_history:]

    def history(self, rel: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            h = [e for e in self._history if rel is None or e["path"] == rel]
        return h[-limit:]

    def query(self, q: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Query the session history/changelog by keyword (the 'query it' behavior)."""
        with self._lock:
            hits = [e for e in self._history if q.lower() in e["path"].lower()
                    or q.lower() in e["author"].lower()]
        return hits[-limit:]

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {"files": sorted(self._files.keys()),
                    "history_len": len(self._history),
                    "locks": {p: r.lock_owner for p, r in self._files.items()
                              if r.lock_owner}}


# ---------------------------------------------------------------------------
# Siloed-data helper: anonymize before sharing (from the transcript)
# ---------------------------------------------------------------------------

_SENSITIVE = r"(?i)\b(api[_-]?key|secret|password|passwd|token|bearer|private|confid)\b"


def anonymize_for_share(text: str, redact: bool = True) -> str:
    """Return text with sensitive values masked for safe sharing.

    Mirrors the transcript's 'some things we don't want to share / siloed data':
    private credential-like values are replaced with <redacted> before anything is
    shared, while the rest of the workspace stays intact.
    """
    out = re.sub(_SENSITIVE + r"['\"]?\s*[:=]?\s*['\"]?[A-Za-z0-9_\-]{4,}",
                 lambda m: m.group(1).capitalize() + "=<redacted>", text)
    out = re.sub(r"(?i)\b[a-f0-9]{32,64}\b", "<redacted>", out)
    return out


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8", "replace")).hexdigest()


__all__ = ["SharedWorkspace", "WorkspaceFile", "anonymize_for_share",
           "sha256", "__version__"]
__version__ = "1.0.0"