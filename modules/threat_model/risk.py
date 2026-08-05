#!/usr/bin/env python3
"""
ENI Threat Model — Risk Register & Mitigation Planning (Master Class).

Stdlib-only, zero-dependency risk-management layer layered over the STRIDE
threat modelling in ``threat_model.py``. Provides:

* ``SeverityScore``  — a CVSS-inspired, documented weighted formula that turns
  (impact, likelihood, privilege_level, attack_vector) into a single risk score
  in the 0–10 range plus a qualitative band (LOW/MEDIUM/HIGH/CRITICAL).
* ``RiskRegister``   — a durable SQLite-backed register of risks with full CRUD,
  status lifecycle (open → mitigated → closed) and severity/status filtering.
* ``MitigationPlanner`` — suggests minimum viable mitigations per STRIDE category
  and tracks the application status of each linked mitigation.
* ``ThreatAssessment`` — a facade that models a system (assets + threats),
  computes per-threat severity, persists to the register and produces a
  prioritized top-N risk list with mitigations and an overall risk score.

Everything is pure Python 3.10+ standard library (``sqlite3``, ``dataclasses``,
``enum``, ``math``). No external dependencies.

Version: 1.0.0
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

# ---------------------------------------------------------------------------
# Severity scoring
# ---------------------------------------------------------------------------


class SeverityBand(str, Enum):
    """Qualitative band derived from a 0–10 risk score (CVSS-style breaks)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @classmethod
    def from_score(cls, score: float) -> "SeverityBand":
        """Map a 0–10 numeric score to a qualitative band."""
        if score >= 9.0:
            return cls.CRITICAL
        if score >= 7.0:
            return cls.HIGH
        if score >= 4.0:
            return cls.MEDIUM
        return cls.LOW


class SeverityScore:
    """Compute a CVSS-like 0–10 risk score from four weighted factors.

    Formula (documented, weights sum to 1.0 over the two principal axes):

        impact_n      = clamp(impact, 0..10) / 10            # 0..1
        likelihood_n  = clamp(likelihood, 0..10) / 10        # 0..1
        av_factor     = ATTACK_VECTOR[attack_vector]         # 1.0..0.3 (ease)
        pr_factor     = PRIVILEGE[privilege_level]           # 1.0..0.45 (ease)

        exploitability_n = likelihood_n * av_factor * pr_factor   # 0..1

        risk = 0.60 * impact_n + 0.40 * exploitability_n

    Interpretation:
      * Impact dominates the score (60%) — a catastrophic data-loss with even a
        modest chance of occurring remains dangerous.
      * Exploitability (40%) is the likelihood tempered by *how easy* the
        attack vector is and *how little* privilege the attacker needs.
      * ``attack_vector`` scales ease: network (1.0) > adjacent (0.75) >
        local (0.5) > physical (0.3).
      * ``privilege_level`` is the privilege the attacker requires:
        none (1.0) > low (0.7) > high (0.45) — lower requirement is easier.

    The result is clamped to [0, 10] and rounded to two decimals.
    """

    ATTACK_VECTOR: Dict[str, float] = {
        "network": 1.0,
        "adjacent": 0.75,
        "adjacent_network": 0.75,
        "local": 0.5,
        "physical": 0.3,
    }

    # privilege the attacker must already hold to exploit — lower is easier
    PRIVILEGE: Dict[str, float] = {
        "none": 1.0,
        "low": 0.7,
        "high": 0.45,
        "required": 0.45,
    }

    IMPACT_WEIGHT = 0.60
    EXPLOIT_WEIGHT = 0.40

    def __init__(
        self,
        impact: float = 5.0,
        likelihood: float = 5.0,
        privilege_level: str = "none",
        attack_vector: str = "network",
    ) -> None:
        self.impact = float(impact)
        self.likelihood = float(likelihood)
        self.privilege_level = privilege_level.lower()
        self.attack_vector = attack_vector.lower()

    # -- factor helpers -----------------------------------------------------

    def _impact_n(self) -> float:
        return max(0.0, min(self.impact, 10.0)) / 10.0

    def _likelihood_n(self) -> float:
        return max(0.0, min(self.likelihood, 10.0)) / 10.0

    def _attack_vector_factor(self) -> float:
        factor = self.ATTACK_VECTOR.get(self.attack_vector)
        if factor is None:
            # unknown vectors are treated pessimistically by defaulting to network
            factor = self.ATTACK_VECTOR["network"]
        return factor

    def _privilege_factor(self) -> float:
        factor = self.PRIVILEGE.get(self.privilege_level)
        if factor is None:
            factor = self.PRIVILEGE["none"]
        return factor

    # -- evaluation ---------------------------------------------------------

    def exploitability(self) -> float:
        """Return the 0–1 exploitability component (likelihood x ease)."""
        return self._likelihood_n() * self._attack_vector_factor() * self._privilege_factor()

    def score(self) -> float:
        """Return the weighted 0–10 risk score."""
        exploitability_n = self.exploitability()
        raw = self.IMPACT_WEIGHT * self._impact_n() + self.EXPLOIT_WEIGHT * exploitability_n
        return round(max(0.0, min(raw, 1.0)) * 10.0, 2)

    def band(self) -> SeverityBand:
        """Return the qualitative band for this score."""
        return SeverityBand.from_score(self.score())

    def to_dict(self) -> Dict[str, Any]:
        """Return a serializable summary of the scoring."""
        return {
            "impact": self.impact,
            "likelihood": self.likelihood,
            "privilege_level": self.privilege_level,
            "attack_vector": self.attack_vector,
            "exploitability": round(self.exploitability(), 3),
            "score": self.score(),
            "band": self.band().value,
        }

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"SeverityScore(impact={self.impact}, likelihood={self.likelihood}, "
            f"priv={self.privilege_level!r}, av={self.attack_vector!r}) "
            f"> score={self.score()} [{self.band().value}]"
        )


# ---------------------------------------------------------------------------
# Risk register (SQLite-backed)
# ---------------------------------------------------------------------------

# valid lifecycle states
STATUS_OPEN = "open"
STATUS_MITIGATED = "mitigated"
STATUS_CLOSED = "closed"
STATUSES = (STATUS_OPEN, STATUS_MITIGATED, STATUS_CLOSED)


@dataclass
class Risk:
    """A single persisted risk record."""

    id: str
    title: str
    category: str
    severity: float
    status: str = STATUS_OPEN
    owner: str = ""
    notes: str = ""
    noted_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "severity": float(self.severity),
            "status": self.status,
            "owner": self.owner,
            "notes": self.notes,
            "noted_at": self.noted_at,
            "updated_at": self.updated_at,
        }


def _now_iso() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RiskRegister:
    """A durable SQLite-backed risk register.

    Persists risks across ``add``/``get``/``update``/``set_status`` calls and
    across process restarts when a file path (rather than ``:memory:``) is used.
    Thread-safe for concurrent append/read access.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or ":memory:"
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._create_schema()

    # -- schema / helpers ---------------------------------------------------

    def _create_schema(self) -> None:
        cur = self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS risks (
                id         TEXT PRIMARY KEY,
                title      TEXT NOT NULL,
                category   TEXT NOT NULL,
                severity   REAL NOT NULL,
                status     TEXT NOT NULL,
                owner      TEXT NOT NULL DEFAULT '',
                notes      TEXT NOT NULL DEFAULT '',
                noted_at   TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def _row_to_risk(self, row: sqlite3.Row) -> Risk:
        return Risk(
            id=row["id"],
            title=row["title"],
            category=row["category"],
            severity=float(row["severity"]),
            status=row["status"],
            owner=row["owner"],
            notes=row["notes"],
            noted_at=row["noted_at"],
            updated_at=row["updated_at"],
        )

    def _validate_status(self, status: str) -> None:
        if status not in STATUSES:
            raise ValueError(
                f"invalid status {status!r}; expected one of {STATUSES}"
            )

    # -- CRUD ---------------------------------------------------------------

    def add(
        self,
        id: str,
        title: str,
        category: str,
        severity: float,
        status: str = STATUS_OPEN,
        owner: str = "",
        notes: str = "",
    ) -> Risk:
        """Insert a new risk. Raises ValueError if the id already exists."""
        self._validate_status(status)
        now = _now_iso()
        with self._lock:
            exists = self._conn.execute(
                "SELECT 1 FROM risks WHERE id = ?", (id,)
            ).fetchone()
            if exists:
                raise ValueError(f"risk {id!r} already exists")
            self._conn.execute(
                """
                INSERT INTO risks
                    (id, title, category, severity, status, owner, notes, noted_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (id, title, category, float(severity), status, owner, notes, now, now),
            )
            self._conn.commit()
        return Risk(
            id=id, title=title, category=category, severity=float(severity),
            status=status, owner=owner, notes=notes, noted_at=now, updated_at=now,
        )

    def get(self, id: str) -> Optional[Risk]:
        """Return the risk with ``id`` or None if absent."""
        row = self._conn.execute(
            "SELECT * FROM risks WHERE id = ?", (id,)
        ).fetchone()
        return self._row_to_risk(row) if row else None

    def update(
        self,
        id: str,
        title: Optional[str] = None,
        category: Optional[str] = None,
        severity: Optional[float] = None,
        owner: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Risk:
        """Update selectable fields of an existing risk. Raises KeyError if absent."""
        current = self.get(id)
        if current is None:
            raise KeyError(f"no such risk: {id!r}")
        with self._lock:
            self._conn.execute(
                """
                UPDATE risks SET
                    title = COALESCE(?, title),
                    category = COALESCE(?, category),
                    severity = COALESCE(?, severity),
                    owner = COALESCE(?, owner),
                    notes = COALESCE(?, notes),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    title, category, float(severity) if severity is not None else None,
                    owner, notes, _now_iso(), id,
                ),
            )
            self._conn.commit()
        return self.get(id)  # type: ignore[return-value]

    def set_status(self, id: str, status: str) -> Risk:
        """Transition a risk's lifecycle status (open/mitigated/closed)."""
        self._validate_status(status)
        current = self.get(id)
        if current is None:
            raise KeyError(f"no such risk: {id!r}")
        with self._lock:
            self._conn.execute(
                "UPDATE risks SET status = ?, updated_at = ? WHERE id = ?",
                (status, _now_iso(), id),
            )
            self._conn.commit()
        updated = self.get(id)
        return updated  # type: ignore[return-value]

    def close(self, id: str, owner: Optional[str] = None) -> Risk:
        """Convenience: mark a risk closed (optionally setting the owner)."""
        if owner is not None:
            self.update(id, owner=owner)
        return self.set_status(id, STATUS_CLOSED)

    def delete(self, id: str) -> bool:
        """Remove a risk. Returns True if it existed."""
        with self._lock:
            cur = self._conn.execute("DELETE FROM risks WHERE id = ?", (id,))
            self._conn.commit()
        return cur.rowcount > 0

    # -- list / filter ------------------------------------------------------

    def list(self, status: Optional[str] = None) -> List[Risk]:
        """Return all risks, optionally filtered to a single status."""
        return self.filter(status=status)

    def filter(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
        severity_min: Optional[float] = None,
        severity_max: Optional[float] = None,
    ) -> List[Risk]:
        """Return risks matching the given criteria (all optional, ANDed).

        ``severity_min``/``severity_max`` are inclusive bounds on the 0–10 score.
        """
        clauses: List[str] = []
        params: List[Any] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if category is not None:
            clauses.append("category = ?")
            params.append(category)
        if severity_min is not None:
            clauses.append("severity >= ?")
            params.append(float(severity_min))
        if severity_max is not None:
            clauses.append("severity <= ?")
            params.append(float(severity_max))
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self._conn.execute(
            f"SELECT * FROM risks{where} ORDER BY severity DESC, id",
            params,
        ).fetchall()
        return [self._row_to_risk(r) for r in rows]

    def count(self) -> int:
        """Return the total number of risks in the register."""
        row = self._conn.execute("SELECT COUNT(*) AS c FROM risks").fetchone()
        return int(row["c"])

    def purge(self) -> None:
        """Empty the register (destructive; used for reset)."""
        with self._lock:
            self._conn.execute("DELETE FROM risks")
            self._conn.commit()

    def close_db(self) -> None:
        """Close the underlying SQLite connection."""
        with self._lock:
            self._conn.close()

    def __len__(self) -> int:
        return self.count()


# ---------------------------------------------------------------------------
# Mitigation planning
# ---------------------------------------------------------------------------

# Minimum viable controls per STRIDE category. These are the *baseline*
# mitigations every system should apply for the given threat category.
STRIDE_MITIGATIONS: Dict[str, List[str]] = {
    "spoofing": [
        "Mutual TLS / identity verification",
        "Strong authentication (MFA)",
        "Prompt-injection guard",
    ],
    "tampering": [
        "Output hashing & integrity checks",
        "Context / RAG sanitization",
        "Signed tool responses",
    ],
    "repudiation": [
        "Hash-chained audit logging",
        "Tool-call attestation",
        "Non-repudiable event trail",
    ],
    "information_disclosure": [
        "Data loss prevention on output",
        "PII redaction",
        "Secrets management & least-privilege",
    ],
    "denial_of_service": [
        "Request quotas",
        "Input length caps",
        "Rate limiting & resource isolation",
    ],
    "elevation_of_privilege": [
        "Least-privilege tool scoping",
        "Human-in-the-loop approvals",
        "Role-based access control",
    ],
    # acceptance: accept any case variant by normalising on lookup
}

# honour the Pascal-Case STRIDE names used by STRIDEThreatMapper too
_STRIDE_CANONICAL_ALIASES: Dict[str, str] = {
    "Spoofing": "spoofing",
    "Tampering": "tampering",
    "Repudiation": "repudiation",
    "Information Disclosure": "information_disclosure",
    "Denial of Service": "denial_of_service",
    "Elevation of Privilege": "elevation_of_privilege",
}


def _normalise_category(category: str) -> str:
    c = category.strip().lower().replace(" ", "_").replace("-", "_")
    return _STRIDE_CANONICAL_ALIASES.get(category, c)


class MitigationPlanner:
    """Suggest minimum viable mitigations per threat category and track status.

    Each mitigation linked to a risk is tracked with a status in
    {proposed, applied, verified}. The planner is in-memory and keyed by
    ``risk_id`` so it stays in lock-step with the ``RiskRegister``.
    """

    STATUS_PROPOSED = "proposed"
    STATUS_APPLIED = "applied"
    STATUS_VERIFIED = "verified"

    def __init__(self, mitigations: Optional[Dict[str, List[str]]] = None) -> None:
        self.mitigations: Dict[str, List[str]] = dict(
            mitigations or STRIDE_MITIGATIONS
        )
        # risk_id -> {mitigation_name: status}
        self._tracking: Dict[str, Dict[str, str]] = {}

    def suggest(self, category: str) -> List[str]:
        """Return baseline mitigations for a STRIDE category.

        Unknown categories yield an empty list (no invented controls).
        """
        key = _normalise_category(category)
        return list(self.mitigations.get(key, []))

    def categories(self) -> List[str]:
        """Return the STRIDE categories with defined mitigation baselines."""
        return list(self.mitigations.keys())

    # -- per-risk tracking --------------------------------------------------

    def plan(self, risk_id: str, category: str) -> List[str]:
        """Suggest baselines for a risk and register them as ``proposed``."""
        suggestions = self.suggest(category)
        tracking = self._tracking.setdefault(risk_id, {})
        for m in suggestions:
            tracking.setdefault(m, self.STATUS_PROPOSED)
        return suggestions

    def mark(self, risk_id: str, mitigation: str, status: str) -> None:
        """Track the application status of a mitigation for a risk."""
        if risk_id not in self._tracking:
            raise KeyError(f"no mitigation plan for risk {risk_id!r}; call plan() first")
        if mitigation not in self._tracking[risk_id]:
            raise KeyError(f"mitigation {mitigation!r} not suggested for {risk_id!r}")
        if status not in (
            self.STATUS_PROPOSED, self.STATUS_APPLIED, self.STATUS_VERIFIED,
        ):
            raise ValueError(f"invalid mitigation status {status!r}")
        self._tracking[risk_id][mitigation] = status

    def apply(self, risk_id: str, mitigation: str) -> None:
        """Mark a suggested mitigation as applied."""
        self.mark(risk_id, mitigation, self.STATUS_APPLIED)

    def verify(self, risk_id: str, mitigation: str) -> None:
        """Mark a suggested mitigation as applied and verified."""
        self.mark(risk_id, mitigation, self.STATUS_VERIFIED)

    def status(self, risk_id: str) -> Dict[str, str]:
        """Return {mitigation: status} for a risk (empty if not planned)."""
        return dict(self._tracking.get(risk_id, {}))

    def coverage(self, risk_id: str) -> float:
        """Return the fraction of planned mitigations applied/verified (0..1)."""
        tracking = self._tracking.get(risk_id, {})
        if not tracking:
            return 0.0
        done = sum(
            1 for s in tracking.values() if s in (self.STATUS_APPLIED, self.STATUS_VERIFIED)
        )
        return round(done / len(tracking), 3)

    def clear(self, risk_id: str) -> None:
        """Drop the tracked plan for a risk."""
        self._tracking.pop(risk_id, None)


# ---------------------------------------------------------------------------
# Threat assessment facade
# ---------------------------------------------------------------------------


@dataclass
class ThreatEntry:
    """A threat against an asset ready for scoring."""

    name: str
    category: str
    impact: float = 5.0
    likelihood: float = 5.0
    privilege_level: str = "none"
    attack_vector: str = "network"
    asset: str = "any"
    owner: str = ""
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "asset": self.asset,
            "impact": self.impact,
            "likelihood": self.likelihood,
            "privilege_level": self.privilege_level,
            "attack_vector": self.attack_vector,
        }


class ThreatAssessment:
    """Facade that models a system and turns threats into prioritized risk.

    The facade composes ``SeverityScore`` + ``RiskRegister`` +
    ``MitigationPlanner``: for each threat it computes a 0–10 severity, persists
    it to the register (status ``open``), plans baseline mitigations for the
    threat's STRIDE category, and can return a prioritized top-N list plus an
    overall risk score.
    """

    def __init__(
        self,
        register: Optional[RiskRegister] = None,
        planner: Optional[MitigationPlanner] = None,
        scorer: Optional[SeverityScore] = None,
    ) -> None:
        self.register = register or RiskRegister()
        self.planner = planner or MitigationPlanner()

    def _scorer_for(self, threat: ThreatEntry) -> SeverityScore:
        return SeverityScore(
            impact=threat.impact,
            likelihood=threat.likelihood,
            privilege_level=threat.privilege_level,
            attack_vector=threat.attack_vector,
        )

    @staticmethod
    def _risk_id(threat: ThreatEntry) -> str:
        base = threat.name.strip().lower().replace(" ", "_").replace("-", "_")
        base = "".join(ch for ch in base if ch.isalnum() or ch == "_") or "threat"
        return f"{base}_{threat.asset}"

    def assess(self, threats: Sequence[ThreatEntry]) -> List[Dict[str, Any]]:
        """Score each threat, persist to the register and plan mitigations.

        Returns a list of risk dicts (sorted by severity desc) mirroring the
        register. Idempotent per threat name+asset: re-scoring updates severity.
        """
        for threat in threats:
            scorer = self._scorer_for(threat)
            risk_id = self._risk_id(threat)
            existing = self.register.get(risk_id)
            if existing is None:
                self.register.add(
                    id=risk_id,
                    title=threat.name,
                    category=_normalise_category(threat.category),
                    severity=scorer.score(),
                    status=STATUS_OPEN,
                    owner=threat.owner,
                    notes=threat.notes,
                )
            else:
                self.register.update(
                    risk_id,
                    title=threat.name,
                    category=_normalise_category(threat.category),
                    severity=scorer.score(),
                    owner=threat.owner or existing.owner,
                    notes=threat.notes or existing.notes,
                )
            self.planner.plan(risk_id, threat.category)
        return self.prioritized()

    def prioritized(self, top_n: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return register risks sorted by severity desc, enriched with mitigations.

        Each item carries the stored risk fields plus ``mitigations`` (the
        suggested baselines) with their tracked status and ``coverage`` (0..1).
        """
        risks = self.register.list()
        enriched = []
        for risk in risks:
            status_map = self.planner.status(risk.id)
            enriched.append({
                **risk.to_dict(),
                "mitigations": list(status_map.keys()),
                "mitigation_status": status_map,
                "coverage": self.planner.coverage(risk.id),
            })
        enriched.sort(key=lambda r: (r["severity"], r["id"]), reverse=True)
        if top_n is not None and top_n > 0:
            enriched = enriched[:top_n]
        return enriched

    def top_n(self, n: int) -> List[Dict[str, Any]]:
        """Return the ``n`` most severe risks with their mitigations."""
        return self.prioritized(top_n=n)

    def overall_risk(self) -> float:
        """Return the overall system risk score (0–10).

        Defined as the severity of the single most dangerous risk — the ceiling
        that must be managed. Returns 0.0 when no risks are assessed.
        """
        risks = self.register.list()
        if not risks:
            return 0.0
        return max(float(r.severity) for r in risks)

    def risk_count(self) -> int:
        """Return the number of risks currently in the register."""
        return self.register.count()
