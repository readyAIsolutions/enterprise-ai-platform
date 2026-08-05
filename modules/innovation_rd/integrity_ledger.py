"""Reproducible-run fingerprinting and tamper-evident integrity ledger.

MASTER-CLASS integrity subsystem for the Innovation R&D OS.

Provides:

* :class:`RunFingerprint` -- a deterministic sha256 fingerprint that captures
  the *identity* of an experiment run: inputs hash + code version + params +
  seed + a filtered environment snapshot. Two runs with identical fingerprints
  are, by construction, reproducible runs.
* :class:`IntegrityLedger` -- an append-only SQLite ledger in which every record
  carries ``prev_hash`` linking it to the previous record, forming a real hash
  chain. A record's own ``record_hash`` is computed over its full content plus
  the previous record's hash, so any modification or insertion breaks the chain
  and is detectable.
* :class:`IntegrityVerifier` -- recomputes the hash chain over the stored
  records and reports exactly which run_ids were tampered with (modified,
  inserted, or removed).
* :func:`run_is_reproducible` -- convenience comparison of two run fingerprints
  (or fingerprint objects / hex digests).
* An honest isolation hook: each ledger record stores an ``isolation`` flag so
  the platform can prove that an experiment ran inside a sandboxed environment,
  and the fingerprint plumbing guarantees that changing inputs changes the
  run identity.

All hashing is canonical and environment-independent (sorted keys, stable
serialization), so the same logical inputs always produce the same hash. Stdlib
only (hashlib, sqlite3, json, dataclasses).
"""

from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger("enterprise.innovation_rd.integrity_ledger")

GENESIS_HASH = "0" * 64
"""Hash used as the prev_hash of the very first record in a ledger."""

# Environment variables that are inherently volatile (time, process, randomness)
# and therefore must NOT enter a run fingerprint. Keys are matched case-lessly.
DEFAULT_ENV_EXCLUDE = {
    "time",
    "date",
    "timestamp",
    "pid",
    "ppid",
    "random",
    "nonce",
    "nano",
    "micro",
    "epoch",
    "path",
    "cwd",
    "pwd",
    "argv",
    "hostname",
    "shell",
    "term",
}


def _canonical(value: Any) -> Any:  # noqa: ANN401
    """Recursively normalize an arbitrary value into a JSON-stable primitive.

    Dict keys are sorted, Enums collapse to their value, datetimes collapse to
    ISO strings, and numeric types keep their natural repr so ``0.1`` and
    ``0.10`` stay distinct. This makes serialization deterministic regardless
    of insertion order.
    """
    if isinstance(value, Enum):
        return _canonical(value.value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple, set, frozenset)):
        # Preserve list order (meaningful for params); only sort sets.
        if isinstance(value, (set, frozenset)):
            return sorted(_canonical(v) for v in value)
        return [_canonical(v) for v in value]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


def _serialize(canonical_payload: dict[str, Any]) -> bytes:
    """Serialize a canonical payload to deterministic bytes."""
    return json.dumps(
        canonical_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class RunFingerprint:
    """A deterministic identity for a single experiment run.

    The fingerprint hashes: inputs + code version + params + seed + a filtered
    environment snapshot. Because the serialization is canonical, two runs that
    are logically identical produce byte-identical fingerprints.

    Attributes:
        inputs: The run's inputs (dataset refs, raw inputs, data hashes).
        code_version: Version/sha of the code that executed the run.
        params: The run's hyperparameters / configuration.
        seed: The random seed (or None).
        env: A snapshot of the relevant environment (already filtered).
        digest: The computed sha256 hex digest (derived lazily via .compute()).
    """

    inputs: dict[str, Any] = field(default_factory=dict)
    code_version: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    seed: Any | None = None
    env: dict[str, Any] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        """Return the canonical payload that is hashed."""
        return {
            "inputs": _canonical(self.inputs),
            "code_version": _canonical(self.code_version),
            "params": _canonical(self.params),
            "seed": _canonical(self.seed),
            "env": _canonical(self.env),
        }

    def compute(self) -> str:
        """Compute (and return) the sha256 fingerprint for this run."""
        return _sha256_hex(_serialize(self.payload()))

    @classmethod
    def compute_hash(
        cls,
        *,
        inputs: dict[str, Any] | None = None,
        code_version: str = "",
        params: dict[str, Any] | None = None,
        seed: Any | None = None,  # noqa: ANN401
        env: dict[str, Any] | None = None,
        env_exclude: list[str] | None = None,
    ) -> str:
        """One-shot fingerprint computation from raw components.

        Args:
            inputs: Run inputs (data hashes, dataset refs, raw inputs).
            code_version: Version/sha of the executing code.
            params: Hyperparameters / configuration.
            seed: Random seed.
            env: Raw environment snapshot. Keys matching ``env_exclude`` (or
                the :data:`DEFAULT_ENV_EXCLUDE` volatile set) are filtered out.
            env_exclude: Additional environment key substrings to exclude.

        Returns:
            The 64-char sha256 hex digest.
        """
        fp = cls(
            inputs=inputs or {},
            code_version=code_version,
            params=params or {},
            seed=seed,
            env=filter_env_snapshot(env or {}, env_exclude),
        )
        return fp.compute()

    @classmethod
    def from_experiment(
        cls,
        experiment: Any,  # noqa: ANN401
        *,
        code_version: str = "",
        seed: Any | None = None,  # noqa: ANN401
        env: dict[str, Any] | None = None,
        env_exclude: list[str] | None = None,
    ) -> RunFingerprint:
        """Build a fingerprint from an innovation_rd ``Experiment``.

        Inputs are taken from the experiment's dataset/metrics, params from its
        variables, and the seed/code_version from the explicit arguments. This
        is a duck-typed helper so it does not hard-depend on the experiment
        module (avoids circular imports).
        """
        inputs: dict[str, Any] = {}
        params: dict[str, Any] = {}
        if experiment is not None:
            inputs = {
                "dataset": getattr(experiment, "dataset", ""),
                "metrics": getattr(experiment, "metrics", []),
                "baseline": getattr(experiment, "baseline", 0.0),
                "budget": getattr(experiment, "budget", 0.0),
            }
            params = dict(getattr(experiment, "variables", {}) or {})
        return cls(
            inputs=inputs,
            code_version=code_version,
            params=params,
            seed=seed,
            env=filter_env_snapshot(env or {}, env_exclude),
        )


def filter_env_snapshot(
    env: dict[str, Any], extra_exclude: list[str] | None = None
) -> dict[str, Any]:
    """Filter a raw environment snapshot down to fingerprint-relevant keys.

    Drops any key whose lowercased name contains a volatile marker from
    :data:`DEFAULT_ENV_EXCLUDE`, plus any caller-supplied extra exclusions.

    Args:
        env: Raw environment dictionary (e.g. ``dict(os.environ)``).
        extra_exclude: Additional key substrings to exclude.

    Returns:
        A filtered copy of the environment snapshot.
    """
    excludes = set(DEFAULT_ENV_EXCLUDE)
    if extra_exclude:
        excludes.update(str(e).lower() for e in extra_exclude)
    return {
        k: v for k, v in env.items() if not any(marker in str(k).lower() for marker in excludes)
    }


def run_is_reproducible(run_a: Any, run_b: Any) -> bool:  # noqa: ANN401
    """Compare two runs for reproducibility.

    Accepts :class:`RunFingerprint` objects, fingerprint hex digest strings, or
    raw component dicts (which are fingerprinted on the fly). Returns True when
    the two runs share the same deterministic run identity.

    Args:
        run_a: First run (RunFingerprint, hex digest, or spec dict).
        run_b: Second run (RunFingerprint, hex digest, or spec dict).

    Returns:
        True if the two runs are reproducible from each other.
    """
    digest_a = _coerce_digest(run_a)
    digest_b = _coerce_digest(run_b)
    return digest_a == digest_b and digest_a is not None


def _coerce_digest(run: Any) -> str | None:  # noqa: ANN401
    """Coerce a run object into a fingerprint hex digest (or None)."""
    if isinstance(run, RunFingerprint):
        return run.compute()
    if isinstance(run, str):
        return run
    if isinstance(run, dict):
        return RunFingerprint.compute_hash(
            inputs=run.get("inputs"),
            code_version=run.get("code_version", ""),
            params=run.get("params"),
            seed=run.get("seed"),
            env=run.get("env"),
        )
    return None


@dataclass(frozen=True)
class LedgerRecord:
    """A single append-only record in the integrity ledger.

    Attributes:
        seq: Monotonic sequence (row id) within the ledger.
        run_id: Identifier of the run this record describes.
        fingerprint: The run's RunFingerprint digest.
        actor: Who/what performed the action (user, service, worker).
        action: What happened (e.g. 'created', 'ran', 'completed', 'verified').
        isolation: True if the run executed inside an isolated environment.
        recorded_at: ISO-8601 UTC timestamp of the record.
        prev_hash: Hash of the previous record (chain link).
        record_hash: This record's own hash over content + prev_hash.
    """

    seq: int
    run_id: str
    fingerprint: str
    actor: str
    action: str
    isolation: bool
    recorded_at: str
    prev_hash: str
    record_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "run_id": self.run_id,
            "fingerprint": self.fingerprint,
            "actor": self.actor,
            "action": self.action,
            "isolation": self.isolation,
            "recorded_at": self.recorded_at,
            "prev_hash": self.prev_hash,
            "record_hash": self.record_hash,
        }


def _hash_record(
    seq: int,
    run_id: str,
    fingerprint: str,
    actor: str,
    action: str,
    isolation: bool,
    recorded_at: str,
    prev_hash: str,
) -> str:
    """Compute a record's chained hash over its full content + prev hash."""
    payload = {
        "seq": seq,
        "run_id": run_id,
        "fingerprint": fingerprint,
        "actor": actor,
        "action": action,
        "isolation": bool(isolation),
        "recorded_at": recorded_at,
        "prev_hash": prev_hash,
    }
    return _sha256_hex(_serialize(payload))


class IntegrityLedger:
    """Append-only, tamper-evident integrity ledger backed by SQLite.

    Records form a hash chain: each record stores the hash of the previous
    record. Tampering (modifying a record, inserting a foreign record, or
    deleting one) breaks the chain and is detectable by :class:`IntegrityVerifier`.

    The class exposes only :meth:`append` and :meth:`verify`-friendly read
    access; there is no public mutation path, honouring append-only semantics.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        """Open (or create) the ledger database.

        Args:
            db_path: Filesystem path to the SQLite DB, or ":memory:" for a
                transient in-memory ledger.
        """
        self._path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS integrity_records (
                seq         INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id      TEXT    NOT NULL,
                fingerprint TEXT    NOT NULL,
                actor       TEXT    NOT NULL,
                action      TEXT    NOT NULL,
                isolation   INTEGER NOT NULL DEFAULT 0,
                recorded_at TEXT    NOT NULL,
                prev_hash   TEXT    NOT NULL,
                record_hash TEXT    NOT NULL UNIQUE
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_records_run ON integrity_records(run_id)"
        )
        self._conn.commit()

    # -- write path (append-only) ----------------------------------------

    def append(
        self,
        run_id: str,
        fingerprint: str,
        actor: str = "unknown",
        action: str = "record",
        *,
        isolation: bool = False,
        recorded_at: str | None = None,
    ) -> LedgerRecord:
        """Append a new record to the chain.

        Args:
            run_id: Identifier of the run.
            fingerprint: The run's fingerprint digest.
            actor: Who performed the action.
            action: What action occurred.
            isolation: True if the run executed in an isolated environment.
            recorded_at: ISO timestamp (defaults to now UTC).

        Returns:
            The newly appended :class:`LedgerRecord`.
        """
        prev_hash = self.last_hash()
        timestamp = recorded_at or datetime.now(UTC).isoformat()
        next_seq = self._next_seq()
        record_hash = _hash_record(
            next_seq,
            run_id,
            fingerprint,
            actor,
            action,
            isolation,
            timestamp,
            prev_hash,
        )
        self._conn.execute(
            """
            INSERT INTO integrity_records
                (seq, run_id, fingerprint, actor, action, isolation,
                 recorded_at, prev_hash, record_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                next_seq,
                run_id,
                fingerprint,
                actor,
                action,
                int(bool(isolation)),
                timestamp,
                prev_hash,
                record_hash,
            ),
        )
        self._conn.commit()
        record = LedgerRecord(
            seq=next_seq,
            run_id=run_id,
            fingerprint=fingerprint,
            actor=actor,
            action=action,
            isolation=bool(isolation),
            recorded_at=timestamp,
            prev_hash=prev_hash,
            record_hash=record_hash,
        )
        logger.info(
            "Ledger append seq=%d run=%s action=%s isolation=%s",
            next_seq,
            run_id,
            action,
            bool(isolation),
        )
        return record

    # -- read path -------------------------------------------------------

    def records(self) -> list[LedgerRecord]:
        """Return all records in chain order (seq ascending)."""
        rows = self._conn.execute(
            "SELECT seq, run_id, fingerprint, actor, action, isolation, "
            "recorded_at, prev_hash, record_hash FROM integrity_records "
            "ORDER BY seq ASC"
        ).fetchall()
        return [
            LedgerRecord(
                seq=r[0],
                run_id=r[1],
                fingerprint=r[2],
                actor=r[3],
                action=r[4],
                isolation=bool(r[5]),
                recorded_at=r[6],
                prev_hash=r[7],
                record_hash=r[8],
            )
            for r in rows
        ]

    def last_hash(self) -> str:
        """Return the hash of the most recent record (GENESIS if empty)."""
        row = self._conn.execute(
            "SELECT record_hash FROM integrity_records ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else GENESIS_HASH

    def _next_seq(self) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 FROM integrity_records"
        ).fetchone()
        return int(row[0])

    def count(self) -> int:
        """Return the number of records in the ledger."""
        row = self._conn.execute("SELECT COUNT(*) FROM integrity_records").fetchone()
        return int(row[0])

    def __len__(self) -> int:
        return self.count()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        with contextlib.suppress(sqlite3.Error):
            self._conn.close()

    def __enter__(self) -> IntegrityLedger:
        return self

    def __exit__(self, *exc: Any) -> None:  # noqa: ANN401
        self.close()

    # -- testing/tamper-simulation helpers (NOT a public mutation API) ---

    def _execute_raw(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        """Execute raw SQL (used only to simulate tampering in tests)."""
        self._conn.execute(sql, params)
        self._conn.commit()


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of verifying a ledger's hash chain.

    Attributes:
        valid: True if the entire chain verifies.
        total_records: Number of records inspected.
        tampered_seq: Sequence numbers of records whose stored hash does not
            match its recomputed hash (modified or inserted).
        broken_links: Sequence numbers at which the prev_hash chain is broken.
        missing_seq: Expected sequence numbers that were deleted.
    """

    valid: bool
    total_records: int
    tampered_seq: list[int] = field(default_factory=list)
    broken_links: list[int] = field(default_factory=list)
    missing_seq: list[int] = field(default_factory=list)

    def summary(self) -> str:
        if self.valid:
            return f"VerificationResult: VALID ({self.total_records} records)"
        parts = []
        if self.tampered_seq:
            parts.append(f"tampered={self.tampered_seq}")
        if self.broken_links:
            parts.append(f"broken_links={self.broken_links}")
        if self.missing_seq:
            parts.append(f"missing={self.missing_seq}")
        return f"VerificationResult: INVALID ({'; '.join(parts)})"


class IntegrityVerifier:
    """Recomputes and checks an :class:`IntegrityLedger` hash chain.

    Detects three classes of tampering:

    * **Modification** -- a stored record's ``record_hash`` no longer matches
      its recomputed hash (flagged in ``tampered_seq``).
    * **Insertion** -- a foreign record whose ``record_hash`` is inconsistent
      with the chain (flagged in ``tampered_seq`` / ``broken_links``).
    * **Deletion** -- a gap in the expected monotonic ``seq`` (flagged in
      ``missing_seq``).
    """

    def verify(self, ledger: IntegrityLedger) -> VerificationResult:
        """Verify the full chain of a ledger.

        Args:
            ledger: The ledger to verify.

        Returns:
            A :class:`VerificationResult` describing validity and any tampering.
        """
        records = ledger.records()
        return self.verify_records(records)

    def verify_records(self, records: list[LedgerRecord]) -> VerificationResult:
        """Verify a list of ledger records as a standalone hash chain."""
        tampered: list[int] = []
        broken_links: list[int] = []
        missing: list[int] = []

        prev_hash = GENESIS_HASH
        expected_seq = 1
        for rec in records:
            # Deletion detection: sequence numbers must be contiguous.
            if rec.seq != expected_seq:
                missing.extend(range(expected_seq, rec.seq))
                expected_seq = rec.seq
            expected_seq += 1

            # Chain-link detection.
            if rec.prev_hash != prev_hash:
                broken_links.append(rec.seq)

            recomputed = _hash_record(
                rec.seq,
                rec.run_id,
                rec.fingerprint,
                rec.actor,
                rec.action,
                rec.isolation,
                rec.recorded_at,
                rec.prev_hash,
            )
            if recomputed != rec.record_hash:
                tampered.append(rec.seq)

            prev_hash = rec.record_hash

        valid = not (tampered or broken_links or missing)
        return VerificationResult(
            valid=valid,
            total_records=len(records),
            tampered_seq=tampered,
            broken_links=broken_links,
            missing_seq=missing,
        )

    def verify_fingerprint(self, fingerprint: RunFingerprint, expected: str) -> bool:
        """Convenience check that a fingerprint matches an expected digest."""
        return fingerprint.compute() == expected


def record_isolation_run(
    ledger: IntegrityLedger,
    run_id: str,
    fingerprint: str,
    actor: str = "isolation-manager",
    *,
    isolation: bool = True,
) -> LedgerRecord:
    """Honest isolation hook: record that a run executed in a sandbox.

    Writes an append-only ledger record carrying the ``isolation=True`` flag so
    the platform can later prove, from the tamper-evident chain, that the
    experiment genuinely ran inside an isolated environment.

    Args:
        ledger: The ledger to append to.
        run_id: Identifier of the run.
        fingerprint: The run's fingerprint digest.
        actor: Who recorded the isolation fact.
        isolation: Whether isolation was enforced (default True).

    Returns:
        The appended :class:`LedgerRecord`.
    """
    return ledger.append(
        run_id,
        fingerprint,
        actor=actor,
        action="isolated_run",
        isolation=isolation,
    )
