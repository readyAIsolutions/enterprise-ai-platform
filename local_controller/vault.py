"""Local secret vault for the one-prompt-program controller.

INTENT
------
This module is the ONLY place private secrets live inside the local
controller. It stores secrets ON DISK (local only) and NEVER transmits their
values to any network or cloud model. The only thing that may ever leave this
machine is a REDACTED prompt in which every real secret value has been replaced
by its placeholder *name* (e.g. ``openai_key``), never the value.

Storage is a JSON file ``data/vault.json`` with mode 0600. If the optional
``cryptography`` package is available we encrypt the payload with AES-GCM
(key kept in a local mode-0600 file ``data/.vault_key``). If it is NOT
available we fall back to a clear ``::MODE::`` sandbox that still refuses to
ever transmit values (redact never reveals them) and still supports
``get(name) -> Optional[str]``.

Security contract (non-negotiable):
  * get/set operate purely on the local file.
  * redact() guarantees no real value is ever present in the returned string.
"""

from __future__ import annotations

import base64
import json
import os
import re
from typing import Dict, List, Optional

try:  # optional dependency; AES-GCM encryption when present
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    _HAS_CRYPTOGRAPHY = True
except Exception:  # pragma: no cover - environment without the package
    _HAS_CRYPTOGRAPHY = False

# ---------------------------------------------------------------------------
# Path resolution (repo root = two directories above this module)
# ---------------------------------------------------------------------------

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_DATA_DIR = os.path.join(_REPO_ROOT, "data")
_DEFAULT_VAULT_PATH = os.path.join(_DEFAULT_DATA_DIR, "vault.json")
_DEFAULT_KEY_PATH = os.path.join(_DEFAULT_DATA_DIR, ".vault_key")

# Matches a ``{placeholder_name}`` token inside a prompt.
_TOKEN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


class Vault:
    """A local-only secret store with AES-GCM-at-rest and strict redaction."""

    def __init__(
        self,
        path: str = _DEFAULT_VAULT_PATH,
        key_path: str = _DEFAULT_KEY_PATH,
        auto_create: bool = True,
    ) -> None:
        self.path = path
        self.key_path = key_path
        self._secrets: Dict[str, str] = {}
        self._mode = "AES-GCM" if _HAS_CRYPTOGRAPHY else "clear::MODE::sandbox"
        if auto_create:
            self._ensure_file()

    # -- disk helpers -------------------------------------------------------

    def _ensure_file(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if not os.path.exists(self.path):
            self._persist({})
        # enforce restrictive permissions on both files
        for p in (self.path, self.key_path):
            if os.path.exists(p):
                try:
                    os.chmod(p, 0o600)
                except OSError:  # pragma: no cover - OS refuses chmod
                    pass

    def _key(self) -> bytes:
        if not _HAS_CRYPTOGRAPHY:  # pragma: no cover - only in clear mode
            return b"\x00" * 32
        if os.path.exists(self.key_path):
            with open(self.key_path, "rb") as fh:
                return fh.read()
        key = os.urandom(32)
        with open(self.key_path, "wb") as fh:
            fh.write(key)
        try:
            os.chmod(self.key_path, 0o600)
        except OSError:  # pragma: no cover
            pass
        return key

    def _persist(self, payload: Dict[str, str]) -> None:
        data = {"mode": self._mode, "secrets": payload}
        raw = json.dumps(data, sort_keys=True).encode("utf-8")
        if _HAS_CRYPTOGRAPHY:
            nonce = os.urandom(12)
            cipher = AESGCM(self._key())
            ciphertext = cipher.encrypt(nonce, raw, None)
            blob = {
                "enc": "aes-256-gcm",
                "nonce": base64.b64encode(nonce).decode("ascii"),
                "data": base64.b64encode(ciphertext).decode("ascii"),
            }
            with open(self.path, "w") as fh:
                json.dump(blob, fh, sort_keys=True)
        else:  # clear sandbox mode - still local only, never transmitted
            with open(self.path, "w") as fh:
                json.dump({"mode": self._mode, "secrets": payload}, fh)
        try:
            os.chmod(self.path, 0o600)
        except OSError:  # pragma: no cover
            pass

    def _load(self) -> Dict[str, str]:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r") as fh:
                blob = json.load(fh)
        except (json.JSONDecodeError, OSError):  # corrupt file -> empty, safe
            return {}
        if blob.get("enc") == "aes-256-gcm":
            nonce = base64.b64decode(blob["nonce"])
            ciphertext = base64.b64decode(blob["data"])
            cipher = AESGCM(self._key())
            plain = cipher.decrypt(nonce, ciphertext, None)
            data = json.loads(plain.decode("utf-8"))
            return data.get("secrets", {})
        return blob.get("secrets", blob.get("mode") and {} or {})

    # -- public API ---------------------------------------------------------

    def set(self, name: str, value: str) -> None:
        """Store a secret locally. Never transmitted."""
        if not isinstance(name, str) or not name.isidentifier():
            raise ValueError(f"invalid placeholder name: {name!r}")
        self._secrets[name] = value
        self._persist(self._secrets)

    def get(self, name: str) -> Optional[str]:
        """Return the real value or None. Local-only read."""
        self._secrets = self._load()
        return self._secrets.get(name)

    def placeholders(self) -> List[str]:
        """Names currently held in the vault (never their values)."""
        self._secrets = self._load()
        return sorted(self._secrets.keys())

    def redact(self, prompt: str) -> str:
        """Return a prompt with EVERY real secret removed.

        Two layers, so no value can leak:
          1. Any ``{name}`` token for a known placeholder becomes just the name.
          2. Any literal occurrence of a known secret VALUE becomes the name too
             (defends against naive string interpolation of the value itself).
        """
        self._secrets = self._load()
        out = prompt

        def _name_repl(match: "re.Match[str]") -> str:
            return match.group(1)  # leave only the placeholder NAME

        out = _TOKEN.sub(_name_repl, out)
        for name, value in self._secrets.items():
            if value:  # scrub real value wherever it may have been pasted
                out = out.replace(value, name)
        return out


def redact(prompt: str, vault: Optional[Vault] = None) -> str:
    """Module-level convenience redactor: strips ``{NAME}`` tokens to names.

    If a :class:`Vault` is supplied, its known real values are scrubbed too.
    This is the safe helper to call before ANY prompt is sent to a network model.
    """
    if vault is not None:
        return vault.redact(prompt)
    return _TOKEN.sub(lambda m: m.group(1), prompt)


def make_vault(path: str = _DEFAULT_VAULT_PATH) -> Vault:
    """Factory returning a ready vault instance."""
    return Vault(path=path)