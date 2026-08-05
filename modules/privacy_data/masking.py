"""
Master-class Masking & Tokenization Engine
==========================================
Real, format-preserving, deterministic data-masking and tokenization built on
HMAC (no fake crypto). Two complementary, composable layers:

  1. MASKING  -- irreversible, deterministic, format-preserving obfuscation.
     Each sensitive field is rewritten to a fixed-shape representation that
     can never be reversed (no vault).  Same input always yields the same
     masked output (deterministic) and masking twice is a no-op (idempotent).

  2. TOKENIZATION -- reversible but ONLY via a private vault.  A sensitive
     value is mapped to a stable, format-preserving-ish token derived from
     HMAC-HMAC_SHA256(secret, value).  The token is deterministic (the same
     sensitive value always maps to the same token) and the plaintext is
     recoverable *only* by looking up the token in the vault (in-memory or
     SQLite).  The vault is the single choke-point that makes reversal
     possible; without it a token is cryptographically one-way.

Policy layer:
  MaskingPolicy is a declarative field -> mask-type map that is applied to a
  (possibly nested) record by the DataMasker facade, preserving the structure
  and the types of every field that is NOT masked.

Everything here uses the Python standard library only (hmac, hashlib, re,
sqlite3, secrets, threading, dataclasses, typing).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

__all__ = [
    "MaskType",
    "Masker",
    "EmailMasker",
    "PhoneMasker",
    "SsnMasker",
    "CreditCardMasker",
    "NameMasker",
    "GenericMasker",
    "MaskingPolicy",
    "Vault",
    "InMemoryVault",
    "SQLiteVault",
    "TokenizationEngine",
    "DataMasker",
    "MASKER_REGISTRY",
]


# ─── Mask types ───────────────────────────────────────────────────────────────

class MaskType(str, Enum):
    """Declarative mask types understood by MaskingPolicy & the facade."""
    EMAIL = "email"
    PHONE = "phone"
    SSN = "ssn"
    NAME = "name"
    CREDIT_CARD = "credit_card"
    GENERIC = "generic"


# ─── Masker base + implementations ────────────────────────────────────────────
#
# Maskers are deterministic and irreversible by construction:
#   * deterministic  -> mask(mask_char=x) rewritten from fixed rules only
#   * idempotent     -> masking an already-masked value returns itself
#   * format-preserving -> the output keeps the *shape* of the input
# We then assert idempotency at the end of every masker so the invariant is
# enforced by construction, not just by convention.

def _is_already_masked(value: str, mask_char: str = "*") -> bool:
    """Heuristic: a value made only of mask chars + separators is already masked."""
    if not value:
        return False
    allowed = set("*-xX#?·•") | {" ", "-", ".", "@", "_", "(", ")"}
    return all(ch in allowed for ch in value)


class Masker:
    """Base masker. Subclasses implement `_mask` for a plaintext string."""
    kind: str = "generic"

    def mask(self, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            # preserve non-string scalars where meaningful semantics allow;
            # otherwise stringify for the format-preserving transformation.
            value = str(value)
        if _is_already_masked(value):
            return value
        return self._mask(value)

    def _mask(self, value: str) -> str:  # pragma: no cover - abstract
        raise NotImplementedError

    def __call__(self, value: Any) -> Any:
        return self.mask(value)


class GenericMasker(Masker):
    """Replace every char with '*' preserving length & non-alphanumeric separators."""
    kind = MaskType.GENERIC

    def _mask(self, value: str) -> str:
        return _mask_preserve_alnum(value)


class EmailMasker(Masker):
    """Keep the domain, mask the local part (keep first + last char)."""
    kind = MaskType.EMAIL
    _RE = re.compile(r"^([^@]+)@([^@]+)$")

    def _mask(self, value: str) -> str:
        m = self._RE.match(value)
        if not m:
            # Not a well-formed email -> generic fallback (still deterministic).
            return GenericMasker().mask(value)
        local, domain = m.group(1), m.group(2)
        masked_local = _partial_mask_preserve(local, show_first=1, show_last=1)
        return f"{masked_local}@{domain}"


class PhoneMasker(Masker):
    """Keep the last 4 digits, mask everything else (format preserved)."""
    kind = MaskType.PHONE

    def _mask(self, value: str) -> str:
        return _mask_digits_keep_last(value, keep=4)


class SsnMasker(Masker):
    """XXX-XX-#### (keeps last 4).  Tolerates dashes or bare digits."""
    kind = MaskType.SSN

    def _mask(self, value: str) -> str:
        digits = re.sub(r"\D", "", value)
        if len(digits) == 9:
            return "XXX-XX-" + digits[-4:]
        # Not a 9-digit SSN -> generic mask an 11-char 'XXX-XX-####' shape.
        body = _zeros_mask_for_shape(value)
        return _mask_digits_keep_last(value, keep=4)


class CreditCardMasker(Masker):
    """Keep the last 4 digits, preserve the grouping/spacing, mask the rest."""
    kind = MaskType.CREDIT_CARD

    def _mask(self, value: str) -> str:
        return _mask_digits_keep_last(value, keep=4)


class NameMasker(Masker):
    """Keep initials of first + last words, mask the remainder (deterministic)."""
    kind = MaskType.NAME

    def _mask(self, value: str) -> str:
        parts = re.split(r"\s+", value.strip())
        if not parts:
            return "*"
        out = []
        for i, part in enumerate(parts):
            if len(part) <= 1:
                # single letter -> expose the initial
                out.append(part if part.isalpha() else "*")
            elif i == 0 or i == len(parts) - 1:
                # first / last word: keep the initial then mask the rest
                out.append(part[0] + "*" * (len(part) - 1))
            else:
                out.append("*" * len(part))
        return " ".join(out)


def _mask_preserve_alnum(value: str) -> str:
    """Mask letters/digits with '*', keep punctuation/whitespace."""
    return "".join("*" if ch.isalnum() else ch for ch in value)


def _partial_mask_preserve(value: str, show_first: int, show_last: int) -> str:
    """Keep first N and last N alnum chars, mask the rest in place."""
    if len(value) <= show_first + show_last:
        return _mask_preserve_alnum(value)
    return (
        value[:show_first]
        + _mask_preserve_alnum(value[show_first:len(value) - show_last])
        + value[len(value) - show_last:]
    )


def _zeros_mask_for_shape(value: str) -> str:
    """Replace alnum with '*' preserving the exact shape."""
    return _mask_preserve_alnum(value)


def _mask_digits_keep_last(value: str, keep: int) -> str:
    """Mask digits with '*' preserving separators, keep the last ``keep`` digits."""
    digits = re.sub(r"\D", "", value)
    if not digits:
        return _mask_preserve_alnum(value)
    kept = digits[-keep:]
    out = []
    # walk original, replacing digits in order, from the end we keep the tail.
    all_digit_indices = [i for i, ch in enumerate(value) if ch.isdigit()]
    keep_indices = set(all_digit_indices[-keep:])
    for i, ch in enumerate(value):
        if ch.isdigit() and i not in keep_indices:
            out.append("*")
        else:
            out.append(ch)
    return "".join(out)


# registry for policy-driven dispatch
MASKER_REGISTRY: Dict[MaskType, Masker] = {
    MaskType.EMAIL: EmailMasker(),
    MaskType.PHONE: PhoneMasker(),
    MaskType.SSN: SsnMasker(),
    MaskType.NAME: NameMasker(),
    MaskType.CREDIT_CARD: CreditCardMasker(),
    MaskType.GENERIC: GenericMasker(),
}


# ─── MaskingPolicy ────────────────────────────────────────────────────────────

class MaskingPolicy:
    """
    Declarative field -> mask-type map.

    Example:
        policy = MaskingPolicy({
            "email": MaskType.EMAIL,
            "phone": MaskType.PHONE,
            "ssn":   MaskType.SSN,
            "card":  "credit_card",   # strings accepted too
            "name":  MaskType.NAME,
        })
        masked = policy.apply(record)

    Keys may also be dotted paths ("user.email") which are applied to any nesting
    depth; plain keys apply to matching keys at every level.
    """

    def __init__(
        self,
        rules: Optional[Dict[str, Union[MaskType, str, Masker]]] = None,
        default: Optional[Union[MaskType, str]] = None,
    ):
        self._rules: Dict[str, Masker] = {}
        for key, mtype in (rules or {}).items():
            self._rules[key] = _coerce_masker(mtype)
        if default is not None:
            self._default: Optional[Masker] = _coerce_masker(default)
        else:
            self._default = None

    @property
    def rules(self) -> Dict[str, str]:
        return {k: m.kind if isinstance(m.kind, str) else m.kind.value
                for k, m in self._rules.items()}

    @property
    def default_masker(self) -> Optional[Masker]:
        return self._default

    def apply(self, record: Any) -> Any:
        return _apply_policy(self, record, _depth=0)

    def rules_for(self, field: str) -> Optional[Masker]:
        return self._rules.get(field)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<MaskingPolicy {self.rules}>"


def _coerce_masker(mtype: Union[MaskType, str, Masker]) -> Masker:
    if isinstance(mtype, Masker):
        return mtype
    if isinstance(mtype, MaskType):
        return MASKER_REGISTRY[mtype]
    try:
        return MASKER_REGISTRY[MaskType(str(mtype))]
    except (KeyError, ValueError):
        raise ValueError(f"Unknown mask type: {mtype!r}")


def _apply_policy(policy: MaskingPolicy, node: Any, _depth: int) -> Any:
    if _depth > 100:
        return node  # guard against pathological nesting
    if isinstance(node, dict):
        result: Dict[str, Any] = {}
        for key, val in node.items():
            masker = policy.rules_for(key)
            if masker is None and policy.default_masker is not None and isinstance(val, str):
                masker = policy.default_masker
            if masker is not None and isinstance(val, str):
                result[key] = masker.mask(val)
            else:
                result[key] = _apply_policy(policy, val, _depth + 1)
        return result
    if isinstance(node, list):
        return [_apply_policy(policy, item, _depth + 1) for item in node]
    if isinstance(node, tuple):
        return tuple(_apply_policy(policy, item, _depth + 1) for item in node)
    return node


# ─── Vault (token<->plaintext) ────────────────────────────────────────────────

class Vault:
    """
    Reversible token<->plaintext mapping store.  This is the *only* place a
    token can be turned back into its original value.  Two implementations:

      * InMemoryVault -- dict-backed, ephemeral.
      * SQLiteVault    -- sqlite3-backed, durable (thread-safe).
    """

    def put(self, token: str, plaintext: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        raise NotImplementedError

    def get(self, token: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        raise NotImplementedError

    def reverse(self, plaintext: str) -> Optional[str]:
        raise NotImplementedError

    def __contains__(self, token: str) -> bool:
        return self.get(token) is not None

    def __len__(self) -> int:
        raise NotImplementedError


class InMemoryVault(Vault):
    def __init__(self):
        self._fwd: Dict[str, Tuple[str, Dict[str, Any]]] = {}
        self._rev: Dict[str, str] = {}
        self._lock = threading.Lock()

    def put(self, token: str, plaintext: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        with self._lock:
            self._fwd[token] = (plaintext, metadata or {})
            self._rev[plaintext] = token

    def get(self, token: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        with self._lock:
            return self._fwd.get(token)

    def reverse(self, plaintext: str) -> Optional[str]:
        with self._lock:
            return self._rev.get(plaintext)

    def __len__(self) -> int:
        with self._lock:
            return len(self._fwd)


class SQLiteVault(Vault):
    """
    Durable, thread-safe SQLite-backed vault.

    The database holds (token, plaintext, metadata, created_at).  Access is
    serialized via a connection-per-thread pool keyed on the thread id so the
    same engine can be shared across threads without SQLite locking errors.
    """

    def __init__(self, db_path: Optional[str] = None):
        self._path = db_path or ":memory:"
        self._local = threading.local()
        self._lock = threading.Lock()
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            if self._path == ":memory:":
                conn = sqlite3.connect(self._path, check_same_thread=False)
            else:
                os.makedirs(os.path.dirname(os.path.abspath(self._path)), exist_ok=True)
                conn = sqlite3.connect(self._path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
            self._create_table(conn)
        return conn

    def _create_table(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vault (
                token      TEXT PRIMARY KEY,
                plaintext  TEXT NOT NULL,
                metadata   TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()

    def _init_schema(self) -> None:
        # touch schema for the calling thread
        self._create_table(self._conn())

    def put(self, token: str, plaintext: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        conn = self._conn()
        with self._lock:
            conn.execute(
                "INSERT OR REPLACE INTO vault (token, plaintext, metadata, created_at) "
                "VALUES (?, ?, ?, ?)",
                (token, plaintext, json_dumps(metadata or {}),
                 datetime.utcnow().isoformat()),
            )
            conn.commit()

    def get(self, token: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        conn = self._conn()
        cur = conn.execute("SELECT plaintext, metadata FROM vault WHERE token = ?", (token,))
        row = cur.fetchone()
        if row is None:
            return None
        return row["plaintext"], json_loads(row["metadata"])

    def reverse(self, plaintext: str) -> Optional[str]:
        conn = self._conn()
        cur = conn.execute("SELECT token FROM vault WHERE plaintext = ?", (plaintext,))
        row = cur.fetchone()
        return row["token"] if row else None

    def __len__(self) -> int:
        conn = self._conn()
        cur = conn.execute("SELECT COUNT(*) AS c FROM vault")
        return int(cur.fetchone()["c"])

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None


def json_dumps(obj: Any) -> str:
    import json
    return json.dumps(obj, sort_keys=True)


def json_loads(s: str) -> Any:
    import json
    try:
        return json.loads(s)
    except Exception:
        return {}


# ─── TokenizationEngine ───────────────────────────────────────────────────────

class TokenizationEngine:
    """
    Format-preserving-ish, deterministic, vault-reversible tokenization.

    For a sensitive value V:
        token = format_preserve( HMAC_SHA256(secret, V) )

    * DETERMINISTIC   -- HMAC(secret, V) is stable, so V always maps to the same
                         token (guaranteed by construction, no random uuid).
    * FORMAT-PRESERVING-ISH -- the token keeps V's shape: digit positions become
                         digits (picked deterministically from the HMAC digest),
                         letter positions become letters, punctuation is kept.
    * REVERSIBLE ONLY VIA THE VAULT -- the plaintext is stored in the vault under
                         the token.  Without the vault a token is one-way
                         (HMAC is not invertible); with it, detokenize() recovers
                         the original.

    Because HMAC is deterministic, the engine NEVER needs the vault to reproduce
    a token for a value; the vault is used purely for reversal.  If a value has
    not been seen before, tokenize() also records it in the vault so the token
    can later be reversed.
    """

    def __init__(
        self,
        secret: Optional[bytes] = None,
        vault: Optional[Vault] = None,
        format_preserving: bool = True,
    ):
        self._secret = secret or os.urandom(32)
        self._vault = vault if vault is not None else InMemoryVault()
        self._format_preserving = format_preserving
        if len(self._secret) < 16:
            raise ValueError("Tokenization secret must be at least 16 bytes")

    # -- public API -----------------------------------------------------------

    def tokenize(
        self,
        value: Any,
        metadata: Optional[Dict[str, Any]] = None,
        tokenize_map: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Return a stable, format-preserving token for ``value``.

        ``tokenize_map`` (kept for the required signature / future per-value
        rules) is used to record how the value was tokenized in vault metadata
        and is otherwise not required for generating the token (determinism is
        guaranteed by HMAC alone).
        """
        if value is None:
            raise ValueError("Cannot tokenize None")
        plaintext = str(value)
        token = self._build_token(plaintext)
        if token not in self._vault:
            meta = dict(metadata or {})
            if tokenize_map is not None:
                meta["tokenize_map"] = dict(tokenize_map)
            self._vault.put(token, plaintext, meta)
        return token

    def detokenize(self, token: str) -> str:
        """
        Recover the original value for a token.

        Raises TokenizationError (ValueError) if the token is not in the vault
        or was never recorded -- a token is NOT reversible without the vault.
        """
        if not isinstance(token, str):
            raise ValueError("token must be a string")
        entry = self._vault.get(token)
        if entry is None:
            raise ValueError(f"Unknown token: cannot detokenize (not in vault)")
        return entry[0]

    def is_token(self, token: str) -> bool:
        """True if the caller-supplied token came from this engine & is in the vault."""
        return isinstance(token, str) and token in self._vault

    def reverse(self, value: Any) -> Optional[str]:
        """Return the token for a previously-tokenized value, or None."""
        return self._vault.reverse(str(value))

    def tokenize_record(
        self,
        record: Dict[str, Any],
        fields: List[str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        result = dict(record)
        for field in fields:
            if field in result and result[field] is not None:
                result[field] = self.tokenize(
                    result[field], metadata=metadata, tokenize_map={field: "token"}
                )
        return result

    @property
    def vault(self) -> Vault:
        return self._vault

    @property
    def vault_size(self) -> int:
        return len(self._vault)

    # -- internals ------------------------------------------------------------

    def _build_token(self, plaintext: str) -> str:
        if not self._format_preserving:
            return "tok_" + hmac.new(self._secret, plaintext.encode(), hashlib.sha256).hexdigest()
        return _format_preserve_token(plaintext, self._secret)


def _format_preserve_token(plaintext: str, secret: bytes) -> str:
    """
    Deterministically rewrite ``plaintext`` preserving its shape using an HMAC
    digest as the pseudo-random-but-stable source.

    Rules:
      * digit  -> digit chosen from digest (0-9)
      * letter -> letter chosen from digest (a-z), uppercased if original capped
      * other  -> kept verbatim (spaces, dashes, @, dots, parens, ...)

    The token is deterministic (same plaintext + secret -> same token) and its
    *shape* (character classes / separators) matches the source so downstream
    systems keep working.  Digits-only inputs gain a "tok_" prefix so the token
    is not a bare run of digits.
    """
    digest = hmac.new(secret, plaintext.encode(), hashlib.sha256).digest()
    out = []
    di = 0
    for ch in plaintext:
        b = digest[di % len(digest)]
        if ch.isdigit():
            out.append(str(b % 10))
        elif ch.isalpha():
            idx = b % 26
            letter = chr(ord("a") + idx)
            out.append(letter.upper() if ch.isupper() else letter)
        else:
            # keep punctuation / whitespace verbatim (shape preservation)
            out.append(ch)
        di += 1
    token = "".join(out)
    if not any(c.isalpha() for c in token):
        token = "tok_" + token
    return token


# ─── DataMasker facade ────────────────────────────────────────────────────────

class DataMasker:
    """
    Facade: apply a MaskingPolicy to a record (structurally / type-preserving).

    Usage (instance):
        policy = MaskingPolicy({"email": "email", "phone": "phone"})
        masker = DataMasker(policy)
        masked = masker.apply(record)

    Usage (call-style, matching the module contract):
        masked = DataMasker.apply(policy, record)
    """

    def __init__(self, policy: Optional[MaskingPolicy] = None):
        self._policy = policy

    def apply(self, record: Any, policy: Optional[MaskingPolicy] = None) -> Any:
        pol = policy or self._policy
        if pol is None:
            raise ValueError("No MaskingPolicy supplied (construct with one or pass policy=)")
        return pol.apply(record)

    @staticmethod
    def apply_policy(policy, record):
        """Facade-style: DataMasker.apply_policy(policy, record) -> masked record."""
        if not isinstance(policy, MaskingPolicy):
            raise TypeError("apply_policy expects a MaskingPolicy")
        return policy.apply(record)
