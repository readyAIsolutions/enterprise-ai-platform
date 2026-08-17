"""Tests for the licensing + product-auth layer (enterprise/licensing)."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # enterprise repo root

import pytest

from enterprise.licensing.auth import (
    AuthManager,
    ExpiredTokenError,
    InvalidTokenError,
    issue_token,
    verify_token,
)
from enterprise.licensing.license import (
    FREE,
    HOSTED,
    PRO,
    TEAM,
    ExpiredLicenseError,
    InvalidLicenseError,
    LicenseLimitExceeded,
    LicenseManager,
)

SECRET = "test-server-secret-0123456789abcdef"


@pytest.fixture
def manager() -> LicenseManager:
    return LicenseManager(SECRET)


# ---------------------------------------------------------------------------
# B2 — licenses
# ---------------------------------------------------------------------------


def test_free_with_12_builders_returns_exceed(manager: LicenseManager) -> None:
    """A valid FREE key allows 10 builders; 11+ returns 'exceed'."""
    key = manager.create("acme-free", tier=FREE)

    result = manager.validate(key)
    assert result["valid"] is True
    assert result["tier"] == FREE
    assert result["seats"] == 10  # FREE default seat budget

    assert manager.broker_enforce(key, 10) is True  # at the limit: allowed
    assert manager.broker_enforce(key, 12) is False  # exceeded
    assert manager.broker_enforce(key, 25) is False  # exceeded


def test_team_allows_100_builders(manager: LicenseManager) -> None:
    """A valid TEAM key is unlimited — 100 builders is fine."""
    key = manager.create("acme-team", tier=TEAM, max_builders=None)

    result = manager.validate(key)
    assert result["valid"] is True
    assert result["tier"] == TEAM
    assert result["seats"] is None  # unlimited

    assert manager.broker_enforce(key, 100) is True
    assert manager.broker_enforce(key, 10_000) is True  # still unlimited


def test_pro_is_per_seat(manager: LicenseManager) -> None:
    """PRO is per-seat: grants exactly the seat budget supplied."""
    key = manager.create("acme-pro", tier=PRO, max_builders=5)
    result = manager.validate(key)
    assert result["tier"] == PRO
    assert result["seats"] == 5
    assert manager.broker_enforce(key, 5) is True
    assert manager.broker_enforce(key, 6) is False


def test_hosted_unlimited(manager: LicenseManager) -> None:
    key = manager.create("acme-hosted", tier=HOSTED)
    assert manager.broker_enforce(key, 10_000) is True


def test_expired_key_is_invalid(manager: LicenseManager) -> None:
    """A key whose expiry has passed fails validation."""
    past = time.time() - 10
    key = manager.create("acme-free", tier=FREE, expires=past)

    with pytest.raises(ExpiredLicenseError):
        manager.validate(key)
    with pytest.raises(ExpiredLicenseError):
        manager.broker_enforce(key, 3)


def test_future_expiry_is_valid(manager: LicenseManager) -> None:
    future = time.time() + 3600
    key = manager.create("acme-free", tier=FREE, expires=future)
    assert manager.validate(key)["valid"] is True


def test_tampered_key_is_rejected(manager: LicenseManager) -> None:
    """Any modification to the payload or signature must fail verification."""
    key = manager.create("acme-free", tier=FREE)

    # Flip a character in the signature tail.
    sig = key.rsplit(".", 1)[1]
    mangled_sig = ("0" if sig[0] != "0" else "1") + sig[1:]
    tampered = key.rsplit(".", 1)[0] + "." + mangled_sig
    with pytest.raises(InvalidLicenseError):
        manager.validate(tampered)

    # Tamper the payload body.
    body, sig = key.rsplit(".", 1)
    body_flipped = "A" + body[1:] if body[0] != "A" else "B" + body[1:]
    with pytest.raises(InvalidLicenseError):
        manager.validate(f"{body_flipped}.{sig}")


def test_signatures_differ_across_secrets() -> None:
    a = LicenseManager("secret-A").create("k", tier=FREE)
    b = LicenseManager("secret-B").create("k", tier=FREE)
    assert a != b  # different signing keys => different signatures


def test_unknown_tier_rejected(manager: LicenseManager) -> None:
    with pytest.raises(ValueError):
        manager.create("x", tier="ULTRA")


def test_exceed_raises_helper(manager: LicenseManager) -> None:
    """LicenseLimitExceeded is available for callers wanting throwing enforcers."""
    key = manager.create("acme-free", tier=FREE)
    with pytest.raises(LicenseLimitExceeded):
        if not manager.broker_enforce(key, 12):
            raise LicenseLimitExceeded("12 builders exceed FREE limit")


# ---------------------------------------------------------------------------
# B1 — auth tokens
# ---------------------------------------------------------------------------


def test_issue_and_verify_token() -> None:
    am = AuthManager()
    token = am.issue_token("tenant-42", "broker:submit")
    assert isinstance(token, str) and len(token) >= 32

    claims = am.verify_token(token)
    assert claims == {"tenant": "tenant-42", "scope": "broker:submit"}


def test_issue_and_verify_module_level() -> None:
    token = issue_token("tenant-7", "read")
    assert verify_token(token) == {"tenant": "tenant-7", "scope": "read"}


def test_verify_rejects_tampered_token() -> None:
    am = AuthManager()
    token = am.issue_token("tenant-9", "write")

    # Flip one character anywhere in the token.
    tampered = ("0" if token[0] != "0" else "1") + token[1:]
    assert tampered != token
    with pytest.raises(InvalidTokenError):
        am.verify_token(tampered)


def test_verify_rejects_unknown_token() -> None:
    am = AuthManager()
    with pytest.raises(InvalidTokenError):
        am.verify_token("totally-made-up-token-value")


def test_verify_rejects_empty_token() -> None:
    with pytest.raises(InvalidTokenError):
        AuthManager().verify_token("")


def test_expired_token_rejected() -> None:
    am = AuthManager(token_lifetime=-1)  # already expired at issue time
    token = am.issue_token("tenant-1", "read")
    with pytest.raises(ExpiredTokenError):
        am.verify_token(token)


def test_distinct_tokens_are_independent() -> None:
    am = AuthManager()
    t1 = am.issue_token("a", "x")
    t2 = am.issue_token("b", "y")
    assert t1 != t2
    assert am.verify_token(t1) == {"tenant": "a", "scope": "x"}
    assert am.verify_token(t2) == {"tenant": "b", "scope": "y"}
