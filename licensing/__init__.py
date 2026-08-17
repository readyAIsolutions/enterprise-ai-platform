"""Enterprise licensing + product-auth layer.

Independent, server-side module (no dependency on the multiplayer server).
Mints and validates HMAC-signed license keys and issues/verifies in-memory
bearer auth tokens.

Modules:
    licensing.license  — LicenseManager: create / validate / broker_enforce, tiers.
    licensing.auth     — AuthManager: issue_token / verify_token (constant-time).

Stdlib-only, zero external dependencies.
"""

from __future__ import annotations

from .auth import (
    AuthError,
    AuthManager,
    ExpiredTokenError,
    InvalidTokenError,
    issue_token,
    verify_token,
)
from .license import (
    FREE,
    HOSTED,
    PRO,
    TEAM,
    TIERS,
    ExpiredLicenseError,
    InvalidLicenseError,
    LicenseError,
    LicenseLimitExceeded,
    LicenseManager,
)

__all__ = [
    # license
    "LicenseManager",
    "LicenseError",
    "InvalidLicenseError",
    "ExpiredLicenseError",
    "LicenseLimitExceeded",
    "FREE",
    "TEAM",
    "PRO",
    "HOSTED",
    "TIERS",
    # auth
    "AuthManager",
    "AuthError",
    "InvalidTokenError",
    "ExpiredTokenError",
    "issue_token",
    "verify_token",
]
