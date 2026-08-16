# Real Snapshot / Backup / Restore Engine (stdlib, honest crypto)

Pattern for adding a REAL backup/restore executor to an ENI Enterprise OS module
instead of a simulated one. Proven in `disaster_recovery` (SnapshotEngine,
~/Desktop/Enterprise Builder/enterprise/modules/disaster_recovery/snapshot.py).
Pure stdlib only: `tarfile`, `gzip`, `hashlib`, `hmac`, `json`, `os`, `io`.

## Core design (restic-flavored, but stdlib)
- Pack the source tree into ONE gzip'd tar archive with an **embedded JSON
  manifest** as a reserved tar member (e.g. `._eni_manifest.json`).
- Walk with `os.walk`, sort dirs+files for determinism, record EVERY file:
  `{path, size (real byte size), sha256 (real digest), entry_type}` plus dir
  entries so empty dirs survive. Aggregate `n_files`, `total_size`, `source_base`,
  `created_at`.
- Manifest is **sha256 hash-chained**: running digest = sha256(prev_chain +
  entry.sha256 + entry.size + entry.path). Store final value as `chain_hash`.
  Any reorder/edit/drop of an entry changes the chain -> detectable.

## API shape
- `create_snapshot(source_dir, target_dir, name=None, encrypt_key=None)` ->
  `Snapshot{id,name,path,size,n_files,manifest,created_at,encrypted}`. Raise
  ValueError if source_dir isn't a real dir.
- `list_snapshots(target_dir)` -> read each archive's manifest, newest-first.
  Requires the key for encrypted entries.
- `restore_snapshot(snapshot, dest_dir)` -> extract, re-hash every file vs
  manifest, return `RestoreReport{restored,verified,failed,total_bytes,status}`.
- `verify(snapshot)` -> recompute all hashes + replay chain. Returns
  `{status: ok|corrupt, checked, matches, chain_ok}`.

## Critical pitfalls (learned the hard way)
1. **Empty dirs are NOT tar members** if you only add file entries. Recreate
   them on restore by iterating manifest `entry_type=="dir"` entries and
   `os.makedirs(..., exist_ok=True)`.
2. **verify() must not crash on a corrupt/unreadable archive.** Wrap
   archive-read + manifest-load in try/except; on any exception return
   `{status:"corrupt"}`. Byte flips in gzip can produce BadGzipFile/ReadError
   instead of a clean hash mismatch — both must surface as "corrupt", not an
   uncaught exception.
3. **Path-traversal safety on restore**: normalize each member name, reject
   `..` escape, and assert `os.path.commonpath([dest_dir, full]) == dest_dir`
   before writing.
4. **Testing trick**: read raw archive bytes with `open()` (plain), NOT
   `gzip.open().read()` when you're about to hand bytes to
   `tarfile.open(mode="r:gz")` — double-decompressing causes
   "Not a gzipped file" / ReadError.
5. **Don't flip bytes in compressed data** to test "clean" hash mismatch — the
   flip often corrupts decompression instead. For a deterministic manifest-
   tamper test, REBUILD the archive with a tampered manifest (swap a file's
   sha256 to a bogus digest) rather than editing compressed bytes.

## Honest crypto (do NOT overclaim)
- `encrypt_key` -> store as `.eni`: PBKDF2-HMAC-SHA256 key-stretch to build a
  keystream, XOR the archive bytes with it (per-archive random salt), AND write
  an HMAC-SHA256 tag over the plaintext archive in the header.
- On-disk layout: `magic | salt_len(1) | salt | hmac(32) | xored_payload`.
- **Label the XOR as obfuscation-strength ONLY, NOT confidentiality** (a
  known-plaintext attacker recovers the keystream). The HMAC layer is the REAL
  guarantee. Write this in the module docstring — that honesty is what makes it
  "master class" rather than fake crypto.
- Wrong key / tamper -> HMAC mismatch. Low-level reader should raise ValueError;
  high-level `verify` should degrade to `corrupt`.
- Key handling: engine-level default key (`SnapshotEngine(key=...)`) + per-call
  override; `list`/`load` need the right key for encrypted entries.

## Integrating with an existing policy layer
If a `BackupManager`-style policy layer already exists and its tests are sacred:
- Keep the legacy simulated path as a FALLBACK only when the caller passes a
  non-existent/remote source path (so old tests stay green byte-for-byte).
- When a REAL source dir + snapshot store are configured, call the real engine
  and record real `size` + real `chain_hash` as the checksum on the record.
- Preserve all public API + existing tests; ADD exports (`SnapshotEngine`,
  `Snapshot`, `RestoreReport`, `snapshot_to_dict`) to `__init__.__all__`.

## Test coverage to aim for (a master-class suite)
create has files inside archive; real n_files/size vs known inputs; restore
round-trip byte-identical + hash-verified; verify ok; tamper -> corrupt
(content flip, missing member, manifest tamper, unreadable archive); manifest
chain detects reorder & is deterministic; encrypted transform on disk, verify/
list/restore with key, wrong-key and no-key rejection, HMAC tamper; full
lifecycle; policy-layer integration + fallback preservation.
