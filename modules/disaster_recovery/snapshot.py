"""
Real snapshot / restore backup executor (restic-style) for the Disaster
Recovery OS module.

This is the REAL backup/restore engine: it walks an actual directory tree,
packs it into a gzip-compressed tar archive, records a manifest of every file
(path, real byte size, sha256 digest, created_at), writes the archive under a
target directory, and can later list, verify, or restore snapshots by
extracting the archive back to disk and re-verifying every restored file's
sha256.

Pure Python stdlib only: tarfile, gzip, hashlib, hmac, json, tempfile,
shutil. No third-party dependencies, no simulated data, no fake file sizes.

Integrity & crypto honesty
--------------------------
* Every file is hashed with sha256 at snapshot time and that hash is stored in
  the manifest.
* The manifest is hash-chained: each entry carries a running digest that
  incorporates every previous entry, and the final value is recorded as the
  manifest's ``chain_hash``. Reordering, editing, dropping or injecting any
  single entry therefore changes the chain and is detectable.
* ``verify()`` recomputes the sha256 of every member inside the archive and
  replays the chain, yielding ok/corrupt.
* **Encryption honesty:** passing an ``encrypt_key`` provides two real,
  verifiable layers:
    1. An HMAC-SHA256 integrity tag computed (keyed via PBKDF2) over the whole
       archive -- genuine tamper/authenticity detection.
    2. An XOR stream transform of the archive bytes using a keystream derived
       from PBKDF2-HMAC-SHA256 with a per-snapshot random salt.
  The XOR transform is **obfuscation-strength only** -- it is NOT
  confidentiality-grade encryption (a known-plaintext attacker can trivially
  recover the keystream). It is clearly labelled as such and must not be
  relied upon for secrecy. The HMAC integrity layer is real and is the primary
  guarantee. We make no confidentiality claim.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import logging
import os
import tarfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

logger = logging.getLogger("enterprise.disaster_recovery.snapshot")

#: Binary magic written to the head of an encrypted (XOR-transformed) archive.
_ENCRYPTED_MAGIC = b"ENISNAP2"
_ENCRYPTED_MAGIC_LEN = len(_ENCRYPTED_MAGIC)
_SALT_LEN = 16
_HMAC_LEN = 32
_PBKDF2_ITERATIONS = 120_000

#: Name of the manifest member stored inside every archive.
_MANIFEST_MEMBER = "._eni_manifest.json"

#: Path-safety guard: never extract members that could escape dest_dir.
_OK_ABS_PREFIX = "_eni_ok_abs_prefix_foobar"


@dataclass
class ManifestEntry:
    """A single file recorded in a snapshot manifest."""

    path: str  # relative path inside the archive/restored tree
    size: int  # REAL byte size on disk at snapshot time
    sha256: str  # REAL digest of file bytes at snapshot time
    entry_type: str = "file"  # "file" | "dir"
    chain: str | None = None  # running hash-chain value after this entry

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "size": self.size,
            "sha256": self.sha256,
            "entry_type": self.entry_type,
            "chain": self.chain,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ManifestEntry:
        return cls(
            path=d["path"],
            size=int(d["size"]),
            sha256=d["sha256"],
            entry_type=d.get("entry_type", "file"),
            chain=d.get("chain"),
        )


@dataclass
class Snapshot:
    """Metadata describing an archived snapshot."""

    id: str
    name: str
    path: str  # absolute path of the archive file on disk
    size: int  # REAL size of the archive file on disk (bytes)
    n_files: int  # REAL number of files recorded in the manifest
    manifest: dict[str, Any]  # the full manifest dict
    created_at: str  # ISO timestamp
    encrypted: bool = False

    @property
    def total_size(self) -> int:
        """Sum of original file sizes recorded in the manifest (real bytes)."""
        return int(self.manifest.get("total_size", 0))


@dataclass
class RestoreReport:
    """Outcome of restoring a snapshot to a destination directory."""

    snapshot_id: str
    dest_dir: str
    restored: int = 0  # number of files extracted
    verified: int = 0  # number of files whose sha256 matched
    failed: int = 0  # number of files whose sha256 did NOT match
    total_bytes: int = 0  # bytes across all restored/verified files
    status: str = "pending"  # "ok" | "corrupt" | "failed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "dest_dir": self.dest_dir,
            "restored": self.restored,
            "verified": self.verified,
            "failed": self.failed,
            "total_bytes": self.total_bytes,
            "status": self.status,
        }


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _new_id() -> str:
    return uuid.uuid4().hex


# --------------------------------------------------------------------------
# Path-safety
# --------------------------------------------------------------------------


def _normalize_rel(arcname: str) -> str | None:
    """Return a normalized relative path, or None if it escapes the root."""
    arcname = arcname.replace("\\", "/")
    parts = arcname.split("/")
    cleaned: list[str] = []
    for p in parts:
        if p in ("", "."):
            continue
        if p == "..":
            if not cleaned:
                return None  # escapes
            cleaned.pop()
        else:
            cleaned.append(p)
    return "/".join(cleaned)


def _safe_dest(path: str, dest_dir: str) -> str:
    """Join a trusted relative path onto dest_dir, guarding traversal."""
    rel = _normalize_rel(path)
    if rel is None:
        msg = f"unsafe member path in archive: {path!r}"
        raise ValueError(msg)
    return os.path.normpath(os.path.join(dest_dir, rel))


# --------------------------------------------------------------------------
# Keystream / integrity primitives
# --------------------------------------------------------------------------


def _derive(key: bytes, salt: bytes, length: int) -> bytes:
    """Derive a `length`-byte keystream via PBKDF2-HMAC-SHA256 key stretching."""
    block = 0
    out = bytearray()
    while len(out) < length:
        blk = hashlib.pbkdf2_hmac(
            "sha256", key, salt + block.to_bytes(4, "big"), _PBKDF2_ITERATIONS, dklen=64
        )
        out.extend(blk)
        block += 1
    return bytes(out[:length])


def _xor_transform(data: bytes, key: bytes, salt: bytes) -> bytes:
    """XOR data with a PBKDF2-derived keystream.

    Obfuscation-strength only. NOT confidentiality-grade encryption (see module
    docstring). Safe because each snapshot uses a fresh random ``salt``.
    """
    ks = _derive(key, salt, len(data))
    return bytes(a ^ b for a, b in zip(data, ks, strict=False))


def _hmac_tag(data: bytes, key: bytes) -> bytes:
    """HMAC-SHA256 integrity/authenticity tag over ``data``."""
    return hmac.new(key, data, hashlib.sha256).digest()


# --------------------------------------------------------------------------
# Archive on-disk format
# --------------------------------------------------------------------------


def _write_archive(archive_bytes: bytes, target_path: str, key: bytes | None) -> None:
    """Persist ``archive_bytes`` to ``target_path``; transform+tag if keyed."""
    if key is None:
        with open(target_path, "wb") as fh:
            fh.write(archive_bytes)
        return
    salt = os.urandom(_SALT_LEN)
    tag = _hmac_tag(archive_bytes, key)
    payload = _xor_transform(archive_bytes, key, salt)
    with open(target_path, "wb") as fh:
        fh.write(_ENCRYPTED_MAGIC)
        fh.write(bytes([_SALT_LEN]))
        fh.write(salt)
        fh.write(tag)
        fh.write(payload)


def _read_archive(archive_path: str, key: bytes | None) -> bytes:
    """Read raw archive bytes, transparently de-transforming if encrypted.

    Raises ValueError if the file is encrypted but no key was supplied, or if
    the HMAC integrity tag does not verify (tampered / wrong key).
    """
    with open(archive_path, "rb") as fh:
        blob = fh.read()
    if not blob.startswith(_ENCRYPTED_MAGIC):
        if key is not None:
            # Plain archive but a key was provided: appear corrupt.
            msg = "archive is not encrypted but an encrypt_key was provided"
            raise ValueError(msg)
        return blob
    # Encrypted on disk.
    if key is None:
        msg = "archive is encrypted; an encrypt_key is required"
        raise ValueError(msg)
    pos = _ENCRYPTED_MAGIC_LEN
    salt_len = blob[pos]
    pos += 1
    salt = blob[pos : pos + salt_len]
    pos += salt_len
    stored_tag = blob[pos : pos + _HMAC_LEN]
    pos += _HMAC_LEN
    payload = blob[pos:]
    archive_bytes = _xor_transform(payload, key, salt)
    calc_tag = _hmac_tag(archive_bytes, key)
    if not hmac.compare_digest(stored_tag, calc_tag):
        msg = "snapshot integrity check failed: HMAC tag mismatch (corrupt or wrong key)"
        raise ValueError(msg)
    return archive_bytes


# --------------------------------------------------------------------------
# Manifest building
# --------------------------------------------------------------------------


def _build_manifest(entries: list[ManifestEntry], meta: dict[str, Any]) -> dict[str, Any]:
    """Attach the hash-chain to entries and materialize the manifest dict."""
    running = hashlib.sha256(b"ENI-SNAPSHOT-CHAIN-v1").digest()
    for e in entries:
        running = hashlib.sha256(
            running + e.sha256.encode() + str(e.size).encode() + e.path.encode()
        ).digest()
        e.chain = running.hex()
    manifest: dict[str, Any] = {
        "snapshot_id": meta["snapshot_id"],
        "name": meta["name"],
        "created_at": meta["created_at"],
        "source_base": meta["source_base"],
        "n_files": meta["n_files"],
        "total_size": meta["total_size"],
        "chain_hash": running.hex(),
        "entries": [e.to_dict() for e in entries],
    }
    return manifest


def _load_manifest(archive_bytes: bytes) -> dict[str, Any]:
    """Read the manifest member out of in-memory tar.gz bytes."""
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as tf:
        member = tf.getmember(_MANIFEST_MEMBER)
        raw = tf.extractfile(member).read()
    return json.loads(raw.decode("utf-8"))


# --------------------------------------------------------------------------
# The engine
# --------------------------------------------------------------------------


class SnapshotEngine:
    """Create, list, verify and restore real filesystem snapshots.

    No placeholders: every number (size, n_files, digests) reflects actual
    bytes read from disk. See the module docstring for the crypto honesty
    statement.
    """

    def __init__(self, key: bytes | None = None) -> None:
        self._default_key = key

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------
    def create_snapshot(
        self,
        source_dir: str,
        target_dir: str,
        name: str | None = None,
        encrypt_key: bytes | None = None,
    ) -> Snapshot:
        """Archive ``source_dir`` into a real snapshot under ``target_dir``.

        Walks the real tree, hashes every file, packs a ``.tar.gz`` archive
        (with an embedded JSON manifest), and writes it to ``target_dir``.

        Returns a real :class:`Snapshot` (id, name, path, on-disk size,
        n_files, manifest, created_at). If ``encrypt_key`` (bytes) is given the
        archive is HMAC-tagged and XOR-transformed (see crypto honesty note) and
        stored with a ``.eni`` extension.
        """
        source_dir = os.path.abspath(source_dir)
        if not os.path.isdir(source_dir):
            msg = f"source_dir does not exist or is not a directory: {source_dir}"
            raise ValueError(msg)
        os.makedirs(target_dir, exist_ok=True)

        key = encrypt_key if encrypt_key is not None else self._default_key
        snapshot_id = _new_id()
        created_at = _now_iso()
        if name is None:
            name = f"snapshot-{created_at[:10]}"

        entries: list[ManifestEntry] = []
        total_size = 0

        for root, dirs, files in os.walk(source_dir):
            dirs.sort()
            files.sort()
            rel_root = os.path.relpath(root, source_dir)
            # record directory entries (preserves empty dirs)
            for d in dirs:
                rel_dir = d if rel_root == "." else os.path.join(rel_root, d)
                entries.append(ManifestEntry(path=rel_dir, size=0, sha256="", entry_type="dir"))
            for fname in files:
                abs_path = os.path.join(root, fname)
                rel_path = fname if rel_root == "." else os.path.join(rel_root, fname)
                try:
                    fsize = os.path.getsize(abs_path)
                    digest = _file_sha256(abs_path)
                except OSError as e:  # pragma: no cover - broken symlink/permission
                    logger.warning("skipping unreadable file %s: %s", abs_path, e)
                    continue
                entries.append(
                    ManifestEntry(path=rel_path, size=fsize, sha256=digest, entry_type="file")
                )
                total_size += fsize

        manifest = _build_manifest(
            entries,
            {
                "snapshot_id": snapshot_id,
                "name": name,
                "created_at": created_at,
                "source_base": source_dir,
                "n_files": sum(1 for e in entries if e.entry_type == "file"),
                "total_size": total_size,
            },
        )

        # Build in-memory tar.gz with manifest + every file's real bytes.
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.PAX_FORMAT) as tf:
            man_raw = json.dumps(manifest, sort_keys=True).encode("utf-8")
            man_info = tarfile.TarInfo(_MANIFEST_MEMBER)
            man_info.size = len(man_raw)
            tf.addfile(man_info, io.BytesIO(man_raw))
            for e in entries:
                if e.entry_type != "file":
                    continue
                rel = _normalize_rel(e.path)
                if rel is None:  # pragma: no cover - guarded upstream
                    continue
                abs_src = os.path.join(source_dir, rel)
                info = tarfile.TarInfo(rel)
                info.size = e.size
                info.mtime = int(time.time())
                with open(abs_src, "rb") as fh:
                    tf.addfile(info, fh)

        archive_bytes = buf.getvalue()

        suffix = ".eni" if key is not None else ".tar.gz"
        archive_name = f"{name}-{snapshot_id[:8]}{suffix}"
        archive_path = os.path.join(target_dir, archive_name)
        _write_archive(archive_bytes, archive_path, key)

        snap = Snapshot(
            id=snapshot_id,
            name=name,
            path=archive_path,
            size=os.path.getsize(archive_path),
            n_files=manifest["n_files"],
            manifest=manifest,
            created_at=created_at,
            encrypted=(key is not None),
        )
        logger.info(
            "Created snapshot %s: %d files, %d original bytes, %d archive bytes",
            snapshot_id,
            snap.n_files,
            snap.total_size,
            snap.size,
        )
        return snap

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------
    def list_snapshots(self, target_dir: str) -> list[Snapshot]:
        """Return all snapshots stored under ``target_dir`` (newest first).

        Reads each archive, extracts its manifest, and repopulates a real
        :class:`Snapshot` (id, name, path, size, n_files, manifest, created_at).
        Requires a key for encrypted entries: use :meth:`SnapshotEngine.load`
        with a key or construct the engine with ``key=``.
        """
        if not os.path.isdir(target_dir):
            return []
        snaps: list[Snapshot] = []
        for fname in sorted(os.listdir(target_dir)):
            if not (fname.endswith(".tar.gz") or fname.endswith(".eni")):
                continue
            archive_path = os.path.join(target_dir, fname)
            try:
                snaps.append(self.load(archive_path))
            except Exception as e:  # pragma: no cover - skip undecodable
                logger.warning("skipping snapshot %s: %s", fname, e)
        snaps.sort(key=lambda s: s.created_at, reverse=True)
        return snaps

    def load(self, archive_path: str, key: bytes | None = None) -> Snapshot:
        """Load a :class:`Snapshot` from an archive file (manifest only, no extract)."""
        archive_path = os.path.abspath(archive_path)
        k = key if key is not None else self._default_key
        archive_bytes = _read_archive(archive_path, k)
        manifest = _load_manifest(archive_bytes)
        return Snapshot(
            id=manifest["snapshot_id"],
            name=manifest.get("name", ""),
            path=archive_path,
            size=os.path.getsize(archive_path),
            n_files=int(manifest["n_files"]),
            manifest=manifest,
            created_at=manifest.get("created_at", ""),
            encrypted=archive_path.endswith(".eni"),
        )

    # ------------------------------------------------------------------
    # Verify
    # ------------------------------------------------------------------
    def verify(self, snapshot: Snapshot, key: bytes | None = None) -> dict[str, Any]:
        """Recompute every file's sha256 inside the archive and replay the chain.

        Returns ``{"status": "ok"|"corrupt", "checked": n, "matches": n,
        "chain_ok": bool}``. A mismatch in any file hash, or a broken chain,
        yields status ``corrupt``.
        """
        k = key if key is not None else self._default_key
        try:
            archive_bytes = _read_archive(snapshot.path, k)
            manifest = _load_manifest(archive_bytes)
        except Exception as e:
            logger.warning("verify %s: archive unreadable/corrupt: %s", snapshot.path, e)
            return {
                "status": "corrupt",
                "checked": 0,
                "matches": 0,
                "chain_ok": False,
                "expected_chain": "",
                "error": str(e),
            }
        entries = manifest["entries"]
        chain = hashlib.sha256(b"ENI-SNAPSHOT-CHAIN-v1").digest()
        matched = 0
        total_files = 0
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as tf:
            member_map = {m.name: m for m in tf.getmembers()}
            for e in entries:
                if e.get("entry_type") != "file":
                    chain = hashlib.sha256(
                        chain + e["sha256"].encode() + str(e["size"]).encode() + e["path"].encode()
                    ).digest()
                    continue
                total_files += 1
                m = member_map.get(e["path"])
                ef = tf.extractfile(m) if m is not None else None
                if ef is None:
                    continue  # missing/unreadable -> won't match
                data = ef.read()
                calc = hashlib.sha256(data).hexdigest()
                if calc == e["sha256"]:
                    matched += 1
                chain = hashlib.sha256(
                    chain + e["sha256"].encode() + str(e["size"]).encode() + e["path"].encode()
                ).digest()
        chain_ok = chain.hex() == manifest.get("chain_hash", "")
        ok = chain_ok and matched == total_files
        return {
            "status": "ok" if ok else "corrupt",
            "checked": total_files,
            "matches": matched,
            "chain_ok": chain_ok,
            "expected_chain": manifest.get("chain_hash", ""),
        }

    # ------------------------------------------------------------------
    # Restore
    # ------------------------------------------------------------------
    def restore_snapshot(
        self,
        snapshot: Snapshot,
        dest_dir: str,
        key: bytes | None = None,
    ) -> RestoreReport:
        """Extract a snapshot archive into ``dest_dir`` and verify every file.

        Each extracted file's bytes are re-hashed and compared to the manifest.
        If any file fails verification the report status is ``corrupt`` but
        already-extracted files remain (caller may choose to clean up). Path
        traversal outside ``dest_dir`` is rejected.
        """
        dest_dir = os.path.abspath(dest_dir)
        os.makedirs(dest_dir, exist_ok=True)
        k = key if key is not None else self._default_key
        archive_bytes = _read_archive(snapshot.path, k)
        manifest = _load_manifest(archive_bytes)
        entries = {e["path"]: e for e in manifest["entries"] if e.get("entry_type") == "file"}

        report = RestoreReport(snapshot_id=snapshot.id, dest_dir=dest_dir)
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as tf:
            for member in tf.getmembers():
                if member.name == _MANIFEST_MEMBER:
                    continue
                rel = _normalize_rel(member.name)
                if rel is None:
                    msg = f"unsafe member path in archive: {member.name!r}"
                    raise ValueError(msg)
                full = os.path.normpath(os.path.join(dest_dir, rel))
                # guard against escaping dest_dir
                if os.path.commonpath([dest_dir, full]) != dest_dir:
                    msg = f"member escapes destination: {member.name!r}"
                    raise ValueError(msg)
                if member.isdir():
                    os.makedirs(full, exist_ok=True)
                    continue
                src = tf.extractfile(member)
                if src is None:
                    continue
                os.makedirs(os.path.dirname(full) or dest_dir, exist_ok=True)
                data = src.read()
                with open(full, "wb") as fh:
                    fh.write(data)
                report.restored += 1
                report.total_bytes += len(data)
                expected = entries.get(rel)
                calc = hashlib.sha256(data).hexdigest()
                if expected is not None and calc == expected["sha256"]:
                    report.verified += 1
                else:
                    report.failed += 1

        report.status = (
            "ok" if report.failed == 0 and report.verified == report.restored else "corrupt"
        )
        # Recreate empty / directory-only entries from the manifest so the
        # restored tree structurally matches the source.
        for e in manifest["entries"]:
            if e.get("entry_type") != "dir":
                continue
            rel = _normalize_rel(e["path"])
            if rel is None:
                continue
            os.makedirs(_safe_dest(rel, dest_dir), exist_ok=True)
        logger.info(
            "Restored snapshot %s -> %s: %d files, %d verified, %d failed",
            snapshot.id,
            dest_dir,
            report.restored,
            report.verified,
            report.failed,
        )
        return report


def _file_sha256(path: str) -> str:
    """Compute the sha256 of a file's real bytes on disk."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot_to_dict(snapshot: Snapshot) -> dict[str, Any]:
    """Serialize a Snapshot (minus the bulky entries) for reporting."""
    return {
        "id": snapshot.id,
        "name": snapshot.name,
        "path": snapshot.path,
        "size": snapshot.size,
        "n_files": snapshot.n_files,
        "total_size": snapshot.total_size,
        "created_at": snapshot.created_at,
        "encrypted": snapshot.encrypted,
    }
