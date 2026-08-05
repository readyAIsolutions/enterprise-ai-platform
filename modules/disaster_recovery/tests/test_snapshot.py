"""
Real snapshot/restore engine tests for the disaster_recovery module.

These exercise the REAL backup executor (SnapshotEngine): every snapshot is a
genuine directory archived to a tar.gz, every number (size, n_files, digests)
reflects actual bytes on disk. We also cover encrypted (XOR+HMAC) snapshots,
tamper detection, manifest hash-chain integrity, and the BackupManager
integration.

No destructive operations occur: all work happens inside pytest tmp dirs.
"""

import gzip
import hashlib
import io
import json
import os
import sys
import tarfile

import pytest

sys.path.insert(0, "/home/hunter/Desktop/Enterprise Builder")

from enterprise.modules.disaster_recovery.snapshot import (
    SnapshotEngine,
    Snapshot,
    ManifestEntry,
    RestoreReport,
    snapshot_to_dict,
    _file_sha256,
)
from enterprise.modules.disaster_recovery.backup import BackupManager, BackupType


# --------------------------------------------------------------------------
# Fixtures / helpers
# --------------------------------------------------------------------------

def _make_tree(root: str, files: dict, subdirs: list = None) -> str:
    """Create a real directory tree. ``files`` maps rel-path -> bytes/str."""
    for sub in subdirs or []:
        os.makedirs(os.path.join(root, sub), exist_ok=True)
    for rel, content in files.items():
        full = os.path.join(root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        if isinstance(content, bytes):
            with open(full, "wb") as fh:
                fh.write(content)
        else:
            with open(full, "w") as fh:
                fh.write(content)
    return root


@pytest.fixture
def sample_tree(tmp_path):
    """A small but real tree with known content and sizes."""
    payload = b"x" * 2048
    txt = "hello ENI disaster recovery\n"
    return _make_tree(
        str(tmp_path / "src"),
        {
            "a.txt": txt,
            "sub/b.bin": payload,
            "sub/deep/c.dat": os.urandom(4096),
            "empty.txt": "",
        },
        subdirs=["sub", "sub/deep", "empty_dir"],
    )


# --------------------------------------------------------------------------
# create_snapshot — real archive, real numbers
# --------------------------------------------------------------------------

def test_create_snapshot_produces_real_file(tmp_path):
    src = _make_tree(str(tmp_path / "src"), {"a.txt": "hello"})
    tgt = str(tmp_path / "snaps")
    eng = SnapshotEngine()
    snap = eng.create_snapshot(src, tgt, name="first")
    assert isinstance(snap, Snapshot)
    assert snap.id
    assert snap.name == "first"
    assert os.path.exists(snap.path)
    # Archive is a real gzip tar with the manifest + a.txt inside.
    with gzip.open(snap.path, "rb") as fh:
        raw = io.BytesIO(fh.read())
    with tarfile.open(fileobj=raw, mode="r") as tf:
        names = {m.name for m in tf.getmembers()}
    assert "a.txt" in names
    assert "._eni_manifest.json" in names


def test_snapshot_counts_real_files(sample_tree, tmp_path):
    eng = SnapshotEngine()
    snap = eng.create_snapshot(sample_tree, str(tmp_path / "snaps"))
    # Real count of regular files: a.txt, sub/b.bin, sub/deep/c.dat, empty.txt = 4
    assert snap.n_files == 4
    # Real total original bytes.
    expected = (
        2048
        + len("hello ENI disaster recovery\n")
        + 4096
        + 0
    )
    assert snap.total_size == expected
    # Archive on disk is real and non-trivial.
    assert snap.size > 0
    assert snap.size == os.path.getsize(snap.path)


def test_snapshot_manifest_has_real_hashes(sample_tree, tmp_path):
    eng = SnapshotEngine()
    snap = eng.create_snapshot(sample_tree, str(tmp_path / "snaps"))
    entries = {e["path"]: e for e in snap.manifest["entries"] if e["entry_type"] == "file"}
    assert entries["a.txt"]["sha256"] == _file_sha256(os.path.join(sample_tree, "a.txt"))
    assert entries["sub/b.bin"]["sha256"] == _file_sha256(
        os.path.join(sample_tree, "sub", "b.bin")
    )
    assert entries["a.txt"]["size"] == len("hello ENI disaster recovery\n")


def test_snapshot_includes_directories_and_empty_dir(sample_tree, tmp_path):
    eng = SnapshotEngine()
    snap = eng.create_snapshot(sample_tree, str(tmp_path / "snaps"))
    types = {e["path"]: e["entry_type"] for e in snap.manifest["entries"]}
    assert types["empty_dir"] == "dir"
    assert types["sub"] == "dir"
    assert types["sub/deep"] == "dir"


def test_create_snapshot_missing_source_raises(tmp_path):
    eng = SnapshotEngine()
    with pytest.raises(ValueError):
        eng.create_snapshot(str(tmp_path / "does_not_exist"), str(tmp_path / "snaps"))


def test_create_snapshot_auto_name_and_unique_ids(tmp_path):
    src = _make_tree(str(tmp_path / "src"), {"f": "data"})
    eng = SnapshotEngine()
    s1 = eng.create_snapshot(src, str(tmp_path / "s1"))
    s2 = eng.create_snapshot(src, str(tmp_path / "s1"))
    assert s1.id != s2.id
    assert s1.path != s2.path
    assert s1.name  # auto-generated


# --------------------------------------------------------------------------
# list_snapshots
# --------------------------------------------------------------------------

def test_list_snapshots_returns_snapshot_metadata(tmp_path):
    src = _make_tree(str(tmp_path / "src"), {"f.txt": "alpha"})
    tgt = str(tmp_path / "snaps")
    eng = SnapshotEngine()
    snap = eng.create_snapshot(src, tgt, name="snapA")
    lst = eng.list_snapshots(tgt)
    assert len(lst) == 1
    loaded = lst[0]
    assert loaded.id == snap.id
    assert loaded.name == "snapA"
    assert loaded.n_files == snap.n_files == 1
    assert loaded.size == snap.size
    assert loaded.path == snap.path


def test_list_snapshots_multiple_newest_first(tmp_path):
    src = _make_tree(str(tmp_path / "src"), {"f": "data"})
    tgt = str(tmp_path / "snaps")
    eng = SnapshotEngine()
    s1 = eng.create_snapshot(src, tgt, name="old")
    s2 = eng.create_snapshot(src, tgt, name="new")
    lst = eng.list_snapshots(tgt)
    assert {s.name for s in lst} == {"old", "new"}
    # Newest first.
    assert lst[0].name == "new"


def test_list_snapshots_empty_dir(tmp_path):
    eng = SnapshotEngine()
    assert eng.list_snapshots(str(tmp_path / "nonexistent_or_empty")) == []


# --------------------------------------------------------------------------
# restore_snapshot — round-trip
# --------------------------------------------------------------------------

def test_restore_roundtrip_byte_identical(sample_tree, tmp_path):
    eng = SnapshotEngine()
    snap = eng.create_snapshot(sample_tree, str(tmp_path / "snaps"))
    dest = str(tmp_path / "restored")
    report = eng.restore_snapshot(snap, dest)
    assert isinstance(report, RestoreReport)
    assert report.status == "ok"
    assert report.failed == 0
    assert report.verified == report.restored == 4
    # Every restored file is byte-identical to the source.
    for rel in ("a.txt", "sub/b.bin", "sub/deep/c.dat", "empty.txt"):
        orig = open(os.path.join(sample_tree, rel), "rb").read()
        back = open(os.path.join(dest, rel), "rb").read()
        assert orig == back
    # Hashes are verified real.
    assert _file_sha256(os.path.join(dest, "sub/b.bin")) == _file_sha256(
        os.path.join(sample_tree, "sub/b.bin")
    )


def test_restore_creates_directories(sample_tree, tmp_path):
    eng = SnapshotEngine()
    snap = eng.create_snapshot(sample_tree, str(tmp_path / "snaps"))
    dest = str(tmp_path / "restored")
    eng.restore_snapshot(snap, dest)
    assert os.path.isdir(os.path.join(dest, "sub", "deep"))
    assert os.path.isdir(os.path.join(dest, "empty_dir"))


def test_restore_overwrites_existing(tmp_path):
    src = _make_tree(str(tmp_path / "src"), {"f.txt": "v1"})
    eng = SnapshotEngine()
    snap = eng.create_snapshot(src, str(tmp_path / "snaps"))
    dest = str(tmp_path / "restored")
    os.makedirs(dest)
    with open(os.path.join(dest, "f.txt"), "w") as fh:
        fh.write("STALE")
    report = eng.restore_snapshot(snap, dest)
    assert report.status == "ok"
    assert open(os.path.join(dest, "f.txt")).read() == "v1"


def test_restore_report_totals_header(sample_tree, tmp_path):
    eng = SnapshotEngine()
    snap = eng.create_snapshot(sample_tree, str(tmp_path / "snaps"))
    r = eng.restore_snapshot(snap, str(tmp_path / "restored"))
    d = r.to_dict()
    assert d["status"] == "ok"
    assert d["snapshot_id"] == snap.id
    assert r.total_bytes == snap.total_size


# --------------------------------------------------------------------------
# verify — real recomputation + tamper detection
# --------------------------------------------------------------------------

def test_verify_ok(sample_tree, tmp_path):
    eng = SnapshotEngine()
    snap = eng.create_snapshot(sample_tree, str(tmp_path / "snaps"))
    res = eng.verify(snap)
    assert res["status"] == "ok"
    assert res["chain_ok"] is True
    assert res["matches"] == res["checked"] == 4


def test_verify_corrupt_content_byte_flip(sample_tree, tmp_path):
    eng = SnapshotEngine()
    snap = eng.create_snapshot(sample_tree, str(tmp_path / "snaps"))
    data = bytearray(open(snap.path, "rb").read())
    idx = min(len(data) - 100, len(data) // 2)
    data[idx] ^= 0xFF
    with open(snap.path, "wb") as fh:
        fh.write(bytes(data))
    assert eng.verify(snap)["status"] == "corrupt"


def test_verify_corrupt_missing_member(sample_tree, tmp_path):
    """Deleting a whole file member from the tar must be flagged corrupt."""
    eng = SnapshotEngine()
    snap = eng.create_snapshot(sample_tree, str(tmp_path / "snaps"))
    # Rebuild a copy of the archive without a.txt, keep manifest as-is.
    buf = io.BytesIO()
    with gzip.open(snap.path, "rb") as fh:
        raw = fh.read()
    members = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r") as tf:
        for m in tf.getmembers():
            if m.name == "a.txt":
                continue
            members[m.name] = m
        out = io.BytesIO()
        with tarfile.open(fileobj=out, mode="w", format=tarfile.PAX_FORMAT) as tf2:
            for name, m in members.items():
                if m.isfile():
                    data = tf.extractfile(m).read()
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    info.type = m.type
                    tf2.addfile(info, io.BytesIO(data))
                else:
                    tf2.addfile(m)
    with gzip.open(snap.path, "wb") as fh:
        fh.write(out.getvalue())
    assert eng.verify(snap)["status"] == "corrupt"


def test_verify_corrupt_manifest_chain_flip(sample_tree, tmp_path):
    """Tampering with a manifest file hash must be flagged corrupt."""
    eng = SnapshotEngine()
    snap = eng.create_snapshot(sample_tree, str(tmp_path / "snaps"))
    # Rebuild the archive with a tampered manifest (one entry's sha256 swapped
    # to a bogus digest) while keeping every real file byte identical.
    from enterprise.modules.disaster_recovery.snapshot import (
        _MANIFEST_MEMBER, _load_manifest,
    )
    with open(snap.path, "rb") as fh:
        archive_bytes = fh.read()  # raw gzipped archive
    manifest = _load_manifest(archive_bytes)
    tampered = json.loads(json.dumps(manifest))
    for e in tampered["entries"]:
        if e["entry_type"] == "file":
            e["sha256"] = "0" * 64  # bogus digest
            break
    # Rebuild tar with the same members but the tampered manifest.
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w", format=tarfile.PAX_FORMAT) as tf2:
        man_raw = json.dumps(tampered, sort_keys=True).encode()
        man_info = tarfile.TarInfo(_MANIFEST_MEMBER)
        man_info.size = len(man_raw)
        tf2.addfile(man_info, io.BytesIO(man_raw))
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as tf:
            for m in tf.getmembers():
                if m.name == _MANIFEST_MEMBER:
                    continue
                src = tf.extractfile(m)
                data = src.read() if src is not None else b""
                info = tarfile.TarInfo(m.name)
                info.size = len(data)
                info.type = m.type
                info.mtime = m.mtime
                tf2.addfile(info, io.BytesIO(data))
    with gzip.open(snap.path, "wb") as fh:
        fh.write(out.getvalue())
    # The stored (tampered) hash no longer matches real file content -> corrupt.
    assert eng.verify(snap)["status"] == "corrupt"


def test_verify_corrupt_on_unreadable_archive(tmp_path):
    """A totally mangled (non-gzip) archive must report corrupt, not crash."""
    eng = SnapshotEngine()
    src = _make_tree(str(tmp_path / "src"), {"f": "data"})
    snap = eng.create_snapshot(src, str(tmp_path / "snaps"))
    with open(snap.path, "wb") as fh:
        fh.write(b"NOT A SNAPSHOT AT ALL" * 10)
    res = eng.verify(snap)
    assert res["status"] == "corrupt"


# --------------------------------------------------------------------------
# Encryption (XOR + HMAC) — honest, labelled obfuscation + real HMAC integrity
# --------------------------------------------------------------------------

KEY = b"correct horse battery staple"


def test_encrypted_snapshot_is_transformed_on_disk(sample_tree, tmp_path):
    eng = SnapshotEngine()
    snap = eng.create_snapshot(
        sample_tree, str(tmp_path / "snaps"), name="enc", encrypt_key=KEY
    )
    assert snap.encrypted is True
    assert snap.path.endswith(".eni")
    on_disk = open(snap.path, "rb").read()
    assert b"hello ENI disaster recovery" not in on_disk  # obfuscated
    # xor transform is not plaintext
    assert not on_disk.startswith(b"\x1f\x8b")  # not a raw gzip header


def test_encrypted_verify_with_key_ok(sample_tree, tmp_path):
    eng = SnapshotEngine()
    snap = eng.create_snapshot(sample_tree, str(tmp_path / "snaps"), encrypt_key=KEY)
    assert eng.verify(snap, key=KEY)["status"] == "ok"


def test_encrypted_list_requires_key(sample_tree, tmp_path):
    tgt = str(tmp_path / "snaps")
    eng = SnapshotEngine()
    eng.create_snapshot(sample_tree, tgt, encrypt_key=KEY)
    # Without the key, list_snapshots skips the encrypted entry.
    assert SnapshotEngine().list_snapshots(tgt) == []
    # With the key (engine-level default), it is discoverable.
    led = SnapshotEngine(key=KEY).list_snapshots(tgt)
    assert len(led) == 1
    assert led[0].encrypted is True


def test_encrypted_wrong_key_raises(sample_tree, tmp_path):
    eng = SnapshotEngine()
    snap = eng.create_snapshot(sample_tree, str(tmp_path / "snaps"), encrypt_key=KEY)
    # Low-level reader raises on HMAC mismatch (wrong key / tampering).
    from enterprise.modules.disaster_recovery.snapshot import _read_archive
    with pytest.raises(ValueError):
        _read_archive(snap.path, b"wrong key")
    # High-level verify degrades to "corrupt" rather than crashing.
    assert eng.verify(snap, key=b"wrong key")["status"] == "corrupt"


def test_encrypted_restore_roundtrip(sample_tree, tmp_path):
    eng = SnapshotEngine()
    snap = eng.create_snapshot(sample_tree, str(tmp_path / "snaps"), encrypt_key=KEY)
    dest = str(tmp_path / "restored")
    report = eng.restore_snapshot(snap, dest, key=KEY)
    assert report.status == "ok"
    assert open(os.path.join(dest, "a.txt")).read() == "hello ENI disaster recovery\n"


def test_encrypted_tamper_detected_via_hmac(sample_tree, tmp_path):
    eng = SnapshotEngine()
    snap = eng.create_snapshot(sample_tree, str(tmp_path / "snaps"), encrypt_key=KEY)
    data = bytearray(open(snap.path, "rb").read())
    data[len(data) // 2] ^= 0xFF
    with open(snap.path, "wb") as fh:
        fh.write(bytes(data))
    # HMAC tag mismatch -> hard failure from the low-level reader,
    # and high-level verify reports corrupt.
    from enterprise.modules.disaster_recovery.snapshot import _read_archive
    with pytest.raises(ValueError):
        _read_archive(snap.path, KEY)
    assert eng.verify(snap, key=KEY)["status"] == "corrupt"


# --------------------------------------------------------------------------
# Manifest hash-chain integrity
# --------------------------------------------------------------------------

def test_manifest_chain_detects_reorder(sample_tree, tmp_path):
    eng = SnapshotEngine()
    snap = eng.create_snapshot(sample_tree, str(tmp_path / "snaps"))
    # Manually reorder entries in a rebuild and confirm chain_hash differs.
    entries = list(snap.manifest["entries"])
    assert len(entries) >= 2
    entries = entries[::-1]  # reorder
    running = hashlib.sha256(b"ENI-SNAPSHOT-CHAIN-v1").digest()
    for e in entries:
        running = hashlib.sha256(
            running + e["sha256"].encode() + str(e["size"]).encode() + e["path"].encode()
        ).digest()
    assert running.hex() != snap.manifest["chain_hash"]


def test_manifest_chain_stable_across_run(sample_tree, tmp_path):
    """Same input => same chain_hash (deterministic given identical content)."""
    eng = SnapshotEngine()
    s1 = eng.create_snapshot(sample_tree, str(tmp_path / "a"))
    s2 = eng.create_snapshot(sample_tree, str(tmp_path / "b"))
    assert s1.manifest["chain_hash"] == s2.manifest["chain_hash"]


# --------------------------------------------------------------------------
# Utility / lifecycle
# --------------------------------------------------------------------------

def test_snapshot_to_dict(sample_tree, tmp_path):
    eng = SnapshotEngine()
    snap = eng.create_snapshot(sample_tree, str(tmp_path / "snaps"))
    d = snapshot_to_dict(snap)
    assert d["id"] == snap.id
    assert d["n_files"] == 4
    assert d["total_size"] == snap.total_size
    assert d["created_at"] == snap.created_at


def test_snapshot_lifecycle_full(sample_tree, tmp_path):
    """End-to-end: create -> list -> verify -> restore -> verify restored."""
    eng = SnapshotEngine()
    tgt = str(tmp_path / "snaps")
    snap = eng.create_snapshot(sample_tree, tgt, name="lifecycle")
    listed = eng.list_snapshots(tgt)
    assert len(listed) == 1
    assert eng.verify(listed[0])["status"] == "ok"
    dest = str(tmp_path / "restored")
    report = eng.restore_snapshot(listed[0], dest)
    assert report.status == "ok"
    assert report.verified == 4
    # Restored tree is a genuine directory with correct content.
    assert open(os.path.join(dest, "a.txt")).read() == "hello ENI disaster recovery\n"


def test_snapshot_to_dict_encrypted(sample_tree, tmp_path):
    eng = SnapshotEngine()
    snap = eng.create_snapshot(
        sample_tree, str(tmp_path / "snaps"), encrypt_key=KEY
    )
    d = snapshot_to_dict(snap)
    assert d["encrypted"] is True


# --------------------------------------------------------------------------
# BackupManager integration (real snapshot when real source + store configured)
# --------------------------------------------------------------------------

def test_backupmanager_real_snapshot_integration(tmp_path):
    src = _make_tree(str(tmp_path / "src"), {"data.txt": "real backup payload"})
    store = str(tmp_path / "store")
    mgr = BackupManager()
    mgr.configure_policy("srv_full", BackupType.FULL, frequency_hours=24)
    mgr.configure_snapshot_store(store)
    record = mgr.execute_backup("srv_full", source_path=src)
    # Real snapshot was taken: record carries a real archive path + chain digest.
    assert record.snapshot_path
    assert os.path.exists(record.snapshot_path)
    assert len(record.checksum) == 64  # sha256 hex digest
    # Restore it back and confirm the original content survives.
    eng = SnapshotEngine()
    snap = eng.load(record.snapshot_path)
    assert eng.verify(snap)["status"] == "ok"
    dest = str(tmp_path / "restored")
    report = eng.restore_snapshot(snap, dest)
    assert report.status == "ok"
    assert open(os.path.join(dest, "data.txt")).read() == "real backup payload"


def test_backupmanager_fallback_without_real_store(tmp_path):
    """No snapshot store configured -> existing simulated-bookkeeping path."""
    mgr = BackupManager()
    mgr.configure_policy("daily", BackupType.FULL, frequency_hours=24)
    record = mgr.execute_backup("daily")  # no real source/store
    assert record.backup_id
    assert record.snapshot_path == ""
    # Original behavior preserved for existing callers/tests.
    assert mgr.verify_integrity(record.backup_id) is True
