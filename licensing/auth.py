"""Product auth helper — minimal but real bearer-token facility.

Independent of the multiplayer server, this module lets any service issue a
short-lived bearer token bound to a *tenant* and a *scope*, and later verify it
back. Issued tokens are held **in-memory** (per-process) with an expiry, so a
token is only valid on the process that issued it — the intended use is a
single service authenticating its own callers/brokers.

Security properties:

* All stored-token comparisons (both lookup hashes and the presented token)
  are performed with :func:`hmac.compare_digest` — constant time.
* Expired tokens are purged from memory on access, so stale entries do not
  accumulate and cannot be verified.

Stdlib-only, zero external dependencies.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from typing import Dict, Optional, Tuple

_DEFAULT_LIFETIME = 3600.0  # 1 hour


class AuthError(Exception):
    """Base class for auth failures."""


class InvalidTokenError(AuthError):
    """The presented token is malformed, unknown, or failed verification."""


class ExpiredTokenError(AuthError):
    """The token is known but its lifetime has elapsed."""


def _const_eq(a: str, b: str) -> bool:
    """Constant-time string comparison (works for arbitrary lengths)."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


class TokenStore:
    """Thread-safe in-memory store mapping token hash -> (tenant, scope, exp)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tokens: Dict[str, Tuple[str, str, float]] = {}

    def put(self, token: str, tenant: str, scope: str, expires: float) -> None:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._lock:
            self._tokens[digest] = (tenant, scope, expires)

    def get(self, token: str) -> Optional[Tuple[str, str, float]]:
        """Return (tenant, scope, expires) if a *matching* token exists.

        A match by token digest is returned even if it has gone stale, so the
        caller can distinguish an *expired* (known) token from a *tampered*
        (unknown) one. Stale entries are purged here regardless.

        Comparison of the presented token is done against stored entries using a
        constant-time digest comparison, so a tampered token cannot be
        timing-differentiated from a wrong guess.
        """
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = time.time()
        match = None
        with self._lock:
            stale: list[str] = []
            for key, (tenant, scope, expires) in list(self._tokens.items()):
                expired = expires <= now
                # Constant-time comparison of the full stored key vs presented.
                if _const_eq(key, digest):
                    # Return the match even if stale, so the caller can tell an
                    # *expired* (known) token from a *tampered* (unknown) one.
                    match = (tenant, scope, expires)
                if expired:
                    stale.append(key)
            for key in stale:  # purge before returning
                self._tokens.pop(key, None)
        return match

    def revoke(self, token: str) -> bool:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._lock:
            return self._tokens.pop(digest, None) is not None


class AuthManager:
    """Minimal product-auth manager: issue + verify bearer tokens."""

    def __init__(self, token_lifetime: float = _DEFAULT_LIFETIME) -> None:
        self._lifetime = token_lifetime
        self._store = TokenStore()

    def issue_token(self, tenant: str, scope: str) -> str:
        """Create and remember a bearer token for ``tenant``/``scope``."""
        token = secrets.token_urlsafe(32)
        self._store.put(token, tenant, scope, time.time() + self._lifetime)
        return token

    def verify_token(self, token: str) -> dict[str, str]:
        """Verify ``token`` and return ``{"tenant": ..., "scope": ...}``.

        Raises :class:`InvalidTokenError` for a tampered/unknown token and
        :class:`ExpiredTokenError` if it is known but past its lifetime.
        """
        if not isinstance(token, str) or not token:
            raise InvalidTokenError("missing or empty token")
        hit = self._store.get(token)
        if hit is None:
            raise InvalidTokenError("token verification failed (unknown or tampered)")
        tenant, scope, expires = hit
        if time.time() > expires:
            raise ExpiredTokenError("token has expired")
        return {"tenant": tenant, "scope": scope}

    # Convenience aliases matching the task's top-level function signatures.
    issue = issue_token
    verify = verify_token


# ---------------------------------------------------------------------------
# Module-level convenience API (stateless-lite, single shared manager)
# ---------------------------------------------------------------------------

_default_manager = AuthManager()


def issue_token(tenant: str, scope: str) -> str:
    """Issue a bearer token for ``tenant``/``scope`` (default shared manager)."""
    return _default_manager.issue_token(tenant, scope)


def verify_token(token: str) -> dict[str, str]:
    """Verify ``token`` and return ``{"tenant", "scope"}`` (default manager)."""
    return _default_manager.verify_token(token)
