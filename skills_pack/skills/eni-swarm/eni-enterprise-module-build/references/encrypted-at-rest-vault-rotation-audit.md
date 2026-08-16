# Stdlib encrypted-at-rest secrets vault + rotation scheduler + access audit

Session: upgraded ENI `modules/secret_rotation/` to master class by ADDING a new
`vault.py` (SecretVault + RotationScheduler + AccessAudit + VaultFacade), keeping
the original hash-only engine untouched. Whole module 74 passed (23 new vault
tests). This is the reusable recipe for any "real encrypted vault / no stubs"
request in the Enterprise platform, done with ZERO third-party deps.

## Why two classes (complementary, not redundant)
- Original `secret_rotation` engine is deliberately HASH-ONLY (stores SHA-256 of
  secrets, never the raw value) → identity/expiry/revocation tracking.
- The vault is the counterpart that CAN return the actual secret (e.g. a key the
  platform must replay), so it must be encrypted-at-rest. Keep both; "upgrade the
  module" rarely means "rewrite it" — ADD the encrypted layer, PRESERVE all API.

## The crypto recipe (honest, stdlib, testable)
1. Key derivation: `hashlib.pbkdf2_hmac('sha256', master_key, salt, iterations,
   dklen=64)` → split into `(enc_key[:32], mac_key[32:])`. Per-secret random
   16-byte salt + 16-byte IV in every blob.
2. Stream cipher (educational, XOR): expand keystream from
   `sha256(enc_key + iv + block_counter.to_bytes(8,'big'))`, XOR with plaintext.
   Documented as non-production (swap for AES-GCM/libsodium in real deployments;
   keep the interface swap-friendly).
3. Authentication: `HMAC-SHA256(mac_key, version||salt||iv||cipher)`, appended to
   blob = `b'\x01' + salt + iv + cipher + mac(32)`.
4. **MAC-verify BEFORE decrypt** with `hmac.compare_digest`. If it fails, the
   ONLY two causes are (a) tampered ciphertext or (b) wrong master key — both
   raise the SAME error, failing closed. This is what makes the "wrong master key
   fails" test pass without storing any plaintext marker.
5. kind="hash" mode: store `hash_secret(plaintext)` as the payload so a secret
   can be retained hash-only (parity with the parent module) while still round-
   tripping through the encrypted blob.

## Serialization / DB
- One SQLite file, three tables sharing one connection: `secrets(name, blob,
  kind, created_at, updated_at)`, `rotation_policies(name, interval_secs,
  last_rotated)`, `audit_log(id, secret_name, action, ts, actor, prev_hash,
  entry_hash)`. A `VaultFacade` owns all three so a single file is atomic/durable.
- Audit hash chain: seed = `sha256(b'en-...-audit-chain-v1')`; each entry's
  `entry_hash = sha256(prev_hash | name | action | repr(ts) | actor)` and its
  `prev_hash` = previous entry hash. `verify()` replays the whole chain and
  reports `broken_at` index → tamper-evident append-only log.

## PITFALLS (cost me 3 failed tests this session — check these first)
- **`0.0 or ts` falsy bug**: when `last_rotated` is exactly `0.0`, `x or ts`
  evaluates to `ts`, so an interval starting at t=0 never looks due. Always test
  `is None`, never truthiness: `last = pol["last_rotated"] if pol["last_rotated"]
  is not None else ts`.
- **Rotation must PRESERVE the configured interval**: a naive `rotate()` that
  calls `set_policy(name, default_interval, last_rotated=now)` clobbers a
  caller's 100s policy back to the 90-day default. Read the existing policy,
  keep its `interval_secs`, only bump `last_rotated`.
- **kind must be honored at `put` too**: if you add `kind="hash"`, `put` must
  hash the payload at write time (not just at rotation time), or the raw secret
  leaks into the encrypted blob and the raw-DB-no-plaintext test fails.
- **Mix of real `time.time()` and synthetic `now=` in tests breaks due/rotation
  math**: if a test passes `now=` to one call but `rotate()` falls back to real
  epoch on another, real-epoch-scaled `last_rotated` dwarfs the synthetic `now`
  and every boundary assertion flips. Be consistent — thread `now` through.
- **Raw-DB-no-plaintext proof**: after `put("k","SUPERSECRET...")`, read the
  sqlite file bytes AND the `blob` column and assert the plaintext string is in
  neither. This is the test that proves "encrypted-at-rest" is real, not stubbed.
- **Wrong master key on reopen**: a vault reopened with a different master key
  decrypts to garbage — but the MAC check catches it, so `get` raises
  `VaultIntegrityError` before any plaintext is produced. Test that too.

## Verification
- Add `tests/test_vault.py` (tmp_path DBs, low PBKDF2 iterations like 2000 for
  speed) covering: put/get round-trip, raw-DB-no-plaintext, wrong-master-key,
  MAC-tamper detection (flip a ciphertext byte via SQL UPDATE), overwrite,
  missing→KeyError, list/delete, rotation-new-secret, due_for_rotation
  boundaries, hash-only mode, audit logging + append-only + chain integrity +
  chain tamper detection, cross-reopen persistence, factory helpers.
- Run the WHOLE module: `pytest modules/secret_rotation -q -p no:cacheprovider` —
  report `N passed (X new + Y legacy)`.
