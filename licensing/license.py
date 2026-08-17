"""Enterprise licensing model — server-side license keys, validation and broker
enforcement.

This module is fully independent of the multiplayer server (and of any network
daemon). It serves two roles:

* **Vendor side** — ``LicenseManager.create(...)`` mints a new license key and
  signs it with a server-held secret via HMAC-SHA256. The signature is embedded
  in the key so a key can be validated *offline* by anything that knows the
  secret (no DB round-trip required for a freshness check).

* **Consumer side** — ``LicenseManager.validate(...)`` verifies the embedded
  signature in constant time, checks expiry, and returns the decoded tier /
  seat budget / expiry. ``broker_enforce(...)`` is the business-rule helper a
  task broker (or arbitrary service) can call to decide whether ``N`` concurrent
  builders fall within the active license.

Tiers::

    FREE    -> 10 builders
    TEAM    -> unlimited builders
    PRO     -> per-seat (seats are whatever was granted)
    HOSTED  -> fully managed / unlimited

All components are stdlib-only with zero external dependencies.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Tier constants
# ---------------------------------------------------------------------------

FREE = "FREE"
TEAM = "TEAM"
PRO = "PRO"
HOSTED = "HOSTED"

TIERS = (FREE, TEAM, PRO, HOSTED)

# Default seat budget per tier (None == unlimited / platform-managed).
TIER_DEFAULTS: dict[str, Optional[int]] = {
    FREE: 10,
    TEAM: None,    # unlimited
    PRO: None,     # per-seat: value supplied at create() time
    HOSTED: None,  # unlimited (managed fleet)
}


class LicenseError(Exception):
    """Base class for licensing failures."""


class InvalidLicenseError(LicenseError):
    """The key is malformed, unsigned, or its signature does not verify."""


class ExpiredLicenseError(LicenseError):
    """The key is well-formed and signed but past its expiry."""


class LicenseLimitExceeded(LicenseError):
    """The requested builder count exceeds the license's seat allowance."""


# ---------------------------------------------------------------------------
# Key (de)serialisation
# ---------------------------------------------------------------------------

_PAYLOAD_SEP = "."


class _Secret:
    """Fixed server-side secret wrapper (kept private to LicenseManager)."""

    def __init__(self, secret: str | bytes) -> None:
        if not secret:
            raise ValueError("license signing secret must be non-empty")
        self._secret = secret if isinstance(secret, bytes) else secret.encode("utf-8")

    def sign(self, payload: bytes) -> str:
        return hmac.new(self._secret, payload, hashlib.sha256).hexdigest()

    def verify(self, payload: bytes, signature: str) -> bool:
        expected = self.sign(payload)
        # Constant-time comparison — length-safe regardless of input lengths.
        return hmac.compare_digest(expected, signature)


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _freeze(value: Any) -> Any:
    """Normalise expiry values into a comparable form (epoch seconds or None)."""
    return value


# ---------------------------------------------------------------------------
# LicenseManager
# ---------------------------------------------------------------------------

class LicenseManager:
    """Mints, validates and enforces signed license keys."""

    def __init__(self, secret: str | bytes) -> None:
        self._secret = _Secret(secret)
        self._tier_defaults = dict(TIER_DEFAULTS)

    # -- minting -----------------------------------------------------------

    def create(
        self,
        key: str,
        tier: str = FREE,
        max_builders: Optional[int] = None,
        expires: Optional[float] = None,
    ) -> str:
        """Sign and return a license key string.

        ``key``   — a human/operator chosen identifier (e.g. a customer or
                    account id). It is embedded (not secret).
        ``tier``  — one of the :data:`TIERS` constants.
        ``max_builders``
                 — seat budget. Defaults per tier; for :data:`FREE` that is 10,
                   for :data:`PRO` it must (or may) be supplied as per-seat.
        ``expires`` — epoch-seconds timestamp, or ``None`` for a non-expiring
                    key.

        Returns an opaque signed token string (`<b64 payload>.<hex HMAC>`).
        """
        tier = tier.upper()
        if tier not in TIERS:
            raise ValueError(f"unknown tier: {tier!r}")

        seats = max_builders
        if seats is None:
            seats = self._tier_defaults[tier]
        if seats is not None and seats < 0:
            raise ValueError("max_builders must be >= 0")

        payload = {
            "key": str(key),
            "tier": tier,
            "max_builders": seats,
            "expires": expires,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        sig = self._secret.sign(raw)
        token = f"{_b64encode(raw)}{_PAYLOAD_SEP}{sig}"
        return token

    # -- validation --------------------------------------------------------

    def validate(self, token: str) -> dict[str, Any]:
        """Validate a license key.

        Returns ``{valid, tier, seats, expires}``.

        Raises :class:`InvalidLicenseError` on a tampered/malformed key and
        :class:`ExpiredLicenseError` when the key is signed but past expiry.
        """
        decoded = self._verify_and_decode(token)
        if decoded["expires"] is not None and time.time() > decoded["expires"]:
            raise ExpiredLicenseError(
                f"license for key {decoded['key']!r} expired at "
                f"{decoded['expires']}"
            )
        return {
            "valid": True,
            "tier": decoded["tier"],
            "seats": decoded["max_builders"],
            "expires": decoded["expires"],
        }

    # -- broker enforcement ------------------------------------------------

    def broker_enforce(self, token: str, builder_count: int) -> bool:
        """Return ``True`` if ``builder_count`` concurrent builders fit the license.

        * FREE / PRO  -> within the seat budget.
        * TEAM / HOSTED -> unlimited, always ``True``.

        An expired or tampered key propagates the same errors as
        :meth:`validate`. Callers that want a soft answer can catch
        :class:`LicenseError` and fall back to ``False``.
        """
        if builder_count < 0:
            raise ValueError("builder_count must be >= 0")
        decoded = self._verify_and_decode(token)
        if decoded["expires"] is not None and time.time() > decoded["expires"]:
            raise ExpiredLicenseError(
                f"license for key {decoded['key']!r} expired at "
                f"{decoded['expires']}"
            )
        tier = decoded["tier"]
        if tier in (TEAM, HOSTED):
            return True
        seats = decoded["max_builders"]
        if seats is None:
            seats = self._tier_defaults[tier]
            if seats is None:
                return True
        if builder_count > seats:
            return False
        return True

    # -- internals ---------------------------------------------------------

    def _verify_and_decode(self, token: str) -> dict[str, Any]:
        if not isinstance(token, str) or _PAYLOAD_SEP not in token:
            raise InvalidLicenseError("malformed license key")
        raw_b64, sig = token.rsplit(_PAYLOAD_SEP, 1)
        try:
            raw = _b64decode(raw_b64)
        except Exception as exc:  # pragma: no cover - defensive
            raise InvalidLicenseError("malformed license key payload") from exc
        if not self._secret.verify(raw, sig):
            raise InvalidLicenseError("license signature verification failed")
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise InvalidLicenseError("license payload is not valid JSON") from exc
