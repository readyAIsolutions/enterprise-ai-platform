#!/usr/bin/env python3
"""Encrypted-at-rest secrets vault + rotation scheduler + access audit.

MASTER-CLASS addition to the ENI Secret Rotation OS module.  While the
parent ``secret_rotation`` engine is deliberately *hash-only* (it never
retains a raw credential), this vault is the complementary counterpart: a
real, encrypted-at-rest secrets store so that when a credential *must* be
retained (e.g. an API key the platform actually needs to replay), it is
never written to disk in the clear.

Architecture
------------
* :class:`SecretVault`     - SQLite-backed, CBC-like (XOR-stream) encrypted
                             store.  Every secret is encrypted-at-rest with a
                             key derived from a master passphrase via PBKDF2,
                             and authenticated by an HMAC so any tampering or
                             a wrong master key is detected.  Plaintext is
                             never stored.
* :class:`RotationScheduler` - per-secret rotation policies (interval) plus
                             ``last_rotated`` tracking, ``due_for_rotation``
                             and an automatic ``rotate`` that generates a new
                             random secret and stores it.
* :class:`AccessAudit`      - append-only audit of every get/put/store/rotate/
                             delete with a SHA-256 hash chain so the log is
                             tamper-evident.
* :class:`VaultFacade`      - combines vault + scheduler + audit behind one
                             object sharing a single SQLite file.

Honest crypto (read this) - stdlib only
---------------------------------------
This is a *deliberately transparent*, educational-strength construction built
from ``hashlib``/``hmac``/``sqlite3`` with **no third-party deps**:

1.  A 64-byte key is derived from the master passphrase and a random 16-byte
    per-secret *salt* using ``hashlib.pbkdf2_hmac('sha256', ..., iterations)``.
    The first 32 bytes become the *encryption* key, the last 32 the *MAC* key.

2.  Encryption is a stream cipher: a keystream is expanded from
    ``enc_key || iv || block_counter`` via repeated SHA-256 calls, and the
    plaintext is XOR'd with that keystream.  (This is the classic
    "counter-mode Kerckhoffs stream" - fine for demonstrating AEAD-*style*
    construction, but **do not** use it for production secrets; prefer a
    battle-tested library such as ``cryptography`` / AES-GCM or libsodium
    there.  The interface here is designed so that swap is trivial.)

3.  Authentication: ``HMAC-SHA256(mac_key, version||salt||iv||ciphertext)`` is
    appended to the blob.  Every ``get`` recomputes and ``hmac.compare_digest``
    verifies the MAC **before** decrypting, so a flipped ciphertext byte or a
    wrong master key (which derives a different mac key) is rejected.

4.  ``last_rotated`` / policy state, the audit hash chain and the vault rows
    all live in one SQLite file for an atomic, durable on-disk story.  Tests
    exercise this against ``tmp_path`` databases.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import sqlite3
import threading
import time
from typing import TYPE_CHECKING, Any

from .secret_rotation import hash_secret

if TYPE_CHECKING:
    import builtins
    from collections.abc import Callable

logger = logging.getLogger("enterprise.secret_rotation.vault")

#: Number of PBKDF2 iterations used when a caller does not override.  High
#: enough to be meaningful, low enough that tests stay fast (tests may pass a
#: lower value explicitly for speed).
DEFAULT_PBKDF2_ITERATIONS = 100_000

#: Random-secret length (bytes) for auto-generated rotation candidates.
DEFAULT_ROTATION_BYTES = 32

BLOB_VERSION = b"\x01"
_CHAIN_SEED = b"eni-secret-rotation-audit-chain-v1"


class VaultError(Exception):
    """Base error for the encrypted vault."""


class VaultIntegrityError(VaultError):
    """Raised when a blob fails MAC verification (tampered / wrong key)."""


class SecretNotFoundError(VaultError, KeyError):
    """Raised when a requested secret does not exist."""


def derive_keys(
    master_key: str | bytes,
    salt: bytes,
    iterations: int = DEFAULT_PBKDF2_ITERATIONS,
) -> tuple[bytes, bytes]:
    """Derive ``(enc_key, mac_key)`` from ``master_key`` + ``salt`` via PBKDF2."""
    if isinstance(master_key, str):
        master_key = master_key.encode("utf-8")
    dk = hashlib.pbkdf2_hmac("sha256", master_key, salt, iterations, dklen=64)
    return dk[:32], dk[32:]


def _stream_xor(enc_key: bytes, iv: bytes, data: bytes) -> bytes:
    """XOR ``data`` against a SHA-256 CTR-like keystream from key+IV."""
    out = bytearray()
    block = 0
    while len(out) < len(data):
        ks = hashlib.sha256(enc_key + iv + block.to_bytes(8, "big")).digest()
        for i, b in enumerate(ks):
            idx = block * 32 + i
            if idx >= len(data):
                break
            out.append(data[idx] ^ b)
        block += 1
    return bytes(out)


def _authenticate(mac_key: bytes, salt: bytes, iv: bytes, cipher: bytes) -> bytes:
    return hmac.new(mac_key, BLOB_VERSION + salt + iv + cipher, hashlib.sha256).digest()


def encrypt_blob(
    secret: bytes, master_key: str | bytes, iterations: int = DEFAULT_PBKDF2_ITERATIONS
) -> bytes:
    """Encrypt ``secret`` into an authenticated blob (no plaintext stored)."""
    salt = os.urandom(16)
    iv = os.urandom(16)
    enc_key, mac_key = derive_keys(master_key, salt, iterations)
    cipher = _stream_xor(enc_key, iv, secret)
    mac = _authenticate(mac_key, salt, iv, cipher)
    return BLOB_VERSION + salt + iv + cipher + mac


def decrypt_blob(
    blob: bytes, master_key: str | bytes, iterations: int = DEFAULT_PBKDF2_ITERATIONS
) -> bytes:
    """Decrypt + MAC-verify an authenticated blob.

    Raises :class:`VaultIntegrityError` on a wrong master key or tampered
    ciphertext (the MAC will not verify).
    """
    if not blob or blob[0:1] != BLOB_VERSION:
        msg = "unknown blob version"
        raise VaultIntegrityError(msg)
    salt = blob[1:17]
    iv = blob[17:33]
    cipher = blob[33:-32]
    mac = blob[-32:]
    enc_key, mac_key = derive_keys(master_key, salt, iterations)
    expect = _authenticate(mac_key, salt, iv, cipher)
    if not hmac.compare_digest(expect, mac):
        msg = "MAC verification failed (wrong master key or tampered blob)"
        raise VaultIntegrityError(msg)
    return _stream_xor(enc_key, iv, cipher)


def _coerce_secret(secret: str | bytes) -> bytes:
    return secret.encode("utf-8") if isinstance(secret, str) else bytes(secret)


class SecretVault:
    """SQLite-backed encrypted-at-rest secrets store.

    Rows hold only {name, blob, created_at, updated_at, kind}.  The ``blob``
    is the authenticated ciphertext from :func:`encrypt_blob`; raw secrets are
    never stored and never even exist on the page in the clear.
    """

    def __init__(
        self,
        db_path: str | os.PathLike,
        master_key: str | bytes,
        iterations: int = DEFAULT_PBKDF2_ITERATIONS,
    ) -> None:
        self._db_path = str(db_path)
        self._master_key = master_key
        self._iterations = iterations
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self._db_path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS secrets (
                name       TEXT PRIMARY KEY,
                blob       BLOB NOT NULL,
                kind       TEXT NOT NULL DEFAULT 'plain',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        self._conn.commit()

    # -- low-level --------------------------------------------------------

    @property
    def master_key(self) -> str | bytes:
        return self._master_key

    @property
    def path(self) -> str:
        return self._db_path

    def _resolve_key(self, master_key: str | bytes | None) -> str | bytes:
        return self._master_key if master_key is None else master_key

    # -- CRUD -------------------------------------------------------------

    def put(
        self,
        name: str,
        secret: str | bytes,
        master_key: str | bytes | None = None,
        kind: str = "plain",
        now: float | None = None,
    ) -> dict[str, Any]:
        """Store ``secret`` encrypted-at-rest under ``name``."""
        ts = now if now is not None else time.time()
        payload = secret
        if kind == "hash":
            s = secret.decode("utf-8") if isinstance(secret, bytes) else secret
            payload = hash_secret(s)
        blob = encrypt_blob(
            _coerce_secret(payload),
            self._resolve_key(master_key),
            self._iterations,
        )
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO secrets (name, blob, kind, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    blob = excluded.blob,
                    kind = excluded.kind,
                    updated_at = excluded.updated_at
                """,
                (name, blob, kind, ts, ts),
            )
            self._conn.commit()
        return {"name": name, "kind": kind, "updated_at": ts}

    #: Alias for :meth:`put` matching a ``store`` verb.
    store = put

    def get(
        self,
        name: str,
        master_key: str | bytes | None = None,
    ) -> str:
        """Decrypt + MAC-verify ``name`` and return the plaintext string.

        Raises :class:`SecretNotFoundError` if absent and
        :class:`VaultIntegrityError` on a wrong master key / tampered blob.
        """
        with self._lock:
            row = self._conn.execute("SELECT blob FROM secrets WHERE name=?", (name,)).fetchone()
        if row is None:
            raise SecretNotFoundError(name)
        plain = decrypt_blob(bytes(row[0]), self._resolve_key(master_key), self._iterations)
        return plain.decode("utf-8")

    def rotate(
        self,
        name: str,
        new_secret: str | bytes | None = None,
        master_key: str | bytes | None = None,
        now: float | None = None,
    ) -> dict[str, Any]:
        """Store a freshly generated random secret for ``name``.

        If ``new_secret`` is not provided, one is generated with
        ``secrets.token_urlsafe``.  For ``kind='hash'`` rows the stored payload
        is the SHA-256 of the secret (hash-only mode).
        """
        with self._lock:
            row = self._conn.execute("SELECT kind FROM secrets WHERE name=?", (name,)).fetchone()
        if row is None:
            raise SecretNotFoundError(name)
        kind = row[0]
        if new_secret is None:
            new_secret = secrets.token_urlsafe(DEFAULT_ROTATION_BYTES)
        candidate = new_secret.decode("utf-8") if isinstance(new_secret, bytes) else new_secret
        payload: str | bytes = hash_secret(candidate) if kind == "hash" else candidate
        return self.put(name, payload, master_key=master_key, kind=kind, now=now)

    def list(self) -> builtins.list[dict[str, Any]]:
        """Return metadata for every stored secret (no plaintext)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT name, kind, created_at, updated_at FROM secrets ORDER BY name"
            ).fetchall()
        return [{"name": r[0], "kind": r[1], "created_at": r[2], "updated_at": r[3]} for r in rows]

    def has(self, name: str) -> bool:
        with self._lock:
            return (
                self._conn.execute("SELECT 1 FROM secrets WHERE name=?", (name,)).fetchone()
                is not None
            )

    def kind_of(self, name: str) -> str | None:
        with self._lock:
            row = self._conn.execute("SELECT kind FROM secrets WHERE name=?", (name,)).fetchone()
        return row[0] if row else None

    def delete(self, name: str) -> bool:
        """Delete ``name``; returns True if it existed, else False."""
        with self._lock:
            cur = self._conn.execute("DELETE FROM secrets WHERE name=?", (name,))
            self._conn.commit()
            return cur.rowcount > 0

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class RotationScheduler:
    """Per-secret rotation policies: interval, last_rotated, due checks."""

    def __init__(self, vault: SecretVault) -> None:
        self._vault = vault
        self._conn = vault._conn
        self._default_interval = 90 * 86400.0
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rotation_policies (
                name          TEXT PRIMARY KEY,
                interval_secs REAL NOT NULL,
                last_rotated  REAL
            )
            """
        )
        self._conn.commit()

    def set_policy(
        self, name: str, interval_secs: float, last_rotated: float | None = None
    ) -> None:
        if interval_secs <= 0:
            msg = "interval_secs must be > 0"
            raise ValueError(msg)
        ts = last_rotated if last_rotated is not None else time.time()
        with self._vault._lock:
            self._conn.execute(
                """
                INSERT INTO rotation_policies (name, interval_secs, last_rotated)
                VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    interval_secs = excluded.interval_secs,
                    last_rotated  = excluded.last_rotated
                """,
                (name, interval_secs, ts),
            )
            self._conn.commit()

    def policy(self, name: str) -> dict[str, Any] | None:
        with self._vault._lock:
            row = self._conn.execute(
                "SELECT interval_secs, last_rotated FROM rotation_policies WHERE name=?", (name,)
            ).fetchone()
        return {"name": name, "interval_secs": row[0], "last_rotated": row[1]} if row else None

    def mark_rotated(self, name: str, now: float | None = None) -> None:
        ts = now if now is not None else time.time()
        with self._vault._lock:
            self._conn.execute(
                "UPDATE rotation_policies SET last_rotated=? WHERE name=?",
                (ts, name),
            )
            self._conn.commit()

    def due_for_rotation(self, name: str, now: float | None = None) -> bool:
        """True when ``name``'s rotation interval has elapsed."""
        ts = now if now is not None else time.time()
        pol = self.policy(name)
        if pol is None:
            last = ts
            interval = self._default_interval
        else:
            last = pol["last_rotated"] if pol["last_rotated"] is not None else ts
            interval = pol["interval_secs"]
        return (ts - last) >= interval

    def rotate(
        self,
        name: str,
        now: float | None = None,
        generator: Callable[[], str] | None = None,
        master_key: str | bytes | None = None,
    ) -> dict[str, Any]:
        """Generate a new random secret for ``name`` and store it via the vault.

        Returns a dict with ``name``, ``new_secret`` (the plaintext candidate,
        or the stored hash) and ``next_due``.
        """
        ts = now if now is not None else time.time()
        pol = self.policy(name)
        interval = pol["interval_secs"] if pol is not None else self._default_interval
        if generator is not None:
            new_secret = generator()
        else:
            new_secret = secrets.token_urlsafe(DEFAULT_ROTATION_BYTES)
        result = self._vault.rotate(name, new_secret=new_secret, master_key=master_key, now=ts)
        # Preserve the configured interval; bump last_rotated to now.
        self.set_policy(name, interval, last_rotated=ts)
        result["new_secret"] = new_secret
        result["next_due"] = ts + interval
        return result


class AccessAudit:
    """Append-only, tamper-evident audit of vault actions.

    Every entry carries the previous entry's hash, forming a SHA-256 chain.
    :meth:`verify` replays the chain and reports whether it is intact.
    """

    def __init__(self, vault: SecretVault) -> None:
        self._vault = vault
        self._conn = vault._conn
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                secret_name TEXT NOT NULL,
                action      TEXT NOT NULL,
                ts          REAL NOT NULL,
                actor       TEXT NOT NULL,
                prev_hash   TEXT NOT NULL,
                entry_hash  TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def _last_hash(self) -> str:
        row = self._conn.execute(
            "SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return hashlib.sha256(_CHAIN_SEED).hexdigest()
        return row[0]

    def log(
        self,
        secret_name: str,
        action: str,
        ts: float | None = None,
        actor: str = "system",
    ) -> dict[str, Any]:
        now = ts if ts is not None else time.time()
        with self._vault._lock:
            prev = self._last_hash()
            payload = (
                prev + "|" + secret_name + "|" + action + "|" + repr(now) + "|" + actor
            ).encode("utf-8")
            entry_hash = hashlib.sha256(payload).hexdigest()
            self._conn.execute(
                """
                INSERT INTO audit_log
                    (secret_name, action, ts, actor, prev_hash, entry_hash)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (secret_name, action, now, actor, prev, entry_hash),
            )
            self._conn.commit()
        return {
            "secret_name": secret_name,
            "action": action,
            "ts": now,
            "actor": actor,
            "entry_hash": entry_hash,
        }

    def entries(self) -> list[dict[str, Any]]:
        with self._vault._lock:
            rows = self._conn.execute(
                "SELECT id, secret_name, action, ts, actor, prev_hash, entry_hash "
                "FROM audit_log ORDER BY id"
            ).fetchall()
        return [
            {
                "id": r[0],
                "secret_name": r[1],
                "action": r[2],
                "ts": r[3],
                "actor": r[4],
                "prev_hash": r[5],
                "entry_hash": r[6],
            }
            for r in rows
        ]

    def count(self) -> int:
        with self._vault._lock:
            return self._conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]

    def verify(self) -> dict[str, Any]:
        """Replay the hash chain; report integrity.

        Returns ``{"valid": bool, "entries": n, "broken_at": int|None}``.
        """
        entries = self.entries()
        prev = hashlib.sha256(_CHAIN_SEED).hexdigest()
        for idx, e in enumerate(entries):
            payload = (
                e["prev_hash"]
                + "|"
                + e["secret_name"]
                + "|"
                + e["action"]
                + "|"
                + repr(e["ts"])
                + "|"
                + e["actor"]
            ).encode("utf-8")
            expect = hashlib.sha256(payload).hexdigest()
            if e["prev_hash"] != prev or e["entry_hash"] != expect:
                return {"valid": False, "entries": len(entries), "broken_at": idx}
            prev = e["entry_hash"]
        return {"valid": True, "entries": len(entries), "broken_at": None}


class VaultFacade:
    """Combined vault + scheduler + audit behind one SQLite file."""

    def __init__(
        self,
        db_path: str | os.PathLike,
        master_key: str | bytes,
        iterations: int = DEFAULT_PBKDF2_ITERATIONS,
        actor: str = "system",
    ) -> None:
        self._actor = actor
        self.vault = SecretVault(db_path, master_key, iterations=iterations)
        self.scheduler = RotationScheduler(self.vault)
        self.audit = AccessAudit(self.vault)

    # -- vault ops (auto-audited) ----------------------------------------

    def put(
        self,
        name: str,
        secret: str | bytes,
        kind: str = "plain",
        actor: str | None = None,
    ) -> dict[str, Any]:
        result = self.vault.put(name, secret, kind=kind)
        self.audit.log(name, "put", actor=actor or self._actor)
        return result

    store = put

    def get(
        self,
        name: str,
        master_key: str | bytes | None = None,
        actor: str | None = None,
    ) -> str:
        value = self.vault.get(name, master_key=master_key)
        self.audit.log(name, "get", actor=actor or self._actor)
        return value

    def rotate(self, name: str, actor: str | None = None, **kw: Any) -> dict[str, Any]:  # noqa: ANN401  # forwards scheduler kwargs
        result = self.scheduler.rotate(name, **kw)
        self.audit.log(name, "rotate", actor=actor or self._actor)
        return result

    def delete(self, name: str, actor: str | None = None) -> bool:
        removed = self.vault.delete(name)
        if removed:
            self.audit.log(name, "delete", actor=actor or self._actor)
        return removed

    # -- scheduler passthrough -------------------------------------------

    def set_policy(
        self, name: str, interval_secs: float, last_rotated: float | None = None
    ) -> None:
        self.scheduler.set_policy(name, interval_secs, last_rotated)

    def due_for_rotation(self, name: str, now: float | None = None) -> bool:
        return self.scheduler.due_for_rotation(name, now)

    def mark_rotated(self, name: str, now: float | None = None) -> None:
        self.scheduler.mark_rotated(name, now)

    # -- reporting -------------------------------------------------------

    def list(self) -> builtins.list[dict[str, Any]]:
        return self.vault.list()

    def audit_entries(self) -> builtins.list[dict[str, Any]]:
        return self.audit.entries()

    def audit_verify(self) -> dict[str, Any]:
        return self.audit.verify()

    def close(self) -> None:
        self.vault.close()
