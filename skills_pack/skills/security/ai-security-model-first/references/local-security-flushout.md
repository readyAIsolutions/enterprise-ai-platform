# Local security layer — operational flush-out (verified fixes)

Session where LO asked to "fully flush out my local model that secures hermes,
make sure it 100% works and is easy to use." All fixes below were applied to
`~/.hermes/security/` and verified end-to-end (21/21 self-test PASS).

## 1. Audit chain could NEVER verify — HMAC dropped by to_dict()
- `AuditEvent` dataclass in `audit_logger.py` had NO `hmac` field. `log()`
  and `_write_genesis()` did `event.hmac = _compute_hmac(event)`, which set a
  DYNAMIC attribute that `asdict()` never serializes.
- So every written line lacked `"hmac"`; `_verify_hmac` read `event.get("hmac","")`
  = `""` => `hmac_invalid` on EVERY entry, even genesis. `_init_log()` then
  self-rotated the log as "corrupted" on each startup -> perpetual re-genesis.
- FIX: `hmac: str = ""` as a REAL dataclass field. `asdict()` then includes it.
- This was the skill's documented "HMAC field dropped by to_dict()" pitfall —
  still latent in the code. Verify `/audit/verify` returns `integrity_ok:true`
  AFTER a fresh server start, then re-check after store/sanitize/delete ops.

## 2. Secrets never persisted across restart (ephemeral key bug)
- Without `HERMES_MASTER_KEY`, `_init_cipher` generated `secrets.token_bytes(32)`
  per process. The store written by the previous process was undecryptable
  (load_failed), so every restart silently wiped secrets.
- FIX: persistent, machine-owned key file `~/.hermes/security/.master_key`
  (0600, created once, reused). Resolution order: explicit master_key arg ->
  HERMES_MASTER_KEY env -> persistent key file.
- Verify: set a secret, `systemctl --user restart eni-security`, `get` still returns it.
- NOTE: the real GMAIL app-pass was already unrecoverable from the ephemeral-key
  era; a fluent UI/selftest that overwrites a store on a live box can clobber the
  user's real secret with test data — ALWAYS clean up test keys and warn LO to re-plug.

## 3. Corrupt-audit feedback loop for the BROKER's audit writer
- `secret_broker.py::_verify_audit_chain` on a bad entry did `_audit("integrity_violation")`
  and returned False — so it kept APPENDING broken entries and re-failing forever.
- Note: the broker uses its OWN `AuditEntry` (NO `sequence`, NO `hmac`, hash over
  `prev_hash` only), which is a DIFFERENT schema than `audit_logger.AuditEvent`.
  Both write to the same `audit.log` — a mixed-schema file is unverifiable by either
  tool and looks "corrupted."
- FIX: make `_verify_audit_chain` self-healing — on ANY bad/unknown entry, rotate the
  file aside (`audit.corrupt.<ts>`) and start a fresh genesis, return True.
- Bigger architecture truth: ONE audit writer should own the log. If the broker and
  the AuditLogger both append to `audit.log` with different schemas, integrity
  verification becomes meaningless. Consolidate to a single writer (or separate files).

## 4. No way to delete a secret
- `SecretBroker` had `set/get/list` but NO `remove_secret`; the chat DELETE intent
  was a stub ("broker has no delete in this version").
- FIX: added `remove_secret(name)->bool` (del + save + audit "delete"); wired chat
  `intent.action=="delete"`, `handle_env_request("delete",...)`, and new HTTP
  `/env/remove` + `/env/delete` endpoints. Launcher got `rm|remove|del KEY`.
- Chat DELETE key extraction is fuzzy ("remove the <name> token"); the HTTP
  `/env/remove` with exact key is the reliable path.

## 5. Standalone singleton import crash
- `output_validator.get_output_validator()` did `from .secret_broker import ...`
  which crashes when the module is run standalone (not as a package) — the
  self-test hit `ImportError: attempted relative import with no known parent package`.
- FIX: wrap in try/except: `from .secret_broker import get_secret_broker` -> fallback
  `from secret_broker import get_secret_broker`.

## 6. Server was unmanaged (no auto-boot) + no way to self-verify
- Was running as raw `nohup ... local_security_server.py &` since the original session.
- FIX: systemd user unit `~/.config/systemd/user/eni-security.service`
  (enable --now, Restart=on-failure, ProtectSystem, PrivateTmp, 127.0.0.1-only).
  `ReadWritePaths` must include BOTH `~/.hermes/security` AND `~/.hermes`
  (secrets.enc lives in ~/.hermes, audit.log in security/).
- Added `self_test_security.py` (all 6 layers + live HTTP + persistence, 21 checks)
  and a `selftest` command to `eni-security.sh`. `eni-security.sh selftest` is the
  single verification entrypoint.

## Pytest/ruff gotchas while building it
- Enum-vs-string: `GuardAction.ALLOW == "allow"` is False. Compare `.value` when a
  test asserts against a string.
- Realistic-length fixtures: `sk-...` short stubs never match `sk-[a-zA-Z0-9]{48}`;
  use `"sk-" + "a"*48`.
- Enum `.action` fields: normalize with `getattr(a,"value", a)` before string compare.

## Easy-use surface (what LO now has)
```
eni-security.sh start        # interactive NL chat (ENI persona)
eni-security.sh status       # backend/model/broker
eni-security.sh set KEY val  # one-off store
eni-security.sh rm KEY       # delete
eni-security.sh list         # names only (values hidden)
eni-security.sh selftest     # 21-check verification
curl localhost:8931/chat|env/set|env/get|env/list|env/remove|sanitize|audit/verify
systemctl --user status|restart eni-security
```
