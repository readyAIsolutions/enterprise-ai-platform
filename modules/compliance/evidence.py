#!/usr/bin/env python3
"""
Enterprise Compliance - Live Evidence Register & Gap Analysis
=============================================================
Adds a *live, evidence-based* control assessment layer on top of the static
control catalogue (OWASP LLM Top 10 / NIST AI RMF / MITRE ATLAS).

The static module (``compliance.compliance``) maps controls to a hand-supplied
posture map. This module instead derives posture from **real evidence**:

* :class:`ControlEvidence` - a single, hashable item of audit evidence tying a
  control to a status (implemented / partial / missing) via a source + detail.
* :class:`EvidenceRegister` - an SQLite-backed store (stdlib ``sqlite3``) with
  dedupe on ``(control_id, source)`` and a **tamper-evident SHA-256 hash
  chain** so audit history cannot be silently altered.
* :class:`GapAnalysis` - computes per-framework pass %, lists the missing /
  partial controls, a 0-100 score per framework, and a top-N remediation list.
* :func:`assess` / :func:`ingest` - convenient facades that wire a register to
  the built-in catalogue for quick, real gap reports.

Stdlib-only: ``sqlite3``, ``hashlib``, ``dataclasses``, ``datetime``.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .compliance import (
    BUILTIN_CONTROLS,
    FRAMEWORK_MITRE,
    FRAMEWORK_NIST,
    FRAMEWORK_OWASP,
    STATUS_IMPLEMENTED,
    STATUS_MISSING,
    STATUS_PARTIAL,
    Control,
    controls_for_framework,
)

if TYPE_CHECKING:
    import builtins

logger = logging.getLogger("enterprise.compliance.evidence")

# Evidence granularity is a subset of the full control status vocabulary.
EVIDENCE_STATUSES = frozenset({STATUS_IMPLEMENTED, STATUS_PARTIAL, STATUS_MISSING})

_DEFAULT_FRAMEWORKS = (FRAMEWORK_OWASP, FRAMEWORK_NIST, FRAMEWORK_MITRE)


def _now() -> str:
    """UTC ISO-8601 timestamp with microsecond resolution."""
    return datetime.now(UTC).isoformat()


def _content_hash(**fields: Any) -> str:
    """Canonical SHA-256 over the evidence content fields."""
    canonical = "|".join(
        str(fields.get(k, ""))
        for k in ("control_id", "framework", "status", "source", "detail", "timestamp")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# =============================================================================
# ControlEvidence
# =============================================================================


@dataclass
class ControlEvidence:
    """A single item of audit evidence for a control.

    Attributes:
        control_id:   Control identifier from the catalogue (e.g. ``LLM01``).
        framework:    Owning framework (``owasp`` | ``nist`` | ``mitre``).
        status:       Evidenced posture - ``implemented`` | ``partial`` | ``missing``.
        source:       Where the evidence came from (scanner, audit, test name, tool).
        detail:       Free-form evidence detail / supporting note.
        timestamp:    ISO-8601 timestamp of when the evidence was collected.
        evidence_hash: SHA-256 fingerprint of this evidence's content.
    """

    control_id: str
    framework: str
    status: str
    source: str = "manual"
    detail: str = ""
    timestamp: str = field(default_factory=_now)
    evidence_hash: str = ""

    def __post_init__(self) -> None:
        self.framework = str(self.framework).lower()
        self.status = str(self.status).lower()
        if self.status not in EVIDENCE_STATUSES:
            msg = (
                f"Invalid evidence status {self.status!r}; expected one of "
                f"{sorted(EVIDENCE_STATUSES)}"
            )
            raise ValueError(msg)
        if not self.control_id or not str(self.control_id).strip():
            msg = "control_id is required for evidence"
            raise ValueError(msg)
        if not self.evidence_hash:
            self.evidence_hash = _content_hash(
                control_id=self.control_id,
                framework=self.framework,
                status=self.status,
                source=self.source,
                detail=self.detail,
                timestamp=self.timestamp,
            )

    def recompute_hash(self) -> str:
        """Recompute the SHA-256 fingerprint from the current content."""
        return _content_hash(
            control_id=self.control_id,
            framework=self.framework,
            status=self.status,
            source=self.source,
            detail=self.detail,
            timestamp=self.timestamp,
        )

    @property
    def is_implemented(self) -> bool:
        return self.status == STATUS_IMPLEMENTED

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ControlEvidence:
        data = dict(raw)
        hash_ = data.pop("evidence_hash", "")
        ev = cls(**data)
        if hash_:
            ev.evidence_hash = hash_
        return ev


# =============================================================================
# EvidenceRegister (SQLite + tamper-evident hash chain)
# =============================================================================


class EvidenceRegister:
    """SQLite-backed register of :class:`ControlEvidence` items.

    * Dedupes by ``(control_id, source)`` - re-adding the same key updates the
      record in place rather than creating a duplicate row.
    * Maintains a SHA-256 **hash chain** across rows in insertion order so that
      any out-of-band modification (editing a row, deleting a row, reordering)
      is detectable via :meth:`verify_integrity`.
    * ``db_path=None`` uses an in-memory database; otherwise evidence is
      persisted to an SQLite file (e.g. ``data/compliance_evidence.db``).
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._path: str | None = None
        if db_path is None:
            self._conn = sqlite3.connect(":memory:")
            logger.debug("EvidenceRegister using in-memory database")
        else:
            p = Path(str(db_path))
            if str(db_path).endswith(("/", "\\")) or p.is_dir() or p.suffix == "":
                # Treat bare path (e.g. "data/") as a directory holding the db.
                p.mkdir(parents=True, exist_ok=True)
                p = p / "compliance_evidence.db"
            self._path = str(p)
            if p.parent != Path():
                p.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self._path)
            logger.debug("EvidenceRegister using SQLite file %s", self._path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        self.rebuild_chain()
        self._conn.commit()

    # -- schema -------------------------------------------------------------

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS evidence (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                control_id    TEXT NOT NULL,
                framework     TEXT NOT NULL,
                status        TEXT NOT NULL,
                source        TEXT NOT NULL,
                detail        TEXT NOT NULL DEFAULT '',
                timestamp     TEXT NOT NULL,
                content_hash  TEXT NOT NULL,
                chain_hash    TEXT NOT NULL,
                prev_id       INTEGER
            )
            """
        )
        # Dedupe key: one row per (control_id, source).
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_evidence_dedupe ON evidence(control_id, source)"
        )
        cur.execute("CREATE INDEX IF NOT EXISTS ix_evidence_framework ON evidence(framework)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_evidence_status ON evidence(status)")
        self._conn.commit()

    # -- internal chain management ------------------------------------------

    def rebuild_chain(self) -> None:
        """Rebuild the tamper-evident hash chain across all rows by id order."""
        cur = self._conn.cursor()
        rows = cur.execute("SELECT id, content_hash FROM evidence ORDER BY id").fetchall()
        prev_hash = ""
        prev_id = None
        for row in rows:
            content_h = row["content_hash"]
            chain_h = hashlib.sha256((prev_hash + content_h).encode("utf-8")).hexdigest()
            cur.execute(
                "UPDATE evidence SET chain_hash = ?, prev_id = ? WHERE id = ?",
                (chain_h, prev_id, row["id"]),
            )
            prev_hash = chain_h
            prev_id = row["id"]
        self._conn.commit()

    # -- mutation -----------------------------------------------------------

    def add(self, item: ControlEvidence | dict[str, Any]) -> int:
        """Add or update evidence, deduping on ``(control_id, source)``.

        Returns the SQLite row id. If a record with the same control_id and
        source already exists, its status/detail/timestamp are updated in
        place (its hash is refreshed) and the chain is rebuilt.
        """
        ev = item if isinstance(item, ControlEvidence) else ControlEvidence.from_dict(item)
        if ev.framework not in _DEFAULT_FRAMEWORKS:
            logger.warning(
                "Evidence for %r uses unregistered framework %r",
                ev.control_id,
                ev.framework,
            )
        content_h = ev.recompute_hash()
        cur = self._conn.cursor()
        existing = cur.execute(
            "SELECT id FROM evidence WHERE control_id = ? AND source = ?",
            (ev.control_id, ev.source),
        ).fetchone()
        if existing is not None:
            row_id = existing["id"]
            cur.execute(
                """UPDATE evidence SET framework = ?, status = ?, detail = ?,
                   timestamp = ?, content_hash = ? WHERE id = ?""",
                (ev.framework, ev.status, ev.detail, ev.timestamp, content_h, row_id),
            )
            logger.debug(
                "Updated evidence for (control=%s, source=%s) id=%s",
                ev.control_id,
                ev.source,
                row_id,
            )
        else:
            mid = hashlib.sha256(b"seed").hexdigest()  # placeholder, chain rebuilt below
            cur.execute(
                """INSERT INTO evidence
                   (control_id, framework, status, source, detail, timestamp,
                    content_hash, chain_hash, prev_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ev.control_id,
                    ev.framework,
                    ev.status,
                    ev.source,
                    ev.detail,
                    ev.timestamp,
                    content_h,
                    mid,
                    None,
                ),
            )
            row_id = cur.lastrowid
            if row_id is None:  # pragma: no cover - SQLite always assigns AUTOINCREMENT
                msg = "Failed to obtain last insert id"
                raise RuntimeError(msg)
            logger.debug(
                "Inserted evidence for (control=%s, source=%s) id=%s",
                ev.control_id,
                ev.source,
                row_id,
            )
        self.rebuild_chain()
        self._conn.commit()
        return row_id

    def update(
        self,
        control_id: str,
        source: str,
        *,
        status: str | None = None,
        detail: str | None = None,
        framework: str | None = None,
        timestamp: str | None = None,
    ) -> int | None:
        """Update an existing evidence record by its dedupe key."""
        existing = (
            self._conn.cursor()
            .execute(
                "SELECT * FROM evidence WHERE control_id = ? AND source = ?",
                (control_id, source),
            )
            .fetchone()
        )
        if existing is None:
            return None
        data = dict(existing)
        if status is not None:
            if status not in EVIDENCE_STATUSES:
                msg = f"Invalid status {status!r}"
                raise ValueError(msg)
            data["status"] = status
        if detail is not None:
            data["detail"] = detail
        if framework is not None:
            data["framework"] = str(framework).lower()
        if timestamp is not None:
            data["timestamp"] = timestamp
        ev = ControlEvidence(
            control_id=data["control_id"],
            framework=data["framework"],
            status=data["status"],
            source=data["source"],
            detail=data["detail"],
            timestamp=data["timestamp"],
        )
        return self.add(ev)

    def delete(self, control_id: str, source: str | None = None) -> int:
        """Delete evidence. With ``source=None`` deletes all rows for control."""
        cur = self._conn.cursor()
        if source is None:
            cur.execute("DELETE FROM evidence WHERE control_id = ?", (control_id,))
        else:
            cur.execute(
                "DELETE FROM evidence WHERE control_id = ? AND source = ?",
                (control_id, source),
            )
        n = cur.rowcount
        self.rebuild_chain()
        self._conn.commit()
        return n

    # -- query --------------------------------------------------------------

    def get(self, control_id: str, source: str | None = None) -> builtins.list[ControlEvidence]:
        """Return evidence rows for a control (optionally filtered by source)."""
        cur = self._conn.cursor()
        if source is None:
            rows = cur.execute(
                "SELECT * FROM evidence WHERE control_id = ? ORDER BY timestamp", (control_id,)
            ).fetchall()
        else:
            rows = cur.execute(
                "SELECT * FROM evidence WHERE control_id = ? AND source = ?",
                (control_id, source),
            ).fetchall()
        return [self._row_to_evidence(r) for r in rows]

    def latest(self, control_id: str) -> ControlEvidence | None:
        """Return the most recent evidence row for a control, or None."""
        cur = self._conn.cursor()
        row = cur.execute(
            "SELECT * FROM evidence WHERE control_id = ? ORDER BY timestamp DESC, id DESC LIMIT 1",
            (control_id,),
        ).fetchone()
        return self._row_to_evidence(row) if row else None

    def list(
        self,
        framework: str | None = None,
        control_id: str | None = None,
        status: str | None = None,
        source: str | None = None,
    ) -> builtins.list[ControlEvidence]:
        """List evidence, optionally filtered by framework / control / status / source."""
        clauses: list[str] = []
        params: list[Any] = []
        if framework is not None:
            clauses.append("framework = ?")
            params.append(str(framework).lower())
        if control_id is not None:
            clauses.append("control_id = ?")
            params.append(control_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(str(status).lower())
        if source is not None:
            clauses.append("source = ?")
            params.append(source)
        sql = "SELECT * FROM evidence"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY timestamp"
        rows = self._conn.cursor().execute(sql, params).fetchall()
        return [self._row_to_evidence(r) for r in rows]

    def search(self, query: str, framework: str | None = None) -> builtins.list[ControlEvidence]:
        """Full-text-ish search over control_id, source and detail."""
        pattern = f"%{query}%"
        clauses = ["(control_id LIKE ? OR source LIKE ? OR detail LIKE ?)"]
        params: list[Any] = [pattern, pattern, pattern]
        if framework is not None:
            clauses.append("framework = ?")
            params.append(str(framework).lower())
        rows = (
            self._conn.cursor()
            .execute(
                "SELECT * FROM evidence WHERE " + " AND ".join(clauses) + " ORDER BY timestamp",
                params,
            )
            .fetchall()
        )
        return [self._row_to_evidence(r) for r in rows]

    def count(self, framework: str | None = None) -> int:
        clauses, params = [], []
        if framework is not None:
            clauses.append("framework = ?")
            params.append(str(framework).lower())
        sql = "SELECT COUNT(*) AS n FROM evidence"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        return int(self._conn.cursor().execute(sql, params).fetchone()["n"])

    def clear(self) -> None:
        """Remove all evidence rows."""
        self._conn.cursor().execute("DELETE FROM evidence")
        self.rebuild_chain()
        self._conn.commit()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        try:
            self._conn.close()
        except sqlite3.Error:  # pragma: no cover - defensive
            pass

    # -- integrity ----------------------------------------------------------

    def verify_integrity(self) -> dict[str, Any]:
        """Verify the tamper-evident hash chain.

        Returns ``{"valid": bool, "checked": int, "problems": [str, ...]}``.
        A row is invalid if its stored ``content_hash`` no longer matches its
        content, or if its ``chain_hash`` breaks the previous-link continuity.
        """
        cur = self._conn.cursor()
        rows = cur.execute("SELECT * FROM evidence ORDER BY id").fetchall()
        problems: list[str] = []
        prev_hash = ""
        prev_id = None
        for row in rows:
            rid = row["id"]
            content = {
                "control_id": row["control_id"],
                "framework": row["framework"],
                "status": row["status"],
                "source": row["source"],
                "detail": row["detail"],
                "timestamp": row["timestamp"],
            }
            expected_content = _content_hash(**content)
            if row["content_hash"] != expected_content:
                problems.append(f"row {rid} content tampered (content_hash mismatch)")
            expected_chain = hashlib.sha256(
                (prev_hash + expected_content).encode("utf-8")
            ).hexdigest()
            if row["chain_hash"] != expected_chain:
                problems.append(f"row {rid} chain broken (chain_hash mismatch vs prev {prev_id})")
            if row["prev_id"] != prev_id:
                problems.append(
                    f"row {rid} prev_id mismatch (got {row['prev_id']}, expected {prev_id})"
                )
            prev_hash = expected_chain
            prev_id = rid
        return {
            "valid": len(problems) == 0,
            "checked": len(rows),
            "problems": problems,
        }

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _row_to_evidence(row: sqlite3.Row) -> ControlEvidence:
        return ControlEvidence(
            control_id=row["control_id"],
            framework=row["framework"],
            status=row["status"],
            source=row["source"],
            detail=row["detail"],
            timestamp=row["timestamp"],
            evidence_hash=row["content_hash"],
        )

    def __enter__(self) -> EvidenceRegister:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


# =============================================================================
# GapAnalysis
# =============================================================================


def _effective_status(register: EvidenceRegister, control_id: str) -> str:
    """Derive a control's posture from its evidence.

    Implemented wins if any evidence claims implementation; otherwise any
    partial; otherwise missing.
    """
    rows = register.get(control_id)
    if not rows:
        return STATUS_MISSING
    statuses = {r.status for r in rows}
    if STATUS_IMPLEMENTED in statuses:
        return STATUS_IMPLEMENTED
    if STATUS_PARTIAL in statuses:
        return STATUS_PARTIAL
    return STATUS_MISSING


class GapAnalysis:
    """Live, evidence-derived gap analysis over a :class:`EvidenceRegister`.

    For each framework in scope, the analysis:

    * derives each control's posture from the register's evidence,
    * computes the pass percentage and a 0-100 compliance score,
    * lists the gaps (controls that are missing or only partial),
    * produces a top-N remediation list (highest-priority controls first).
    """

    def __init__(
        self, register: EvidenceRegister | None = None, controls: list[Control] | None = None
    ) -> None:
        self._register = register or EvidenceRegister()
        self._controls = list(controls) if controls is not None else BUILTIN_CONTROLS

    @property
    def register(self) -> EvidenceRegister:
        return self._register

    def analyze(self, framework: str | None = None, top_n: int | None = 5) -> dict[str, Any]:
        """Produce the full gap report for one framework (or all frameworks)."""
        if framework is not None:
            frameworks = [str(framework).lower()]
        else:
            frameworks = list(_DEFAULT_FRAMEWORKS)

        frameworks = [f for f in frameworks if controls_for_framework(f)]

        per_framework: dict[str, dict[str, Any]] = {}
        all_gaps: list[dict[str, Any]] = []
        overall_pass = 0.0
        overall_total = 0

        for fw in frameworks:
            fw_controls = self._controls_for(fw)
            applicable = list(fw_controls)
            total = len(applicable)
            implemented = 0
            partial = 0
            missing = 0
            for c in applicable:
                st = _effective_status(self._register, c.id)
                if st == STATUS_IMPLEMENTED:
                    implemented += 1
                elif st == STATUS_PARTIAL:
                    partial += 1
                else:
                    missing += 1
            pass_pct = (implemented / total * 100.0) if total else 100.0
            score = round(pass_pct, 2)
            per_framework[fw] = {
                "framework": fw,
                "pass_pct": round(pass_pct, 2),
                "score": score,
                "implemented": implemented,
                "partial": partial,
                "missing": missing,
                "total": total,
            }
            overall_pass += pass_pct
            overall_total += 1
            # gaps = controls not fully implemented
            for c in applicable:
                st = _effective_status(self._register, c.id)
                if st != STATUS_IMPLEMENTED:
                    evidence = [e.to_dict() for e in self._register.get(c.id)]
                    all_gaps.append(
                        {
                            "control_id": c.id,
                            "framework": fw,
                            "title": c.title,
                            "category": c.category,
                            "status": st,
                            "severity": 2 if st == STATUS_MISSING else 1,
                            "evidence": evidence,
                        }
                    )

        # Sort gaps most-severe first, then by control id.
        all_gaps.sort(key=lambda g: (-g["severity"], g["control_id"]))
        remediation = all_gaps[:top_n] if top_n is not None else all_gaps

        return {
            "framework": framework.lower() if framework else None,
            "scope": frameworks,
            "frameworks": per_framework,
            "pass_pct": round(overall_pass / overall_total, 2) if overall_total else 100.0,
            "gaps": all_gaps,
            "remediation": remediation,
            "gap_count": len(all_gaps),
            "integrity": self._register.verify_integrity(),
            "timestamp": _now(),
        }

    def gaps(self, framework: str | None = None) -> list[dict[str, Any]]:
        """Return only the list of gaps (missing / partial controls)."""
        return self.analyze(framework=framework, top_n=None)["gaps"]

    def score(self, framework: str | None) -> float:
        """Return the 0-100 compliance score for a single framework."""
        report = self.analyze(framework=framework)
        if framework is not None:
            return report["frameworks"][str(framework).lower()]["score"]
        return report["pass_pct"]

    def _controls_for(self, framework: str) -> list[Control]:
        fw = str(framework).lower()
        return [c for c in self._controls if c.framework.lower() == fw]


# =============================================================================
# Facade functions
# =============================================================================


def _resolve_register(register: EvidenceRegister | None) -> EvidenceRegister:
    return register if register is not None else EvidenceRegister()


def assess(
    framework: str | None = None, register: EvidenceRegister | None = None, top_n: int = 5
) -> dict[str, Any]:
    """Produce a live gap report from an evidence register.

    ``framework=None`` reports across all frameworks. If no register is
    supplied, a fresh in-memory register is used.
    """
    reg = _resolve_register(register)
    return GapAnalysis(reg).analyze(framework=framework, top_n=top_n)


def ingest(
    results: dict[str, Any],
    register: EvidenceRegister | None = None,
    source: str = "scan",
    framework: str | None = None,
) -> int:
    """Bulk-add evidence from a scan-results mapping.

    ``results`` maps a control id (or ``framework -> {control: ...}``) to a
    status (``"implemented"`` | ``"partial"`` | ``"missing"``), a
    ``{"status": ..., "source": ..., "detail": ...}`` dict, or a
    :class:`ControlEvidence`. Returns the number of records added/updated.
    """
    reg = _resolve_register(register)
    added = 0
    if not isinstance(results, dict):
        msg = "ingest expects a dict of scan results"
        raise TypeError(msg)

    # Support nested {framework: {control: value}} or flat {control: value}.
    items: list[tuple] = []
    flat = all(not isinstance(v, dict) or "status" in v for v in results.values())
    if flat:
        for cid, value in results.items():
            items.append((framework, cid, value))
    else:
        for fw, controls in results.items():
            for cid, value in controls.items():
                items.append((str(fw).lower(), cid, value))

    for fw, cid, value in items:
        if isinstance(value, ControlEvidence):
            ev = value
        elif isinstance(value, dict):
            st = value.get("status", STATUS_MISSING)
            src = value.get("source", source)
            det = value.get("detail", "")
            ts = value.get("timestamp", _now())
            ev = ControlEvidence(
                control_id=cid,
                framework=fw or _framework_for_control(cid) or FRAMEWORK_OWASP,
                status=str(st).lower(),
                source=src,
                detail=det,
                timestamp=ts,
            )
        elif isinstance(value, str):
            ev = ControlEvidence(
                control_id=cid,
                framework=fw or _framework_for_control(cid) or FRAMEWORK_OWASP,
                status=str(value).lower(),
                source=source,
                detail="",
            )
        else:  # pragma: no cover - defensive
            continue
        reg.add(ev)
        added += 1
    return added


def _framework_for_control(control_id: str) -> str | None:
    for c in BUILTIN_CONTROLS:
        if c.id == control_id:
            return c.framework
    return None


__all__ = [
    "ControlEvidence",
    "EvidenceRegister",
    "GapAnalysis",
    "assess",
    "ingest",
    "EVIDENCE_STATUSES",
]
