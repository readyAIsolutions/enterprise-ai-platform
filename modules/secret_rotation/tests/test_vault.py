"""Tests for the master-class encrypted-at-rest secret vault (vault.py)."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest
from enterprise.modules.secret_rotation.secret_rotation import hash_secret
from enterprise.modules.secret_rotation.vault import (
    RotationScheduler,
    SecretNotFoundError,
    SecretVault,
    VaultFacade,
    VaultIntegrityError,
    decrypt_blob,
    derive_keys,
    encrypt_blob,
)

# Low PBKDF2 cost keeps the suite fast while still exercising the real path.
FAST = 2000
MASTER = "correct-horse-battery-staple"


def make_vault(tmp_path: Path, master: str = MASTER) -> SecretVault:
    return SecretVault(tmp_path / "vault.db", master, iterations=FAST)


def make_facade(tmp_path: Path, master: str = MASTER) -> VaultFacade:
    return VaultFacade(tmp_path / "vault.db", master, iterations=FAST)


# ── low-level crypto ─────────────────────────────────────────────────────


def test_derive_keys_deterministic_and_split() -> None:
    e1, m1 = derive_keys(MASTER, b"saltbytes1234567", FAST)
    e2, m2 = derive_keys(MASTER, b"saltbytes1234567", FAST)
    assert e1 == e2
    assert m1 == m2
    assert len(e1) == 32
    assert len(m1) == 32
    assert e1 != m1


def test_encrypt_decrypt_roundtrip_and_secrets() -> None:
    blob = encrypt_blob(b"top secret", MASTER, FAST)
    assert decrypt_blob(blob, MASTER, FAST) == b"top secret"
    # The plaintext must never appear inside the blob/ciphertext.
    assert b"top secret" not in blob
    # A different salt/iv yields a different blob each time.
    assert blob != encrypt_blob(b"top secret", MASTER, FAST)


def test_encrypt_decrypt_wrong_master_key_raises() -> None:
    blob = encrypt_blob(b"secret", MASTER, FAST)
    with pytest.raises(VaultIntegrityError):
        decrypt_blob(blob, "wrong-master", FAST)


# ── SecretVault: put/get round-trip, encrypted-at-rest ─────────────────


def test_put_get_roundtrip(tmp_path: Path) -> None:
    v = make_vault(tmp_path)
    v.put("db_pass", "S3cret!")
    assert v.get("db_pass") == "S3cret!"
    assert v.has("db_pass")
    v.close()


def test_raw_db_has_no_plaintext(tmp_path: Path) -> None:
    db = tmp_path / "vault.db"
    v = SecretVault(db, MASTER, iterations=FAST)
    v.put("api_key", "SUPERSECRETPLAINTEXT123456")
    v.close()
    raw = db.read_bytes()
    assert b"SUPERSECRETPLAINTEXT123456" not in raw
    # Even the searchable sqlite text is ciphertext only.
    conn = sqlite3.connect(db)
    blob = conn.execute("SELECT blob FROM secrets WHERE name='api_key'").fetchone()[0]
    conn.close()
    assert b"SUPERSECRETPLAINTEXT123456" not in bytes(blob)


def test_get_wrong_master_key_fails(tmp_path: Path) -> None:
    v = make_vault(tmp_path)
    v.put("k", "v")
    with pytest.raises(VaultIntegrityError):
        v.get("k", master_key="attacker-key")
    v.close()


def test_get_detects_tampered_blob(tmp_path: Path) -> None:
    db = tmp_path / "vault.db"
    v = SecretVault(db, MASTER, iterations=FAST)
    v.put("k", "v")
    v.close()
    conn = sqlite3.connect(db)
    blob = bytearray(conn.execute("SELECT blob FROM secrets WHERE name='k'").fetchone()[0])
    blob[40] ^= 0xFF  # flip one ciphertext byte
    conn.execute("UPDATE secrets SET blob=? WHERE name='k'", (bytes(blob),))
    conn.commit()
    conn.close()
    v2 = SecretVault(db, MASTER, iterations=FAST)
    with pytest.raises(VaultIntegrityError):
        v2.get("k")
    v2.close()


def test_get_missing_raises(tmp_path: Path) -> None:
    v = make_vault(tmp_path)
    with pytest.raises(SecretNotFoundError):
        v.get("nope")
    v.close()


def test_put_overwrite_updates(tmp_path: Path) -> None:
    v = make_vault(tmp_path)
    v.put("k", "old-value")
    v.put("k", "new-value")
    assert v.get("k") == "new-value"
    assert len(v.list()) == 1
    v.close()


def test_list_and_delete(tmp_path: Path) -> None:
    v = make_vault(tmp_path)
    v.put("a", "1")
    v.put("b", "2")
    names = {e["name"] for e in v.list()}
    assert names == {"a", "b"}
    assert v.delete("a") is True
    assert v.delete("a") is False
    assert {e["name"] for e in v.list()} == {"b"}
    with pytest.raises(SecretNotFoundError):
        v.get("a")
    v.close()


def test_vault_rotate_generates_new_secret(tmp_path: Path) -> None:
    v = make_vault(tmp_path)
    v.put("k", "old-secret")
    old = v.get("k")
    v.rotate("k")
    new = v.get("k")
    assert new != old
    assert new  # generated non-empty
    v.close()


def test_vault_rotate_hash_kind_stores_hash_only(tmp_path: Path) -> None:
    v = make_vault(tmp_path)
    v.put("k", "old", kind="hash")
    assert v.get("k") == hash_secret("old")
    db = tmp_path / "vault.db"
    blob = sqlite3.connect(db).execute("SELECT blob FROM secrets WHERE name='k'").fetchone()[0]
    assert b"old" not in bytes(blob)
    before = v.get("k")
    v.rotate("k")
    after = v.get("k")
    # hash-only mode: stored payload is a 64-char hex SHA-256, changed by rotation
    assert len(after) == 64
    assert all(c in "0123456789abcdef" for c in after)
    assert after != before
    assert b"old" not in bytes(
        sqlite3.connect(db).execute("SELECT blob FROM secrets WHERE name='k'").fetchone()[0]
    )
    v.close()


# ── RotationScheduler ───────────────────────────────────────────────────


def test_due_for_rotation(tmp_path: Path) -> None:
    f = make_facade(tmp_path)
    f.put("k", "v")
    f.set_policy("k", interval_secs=100.0, last_rotated=0.0)
    assert f.due_for_rotation("k", now=50.0) is False
    assert f.due_for_rotation("k", now=100.0) is True
    assert f.due_for_rotation("k", now=150.0) is True
    f.close()


def test_rotation_generates_new_and_updates_due(tmp_path: Path) -> None:
    f = make_facade(tmp_path)
    f.put("k", "old")
    f.scheduler.set_policy("k", interval_secs=100.0, last_rotated=0.0)
    # At t=120 it is due.
    res = f.rotate("k", now=120.0)
    new_secret = res["new_secret"]
    assert f.get("k") == new_secret
    # last_rotated bumped to 120 => not due immediately at 120.
    assert f.due_for_rotation("k", now=120.0) is False
    assert f.due_for_rotation("k", now=220.0) is True
    f.close()


def test_rotation_scheduler_rotate(tmp_path: Path) -> None:
    v = make_vault(tmp_path)
    sch = RotationScheduler(v)
    v.put("k", "old")
    sch.set_policy("k", 100.0, last_rotated=0.0)
    assert sch.due_for_rotation("k", now=200.0) is True
    res = sch.rotate("k")
    assert v.get("k") == res["new_secret"]
    v.close()


# ── AccessAudit + integrity ─────────────────────────────────────────────


def test_audit_logs_put_get_rotate(tmp_path: Path) -> None:
    f = make_facade(tmp_path, master=MASTER)
    f.put("k", "v", actor="alice")
    f.get("k", actor="bob")
    f.rotate("k", actor="carol")
    actions = [e["action"] for e in f.audit_entries()]
    assert actions == ["put", "get", "rotate"]
    actors = [e["actor"] for e in f.audit_entries()]
    assert actors == ["alice", "bob", "carol"]
    assert all(e["secret_name"] == "k" for e in f.audit_entries())
    f.close()


def test_audit_hash_chain_integrity(tmp_path: Path) -> None:
    f = make_facade(tmp_path)
    f.put("a", "1")
    f.put("b", "2")
    f.get("a")
    assert f.audit_verify()["valid"] is True
    assert f.audit_verify()["entries"] == 3
    f.close()


def test_audit_detects_tampering(tmp_path: Path) -> None:
    db = tmp_path / "vault.db"
    f = VaultFacade(db, MASTER, iterations=FAST)
    f.put("a", "1")
    f.put("b", "2")
    f.close()
    # Tamper with an existing audit row (rewrite an action in place).
    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE audit_log SET entry_hash='deadbeef' "
        "WHERE action='put' AND id=(SELECT MIN(id) FROM audit_log)"
    )
    conn.commit()
    conn.close()
    f2 = VaultFacade(db, MASTER, iterations=FAST)
    report = f2.audit_verify()
    assert report["valid"] is False
    assert report["broken_at"] == 0
    f2.close()


def test_audit_append_only(tmp_path: Path) -> None:
    f = make_facade(tmp_path)
    f.put("a", "1")
    n1 = f.audit.count()
    f.get("a")
    f.delete("a")
    assert f.audit.count() == n1 + 2  # get + delete appended
    f.close()


def test_delete_is_audited(tmp_path: Path) -> None:
    f = make_facade(tmp_path)
    f.put("k", "v")
    assert f.delete("k") is True
    assert [e["action"] for e in f.audit_entries()] == ["put", "delete"]
    assert f.delete("k") is False
    assert len(f.audit_entries()) == 2
    f.close()


# ── VaultFacade lifecycle / persistence ────────────────────────────────


def test_facade_persists_across_reopen(tmp_path: Path) -> None:
    db = tmp_path / "vault.db"
    f = VaultFacade(db, MASTER, iterations=FAST)
    f.put("k", "durable-secret")
    f.rotate("k")
    f.close()
    f2 = VaultFacade(db, MASTER, iterations=FAST)
    assert f2.get("k")  # decryptable again with the same master key
    assert f2.audit_verify()["valid"] is True
    f2.close()


def test_facade_wrong_master_on_reopen_fails(tmp_path: Path) -> None:
    db = tmp_path / "vault.db"
    f = VaultFacade(db, MASTER, iterations=FAST)
    f.put("k", "v")
    f.close()
    f2 = VaultFacade(db, "different-master", iterations=FAST)
    with pytest.raises(VaultIntegrityError):
        f2.get("k")
    f2.close()


def test_create_vault_facade_factory() -> None:
    import os
    import tempfile

    from enterprise.modules.secret_rotation import create_vault_facade

    with tempfile.TemporaryDirectory() as d:
        f = create_vault_facade(os.path.join(d, "v.db"), MASTER, {"iterations": FAST})  # noqa: PTH118  # plugin API expects os interop
        f.put("k", "v")
        assert f.get("k") == "v"
        assert f.audit_verify()["valid"] is True
        f.close()
