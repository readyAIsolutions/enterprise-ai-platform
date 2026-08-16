# Security model placement — part of the controller, NOT a standalone sidecar

## LO's standing architecture (learned the hard way, 2026-08-05)

When LO says "the local model that secures hermes" or "the security stuff with a
local model", he means the security layer that belongs to the **ENI Hermes
Controller** — the controller is the single local model that owns Hermes, and
the security model is a PART of it, not a separate server LO bolts on.

I built the local security model as a standalone `~/.hermes/security/` package
with its own HTTP server (:8931) and its OWN systemd unit (`eni-security.service`),
then "flushed it out" in isolation. LO rejected this hard ("it was supposed to be
a part of eni controller"). Do NOT repeat this.

## The controller already owns the privacy/secret layer

`eni_controller/secrets.py` — `SecretsBoundary` (singleton `get_boundary()`):
- Wraps the `SecretBroker` (from whichever security dir is on sys.path) as the
  local-first vault.
- `sanitize_for_cloud()` / `assert_cloud_safe()` — fails CLOSED on egress: any
  cloud-bound prompt gets secrets scrubbed to reversible placeholders
  (`__SECRET_<type>__`), and a secret that cannot be masked BLOCKS the call.
- `restore_for_lo()` — restores placeholders only for LO locally, never logged.
- Applied at `Controller.process()` AND inside `router.py` (`ModelRouter.chat`),
  so BOTH egress paths are gated. `controller.status` reports `broker_attached`.

So the security gate is already inside the controller's loop. Extending "the
local security model" means extending THIS — the controller's secrets boundary +
its local model routing — NOT standing up a parallel standalone server with its
own lifecycle.

## Correct approach when asked to "secure hermes / build the local security model"

1. Confirm the target is the ENI controller's privacy/secret path (SecretsBoundary
   in `eni_controller/secrets.py`), not a new detached service.
2. Extend `SecretsBoundary` / the controller's sanitize-on-egress and restore path.
3. Any HTTP surface for secrets/chat should be exposed THROUGH the controller's
   own `serve` (port 8940), under the controller's one systemd unit and restart
   story — never a second `eni-security.service`.
4. If a separate `~/.hermes/security/` broker is used as the underlying vault,
   the controller attaches it as a dependency (sys.path + `SecretBroker`), which
   is already how `secrets.py` works. Keep it as an import, not a separate
   always-on server.

## Chat front-end for secrets: use the two-pane terminal, not a shell command

`scripts/eni_chat_two_pane.py` (in this skill) is LO's two-pane chat terminal:
left pane = HERMES route, right pane = LOCAL airllm brain :8913. It is the SAFE
place to hand a secret to the controller. On send it runs `detect_secret()` /
`sanitize_line()` per line and swaps the raw value for `{SECRET:NAME}` BEFORE
dispatch — so a paste discovered mid-typing never reaches any model. Launch:
`gnome-terminal --geometry=122x34 -- python3 .../eni_chat_two_pane.py`.

## Most-secure storage decision (LO, 2026-08-08): vault ONLY, no .env fallback

When LO says "most secure, don't want cloud models seeing my envs", the answer
is: controller encrypted vault (`/security/env/set` <-> `SecretsBoundary` /
`SecretBroker`, machine-owned `.master_key` 0600) is the ONLY store. Never ALSO
write pasted secrets into `~/.hermes/.env` or a plaintext config so a cloud-bound
provider call can pick them up. Models, cloud or local, see only `{SECRET:NAME}`
placeholders; the raw value resolves ONLY on the box at execution time. Storage
choice is deliberately the Vault, not `.env`.

## Pitfall: a raw secret in a logged command lands in Hermes' own session DB

Verifying the vault with a curl that put the literal test value in the command
body caused a transient plaintext hit in `~/.hermes/state.db` (Hermes' own
session/shell log), even though the vault stayed encrypted. The lesson is NOT
"vault leaks" — it's that a raw secret must never appear verbatim in ANY logged
command or channel (shell history, Hermes session DB, chat). The two-pane UI
redacts before dispatch, so pasting there is the safe path. To verify no
plaintext persists: `grep -rl "<value>" ~/.hermes/` should be empty; note a
transient in `state.db` self-clears (file truncates to 0). Do not copy a live
secret into a curl/terminal invocation — write it via the pane UI or an env var
secured by the vault ref.

## Pitfalls that bite when you build the security layer

- **Audit HMAC dropped on serialize**: `AuditEvent` (and any dataclass) drops any
  field assigned as a dynamic attribute post-construction — `to_dict()`/`asdict()`
  only emits declared dataclass fields. If `hmac` isn't declared, every entry
  fails `hmac_invalid` and the whole log self-rotates as "corrupted". Declare the
  field (`hmac: str = ""`) in the dataclass.
- **Secrets vanish across restart**: a per-process ephemeral encryption key means
  last run's store is undecryptable next start (silent data loss). Persist a
  machine-owned key file (`~/.hermes/security/.master_key`, chmod 0600).
- **Corrupt-audit feedback loop**: on a hash mismatch, append a recovery/rotation
  (backup the corrupt log, start fresh genesis) instead of appending ever more
  `integrity_violation` entries.
- **Enum vs string in self-tests**: `GuardAction.ALLOW == "allow"` is False; compare
  `.value`.

## Verification

`eni_controller/tests/test_controller.py` (17 offline tests) covers the
secrets boundary in fallback mode (`use_broker=False`). After any security change,
run that plus the enterprise `modules/hermes_controller` tests.
