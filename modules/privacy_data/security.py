"""
Security Controls Engine
Implements data security controls:
  Encryption at rest, Encryption in transit, Field-level encryption,
  Tokenization, Masking, Anonymization, Pseudonymization,
  Secrets management, Immutable audit logs, Key rotation
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from cryptography.fernet import Fernet, MultiFernet
from cryptography.hazmat.primitives import hashes, padding, serialization
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa, padding as asym_padding


# ─── Enums ────────────────────────────────────────────────────────────────────

class EncryptionAlgorithm(str, Enum):
    """Supported encryption algorithms."""
    AES_256_GCM = "aes-256-gcm"
    AES_256_CBC = "aes-256-cbc"
    CHACHA20_POLY1305 = "chacha20-poly1305"
    FERNET = "fernet"  # AES-128-CBC + HMAC


class MaskingStrategy(str, Enum):
    """Data masking strategies."""
    FULL_MASK = "full_mask"          # Replace all chars with *
    PARTIAL_MASK = "partial_mask"     # Show first/last N chars
    HASH = "hash"                    # Replace with SHA-256 hash
    TOKENIZE = "tokenize"            # Replace with token
    REDACT = "redact"                # Replace with [REDACTED]
    NULLIFY = "nullify"              # Replace with None
    RANGE_GENERALIZE = "range_generalize"  # Generalize to range
    FAKE = "fake"                    # Replace with realistic fake data


class TokenizationFormat(str, Enum):
    """Token format strategies."""
    UUID = "uuid"
    HASH_HEX = "hash_hex"
    FORMAT_PRESERVING = "format_preserving"
    RANDOM_ALPHANUMERIC = "random_alphanumeric"


class KeyRotationStrategy(str, Enum):
    """Key rotation strategies."""
    TIME_BASED = "time_based"
    USAGE_BASED = "usage_based"
    MANUAL = "manual"
    COMPROMISE = "compromise"


# ─── Key Management ───────────────────────────────────────────────────────────

@dataclass
class EncryptionKey:
    """Managed encryption key with metadata."""
    key_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    key_material: bytes = field(default_factory=lambda: Fernet.generate_key())
    algorithm: EncryptionAlgorithm = EncryptionAlgorithm.FERNET
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    rotated_from: Optional[str] = None
    encryption_count: int = 0
    decryption_count: int = 0
    is_active: bool = True
    is_primary: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def age_days(self) -> int:
        return (datetime.utcnow() - self.created_at).days

    @property
    def fernet(self) -> Fernet:
        return Fernet(self.key_material)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key_id": self.key_id,
            "algorithm": self.algorithm.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "age_days": self.age_days,
            "encryption_count": self.encryption_count,
            "decryption_count": self.decryption_count,
            "is_active": self.is_active,
            "is_primary": self.is_primary,
        }


class KeyManager:
    """
    Encryption key lifecycle manager.

    Handles key generation, rotation, revocation, and multi-key support
    for seamless key rotation.
    """

    def __init__(self, rotation_days: int = 90):
        self._keys: Dict[str, EncryptionKey] = {}
        self._rotation_days = rotation_days
        self._key_history: List[str] = []  # Ordered list of retired key IDs
        self._usage_log: List[Dict[str, Any]] = []

    def generate_key(
        self,
        algorithm: EncryptionAlgorithm = EncryptionAlgorithm.FERNET,
        make_primary: bool = False,
    ) -> EncryptionKey:
        """Generate a new encryption key."""
        if algorithm == EncryptionAlgorithm.FERNET:
            key_material = Fernet.generate_key()
        elif algorithm == EncryptionAlgorithm.AES_256_GCM:
            key_material = secrets.token_bytes(32)  # 256-bit key
        else:
            key_material = Fernet.generate_key()

        key = EncryptionKey(
            key_material=key_material,
            algorithm=algorithm,
            is_primary=make_primary,
        )
        self._keys[key.key_id] = key

        # If primary, deactivate other primary keys
        if make_primary:
            for k in self._keys.values():
                if k.key_id != key.key_id:
                    k.is_primary = False

        return key

    def rotate_keys(self, strategy: KeyRotationStrategy = KeyRotationStrategy.TIME_BASED) -> List[EncryptionKey]:
        """Rotate keys based on strategy. Returns list of new keys."""
        new_keys: List[EncryptionKey] = []

        if strategy == KeyRotationStrategy.TIME_BASED:
            for key in list(self._keys.values()):
                if key.is_active and key.age_days >= self._rotation_days:
                    new_key = self._rotate_single_key(key)
                    new_keys.append(new_key)

        elif strategy == KeyRotationStrategy.COMPROMISE:
            # Rotate all active keys immediately
            for key in list(self._keys.values()):
                if key.is_active:
                    new_key = self._rotate_single_key(key)
                    new_keys.append(new_key)

        elif strategy == KeyRotationStrategy.USAGE_BASED:
            for key in list(self._keys.values()):
                if key.is_active and key.encryption_count >= 1000000:
                    new_key = self._rotate_single_key(key)
                    new_keys.append(new_key)

        return new_keys

    def _rotate_single_key(self, old_key: EncryptionKey) -> EncryptionKey:
        """Rotate a single key, keeping old key for decryption."""
        new_key = self.generate_key(
            algorithm=old_key.algorithm,
            make_primary=old_key.is_primary,
        )
        new_key.rotated_from = old_key.key_id
        old_key.is_active = False
        old_key.expires_at = datetime.utcnow()
        self._key_history.append(old_key.key_id)
        self._usage_log.append({
            "action": "rotated",
            "old_key_id": old_key.key_id,
            "new_key_id": new_key.key_id,
            "timestamp": datetime.utcnow().isoformat(),
        })
        return new_key

    def revoke_key(self, key_id: str) -> bool:
        """Revoke a key immediately."""
        key = self._keys.get(key_id)
        if key:
            key.is_active = False
            key.expires_at = datetime.utcnow()
            self._usage_log.append({
                "action": "revoked",
                "key_id": key_id,
                "timestamp": datetime.utcnow().isoformat(),
            })
            return True
        return False

    def get_active_keys(self) -> List[EncryptionKey]:
        return [k for k in self._keys.values() if k.is_active]

    def get_primary_key(self) -> Optional[EncryptionKey]:
        """Get the primary encryption key."""
        for k in self._keys.values():
            if k.is_primary and k.is_active:
                return k
        # Fall back to any active key
        return next((k for k in self._keys.values() if k.is_active), None)

    def get_key(self, key_id: str) -> Optional[EncryptionKey]:
        return self._keys.get(key_id)

    def get_all_keys_for_decryption(self) -> List[EncryptionKey]:
        """Get all keys that could have encrypted data (active + recently rotated)."""
        return [
            k for k in self._keys.values()
            if k.is_active or k.key_id in self._key_history
        ]

    def build_multi_fernet(self) -> Optional[MultiFernet]:
        """Build a MultiFernet instance with all active keys."""
        active = self.get_active_keys()
        if not active:
            return None
        # Primary first, then others
        fernets = []
        primary = self.get_primary_key()
        if primary:
            fernets.append(primary.fernet)
        for k in active:
            if k.key_id != (primary.key_id if primary else None):
                fernets.append(k.fernet)
        return MultiFernet(fernets) if fernets else None

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "total_keys": len(self._keys),
            "active_keys": len(self.get_active_keys()),
            "primary_key_id": self.get_primary_key().key_id if self.get_primary_key() else None,
            "rotation_days": self._rotation_days,
            "rotated_keys": len(self._key_history),
            "total_encryptions": sum(k.encryption_count for k in self._keys.values()),
            "total_decryptions": sum(k.decryption_count for k in self._keys.values()),
        }


# ─── Encryption Service ──────────────────────────────────────────────────────

class EncryptionService:
    """
    Enterprise encryption service.

    Supports encryption at rest, field-level encryption, and
    encryption metadata tracking.
    """

    def __init__(self, key_manager: Optional[KeyManager] = None):
        self.key_manager = key_manager or KeyManager()
        # Ensure at least one key exists
        if not self.key_manager.get_active_keys():
            self.key_manager.generate_key(make_primary=True)

    def encrypt(
        self, plaintext: Union[str, bytes], key_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Encrypt data. Returns encrypted value with metadata.

        The returned dict contains:
          - ciphertext: base64 encoded encrypted data
          - key_id: which key was used
          - algorithm: algorithm used
          - encrypted_at: timestamp
        """
        key = (
            self.key_manager.get_key(key_id)
            if key_id
            else self.key_manager.get_primary_key()
        )
        if not key:
            raise ValueError("No active encryption key available")

        if isinstance(plaintext, str):
            plaintext = plaintext.encode('utf-8')

        fernet = key.fernet
        ciphertext = fernet.encrypt(plaintext)
        key.encryption_count += 1

        return {
            "ciphertext": base64.b64encode(ciphertext).decode('utf-8'),
            "key_id": key.key_id,
            "algorithm": key.algorithm.value,
            "encrypted_at": datetime.utcnow().isoformat(),
        }

    def decrypt(self, encrypted: Dict[str, Any]) -> bytes:
        """
        Decrypt data. Uses key_id from metadata to find the right key.
        """
        key_id = encrypted.get("key_id")
        if not key_id:
            raise ValueError("Missing key_id in encrypted data")

        key = self.key_manager.get_key(key_id)
        if not key:
            # Try getting from recently rotated keys
            for k in self.key_manager.get_all_keys_for_decryption():
                if k.key_id == key_id:
                    key = k
                    break
        if not key:
            raise ValueError(f"Encryption key {key_id} not found")

        ciphertext = base64.b64decode(encrypted["ciphertext"])
        fernet = key.fernet
        plaintext = fernet.decrypt(ciphertext)
        key.decryption_count += 1
        return plaintext

    def encrypt_field(
        self, data: Dict[str, Any], fields: List[str]
    ) -> Dict[str, Any]:
        """Encrypt specific fields in a data record."""
        result = dict(data)
        for field in fields:
            if field in result and result[field] is not None:
                result[field] = self.encrypt(str(result[field]))
        return result

    def decrypt_field(
        self, data: Dict[str, Any], fields: List[str]
    ) -> Dict[str, Any]:
        """Decrypt specific fields in a data record."""
        result = dict(data)
        for field in fields:
            if field in result and isinstance(result[field], dict) and "ciphertext" in result[field]:
                result[field] = self.decrypt(result[field]).decode('utf-8')
        return result

    def encrypt_record(
        self, record: Dict[str, Any], sensitive_fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Encrypt all sensitive fields in a record."""
        if sensitive_fields is None:
            sensitive_fields = self._detect_sensitive_fields(record)

        result = {}
        for key, value in record.items():
            if key in sensitive_fields and value is not None:
                result[key] = self.encrypt(str(value))
            else:
                result[key] = value
        return result

    @staticmethod
    def _detect_sensitive_fields(record: Dict[str, Any]) -> List[str]:
        """Auto-detect sensitive fields by name patterns."""
        sensitive_patterns = [
            "password", "secret", "token", "key", "credential",
            "ssn", "credit_card", "card_number", "cvv", "pin",
            "private_key", "api_key", "access_token", "refresh_token",
        ]
        return [
            k for k in record
            if any(pattern in k.lower() for pattern in sensitive_patterns)
        ]


# ─── Data Masking Service ─────────────────────────────────────────────────────

class DataMasker:
    """
    Data masking and anonymization service.

    Supports: masking, tokenization, anonymization, pseudonymization,
              and format-preserving transformations.
    """

    @staticmethod
    def mask(
        value: Any,
        strategy: MaskingStrategy = MaskingStrategy.PARTIAL_MASK,
        show_first: int = 2,
        show_last: int = 2,
        mask_char: str = "*",
        custom_mask: Optional[str] = None,
    ) -> Any:
        """Apply masking to a value."""
        if value is None:
            return None

        strval = str(value)

        if strategy == MaskingStrategy.FULL_MASK:
            return mask_char * len(strval)

        elif strategy == MaskingStrategy.PARTIAL_MASK:
            if len(strval) <= show_first + show_last:
                return mask_char * len(strval)
            return (
                strval[:show_first]
                + mask_char * (len(strval) - show_first - show_last)
                + strval[-show_last:]
            )

        elif strategy == MaskingStrategy.HASH:
            return hashlib.sha256(strval.encode()).hexdigest()[:16]

        elif strategy == MaskingStrategy.REDACT:
            return "[REDACTED]"

        elif strategy == MaskingStrategy.NULLIFY:
            return None

        elif strategy == MaskingStrategy.RANGE_GENERALIZE:
            try:
                num = float(strval)
                lower = (num // 10) * 10
                return {"range": [lower, lower + 10], "unit": "decade"}
            except ValueError:
                return strval

        elif strategy == MaskingStrategy.FAKE:
            return DataMasker._generate_fake_value(strval)

        return strval

    @staticmethod
    def mask_record(
        record: Dict[str, Any],
        field_strategies: Dict[str, MaskingStrategy],
        show_first: int = 2,
        show_last: int = 2,
    ) -> Dict[str, Any]:
        """Apply different masking strategies per field."""
        result = {}
        for key, value in record.items():
            strategy = field_strategies.get(key)
            if strategy and value is not None:
                result[key] = DataMasker.mask(
                    value, strategy,
                    show_first=show_first,
                    show_last=show_last,
                )
            else:
                result[key] = value
        return result

    @staticmethod
    def mask_pii(record: Dict[str, Any]) -> Dict[str, Any]:
        """Auto-mask common PII fields."""
        pii_strategies = {
            "email": MaskingStrategy.PARTIAL_MASK,
            "phone": MaskingStrategy.PARTIAL_MASK,
            "ssn": MaskingStrategy.FULL_MASK,
            "credit_card": MaskingStrategy.HASH,
            "password": MaskingStrategy.NULLIFY,
            "secret": MaskingStrategy.REDACT,
            "token": MaskingStrategy.REDACT,
            "address": MaskingStrategy.PARTIAL_MASK,
            "name": MaskingStrategy.PARTIAL_MASK,
            "dob": MaskingStrategy.RANGE_GENERALIZE,
            "ip_address": MaskingStrategy.PARTIAL_MASK,
        }
        return DataMasker.mask_record(record, pii_strategies)

    @staticmethod
    def _generate_fake_value(original: str) -> str:
        """Generate a realistic-looking fake value."""
        # Determine type and generate appropriate fake
        if "@" in original:
            return "user@example.com"
        if original.startswith("+"):
            return "+1-555-0000"
        return f"fake_{hashlib.md5(original.encode()).hexdigest()[:8]}"


# ─── Tokenization Service ─────────────────────────────────────────────────────

class TokenizationService:
    """
    Tokenization service for sensitive data.

    Replaces sensitive values with tokens while maintaining a
    secure mapping in a separate vault.
    """

    def __init__(self):
        self._vault: Dict[str, Dict[str, Any]] = {}  # token -> {original, metadata}
        self._reverse_vault: Dict[str, str] = {}      # hash(original) -> token
        self._format = TokenizationFormat.UUID

    def tokenize(
        self,
        value: Any,
        preserve_format: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Replace a value with a token."""
        if value is None:
            return ""

        strval = str(value)
        orig_hash = hashlib.sha256(strval.encode()).hexdigest()

        # Check if already tokenized
        if orig_hash in self._reverse_vault:
            return self._reverse_vault[orig_hash]

        # Generate token
        token = self._generate_token(strval, preserve_format)
        self._vault[token] = {
            "original_hash": orig_hash,
            "original_length": len(strval),
            "created_at": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }
        self._reverse_vault[orig_hash] = token
        return token

    def detokenize(self, token: str) -> Optional[str]:
        """NOT IMPLEMENTABLE: Tokens are one-way. Vault only stores hash."""
        return None

    def verify_token(self, token: str, value: Any) -> bool:
        """Verify if a token matches a value."""
        if token not in self._vault:
            return False
        value_hash = hashlib.sha256(str(value).encode()).hexdigest()
        return self._vault[token]["original_hash"] == value_hash

    def tokenize_record(
        self, record: Dict[str, Any], fields: List[str]
    ) -> Dict[str, Any]:
        """Tokenize specific fields in a record."""
        result = dict(record)
        for field in fields:
            if field in result and result[field] is not None:
                result[field] = self.tokenize(str(result[field]))
        return result

    def _generate_token(self, value: str, preserve_format: bool) -> str:
        """Generate a token."""
        if preserve_format:
            # Format-preserving: maintain same character set pattern
            chars = []
            for c in value:
                if c.isdigit():
                    chars.append(secrets.choice("0123456789"))
                elif c.isalpha():
                    chars.append(secrets.choice("abcdefghijklmnopqrstuvwxyz"))
                else:
                    chars.append(c)
            return "TOK_" + "".join(chars)
        elif self._format == TokenizationFormat.UUID:
            return f"tok_{uuid.uuid4().hex}"
        elif self._format == TokenizationFormat.HASH_HEX:
            return f"tok_{hashlib.sha256(value.encode()).hexdigest()[:32]}"
        else:
            return f"tok_{secrets.token_hex(16)}"

    @property
    def vault_size(self) -> int:
        return len(self._vault)


# ─── Anonymization / Pseudonymization ─────────────────────────────────────────

class AnonymizationService:
    """
    Data anonymization and pseudonymization service.

    - Anonymization: Irreversible removal of identifying information
    - Pseudonymization: Reversible replacement with artificial identifiers
    """

    def __init__(self, secret_key: Optional[bytes] = None):
        self._secret_key = secret_key or secrets.token_bytes(32)
        self._pseudonym_map: Dict[str, str] = {}

    def anonymize(self, value: Any) -> Any:
        """
        Irreversibly anonymize a value.
        Uses cryptographic hashing with salt.
        """
        if value is None:
            return None
        salt = secrets.token_bytes(16)
        data = str(value).encode()
        hashed = hashlib.pbkdf2_hmac('sha256', data, salt, 100000)
        return base64.b64encode(salt + hashed).decode('utf-8')

    def pseudonymize(self, identifier: str, namespace: str = "default") -> str:
        """
        Reversible pseudonymization.
        Replaces identifier with a pseudonym derived from the secret key.
        Can be reversed if you have the secret key.
        """
        key = f"{namespace}:{identifier}"
        if key in self._pseudonym_map:
            return self._pseudonym_map[key]

        # Derive pseudonym using HMAC
        pseudonym = hmac.new(
            self._secret_key,
            key.encode(),
            hashlib.sha256,
        ).hexdigest()[:16]

        self._pseudonym_map[key] = pseudonym
        return pseudonym

    def depseudonymize(self, pseudonym: str, namespace: str = "default") -> Optional[str]:
        """
        Reverse pseudonymization.
        NOTE: This requires the full mapping to be maintained.
        HMAC-based pseudonyms are not trivially reversible;
        this works because we maintain the mapping.
        """
        for key, pseudo in self._pseudonym_map.items():
            if pseudo == pseudonym and key.startswith(f"{namespace}:"):
                return key.split(":", 1)[1]
        return None

    def anonymize_record(
        self,
        record: Dict[str, Any],
        identifiers: List[str],
        strategy: str = "anonymize",
    ) -> Dict[str, Any]:
        """Anonymize or pseudonymize identifiers in a record."""
        result = dict(record)
        for field in identifiers:
            if field in result and result[field] is not None:
                if strategy == "anonymize":
                    result[field] = self.anonymize(result[field])
                elif strategy == "pseudonymize":
                    result[field] = self.pseudonymize(str(result[field]))
        return result


# ─── Immutable Audit Log ──────────────────────────────────────────────────────

@dataclass
class AuditEntry:
    """A single immutable audit log entry."""
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    actor: str = ""          # Who performed the action
    action: str = ""         # What was done
    resource: str = ""       # On what resource
    details: Dict[str, Any] = field(default_factory=dict)
    result: str = ""         # success, failure, denied
    ip_address: Optional[str] = None
    previous_hash: str = ""  # Hash of previous entry (chain)
    current_hash: str = ""   # Hash of this entry

    def compute_hash(self) -> str:
        """Compute cryptographic hash of this entry."""
        payload = (
            f"{self.entry_id}|{self.timestamp.isoformat()}|{self.actor}|"
            f"{self.action}|{self.resource}|{json.dumps(self.details, sort_keys=True)}|"
            f"{self.result}|{self.previous_hash}"
        )
        return hashlib.sha256(payload.encode()).hexdigest()


class ImmutableAuditLog:
    """
    Immutable audit log with cryptographic chaining.

    Each entry links to the previous via hash, creating a
    tamper-evident chain. Supports verification and export.
    """

    def __init__(self, log_name: str = "default"):
        self._log_name = log_name
        self._entries: List[AuditEntry] = []
        self._last_hash: str = "0" * 64  # Genesis hash
        self._initialized_at = datetime.utcnow()

    def record(
        self,
        actor: str,
        action: str,
        resource: str,
        details: Optional[Dict[str, Any]] = None,
        result: str = "success",
        ip_address: Optional[str] = None,
    ) -> AuditEntry:
        """Record an audit entry."""
        entry = AuditEntry(
            actor=actor,
            action=action,
            resource=resource,
            details=details or {},
            result=result,
            ip_address=ip_address,
            previous_hash=self._last_hash,
        )
        entry.current_hash = entry.compute_hash()
        self._entries.append(entry)
        self._last_hash = entry.current_hash
        return entry

    def verify_integrity(self) -> Tuple[bool, Optional[int]]:
        """
        Verify the integrity of the entire log chain.
        Returns (is_valid, first_bad_index).
        """
        prev_hash = "0" * 64
        for i, entry in enumerate(self._entries):
            if entry.previous_hash != prev_hash:
                return False, i
            # Recompute and verify
            recomputed = entry.compute_hash()
            if recomputed != entry.current_hash:
                return False, i
            prev_hash = entry.current_hash
        return True, None

    def query(
        self,
        actor: Optional[str] = None,
        action: Optional[str] = None,
        resource: Optional[str] = None,
        result: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[AuditEntry]:
        """Query audit entries with filters."""
        results = []
        for entry in reversed(self._entries):
            if actor and entry.actor != actor:
                continue
            if action and entry.action != action:
                continue
            if resource and entry.resource != resource:
                continue
            if result and entry.result != result:
                continue
            if since and entry.timestamp < since:
                continue
            results.append(entry)
            if len(results) >= limit:
                break
        return list(reversed(results))

    def export(self) -> List[Dict[str, Any]]:
        """Export audit log entries."""
        return [
            {
                "entry_id": e.entry_id,
                "timestamp": e.timestamp.isoformat(),
                "actor": e.actor,
                "action": e.action,
                "resource": e.resource,
                "result": e.result,
                "details": e.details,
                "ip_address": e.ip_address,
                "previous_hash": e.previous_hash,
                "current_hash": e.current_hash,
            }
            for e in self._entries
        ]

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    @property
    def stats(self) -> Dict[str, Any]:
        actions = Counter(e.action for e in self._entries)
        actors = Counter(e.actor for e in self._entries)
        return {
            "log_name": self._log_name,
            "total_entries": len(self._entries),
            "initialized_at": self._initialized_at.isoformat(),
            "integrity_verified": self.verify_integrity()[0],
            "top_actions": actions.most_common(5),
            "top_actors": actors.most_common(5),
        }


# ─── Secrets Manager ──────────────────────────────────────────────────────────

class SecretsManager:
    """
    Secure secrets management.

    Manages application secrets with encryption, access control,
    and audit trail.
    """

    def __init__(self, key_manager: Optional[KeyManager] = None):
        self._key_manager = key_manager or KeyManager()
        if not self._key_manager.get_active_keys():
            self._key_manager.generate_key(make_primary=True)
        self._secrets: Dict[str, Dict[str, Any]] = {}
        self._audit_log = ImmutableAuditLog("secrets")
        self._encryption_service = EncryptionService(self._key_manager)

    def store_secret(
        self,
        name: str,
        value: str,
        metadata: Optional[Dict[str, Any]] = None,
        actor: str = "system",
    ) -> str:
        """Store a secret securely. Returns secret name."""
        encrypted = self._encryption_service.encrypt(value)
        self._secrets[name] = {
            "encrypted": encrypted,
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "version": 1,
        }
        self._audit_log.record(actor, "STORE_SECRET", name, {"action": "stored"})
        return name

    def retrieve_secret(self, name: str, actor: str = "system") -> Optional[str]:
        """Retrieve and decrypt a secret."""
        secret = self._secrets.get(name)
        if not secret:
            return None
        plaintext = self._encryption_service.decrypt(secret["encrypted"])
        self._audit_log.record(actor, "RETRIEVE_SECRET", name, {"action": "retrieved"})
        return plaintext.decode('utf-8')

    def rotate_secret(
        self, name: str, new_value: str, actor: str = "system"
    ) -> bool:
        """Rotate a secret value."""
        if name not in self._secrets:
            return False
        encrypted = self._encryption_service.encrypt(new_value)
        self._secrets[name]["encrypted"] = encrypted
        self._secrets[name]["updated_at"] = datetime.utcnow().isoformat()
        self._secrets[name]["version"] += 1
        self._audit_log.record(actor, "ROTATE_SECRET", name, {"action": "rotated"})
        return True

    def delete_secret(self, name: str, actor: str = "system") -> bool:
        """Delete a secret."""
        if name in self._secrets:
            del self._secrets[name]
            self._audit_log.record(actor, "DELETE_SECRET", name, {"action": "deleted"})
            return True
        return False

    def list_secrets(self) -> List[str]:
        return list(self._secrets.keys())

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "total_secrets": len(self._secrets),
            "secret_names": self.list_secrets(),
            "audit_entries": self._audit_log.entry_count,
        }


# ─── Transport Security ───────────────────────────────────────────────────────

@dataclass
class TLSConfig:
    """TLS configuration for data in transit."""
    min_version: str = "TLSv1.3"
    cipher_suites: List[str] = field(default_factory=lambda: [
        "TLS_AES_256_GCM_SHA384",
        "TLS_CHACHA20_POLY1305_SHA256",
    ])
    require_client_cert: bool = False
    cert_path: Optional[str] = None
    key_path: Optional[str] = None
    ca_path: Optional[str] = None
    hostname_verification: bool = True


class TransportSecurity:
    """
    Transport layer security configuration and validation.

    Ensures data-in-transit uses appropriate TLS configurations.
    """

    VALID_CIPHERS = {
        "TLS_AES_256_GCM_SHA384",
        "TLS_AES_128_GCM_SHA256",
        "TLS_CHACHA20_POLY1305_SHA256",
    }

    @classmethod
    def validate_config(cls, config: TLSConfig) -> Tuple[bool, List[str]]:
        """Validate TLS configuration. Returns (valid, warnings)."""
        warnings: List[str] = []

        if config.min_version not in ("TLSv1.2", "TLSv1.3"):
            warnings.append(f"Insecure minimum TLS version: {config.min_version}")
            return False, warnings

        for cipher in config.cipher_suites:
            if cipher not in cls.VALID_CIPHERS:
                warnings.append(f"Non-standard cipher: {cipher}")

        if not config.hostname_verification:
            warnings.append("Hostname verification disabled — MITM risk")

        return len(warnings) == 0 or all(
            "Non-standard" in w for w in warnings
        ), warnings

    @classmethod
    def create_secure_config(cls) -> TLSConfig:
        """Create a secure-by-default TLS configuration."""
        return TLSConfig(
            min_version="TLSv1.3",
            require_client_cert=False,
            hostname_verification=True,
        )


# ─── Comprehensive Security Context ───────────────────────────────────────────

class SecurityContext:
    """
    Complete security context bundling all security services.

    Provides a unified interface for encryption, masking, tokenization,
    anonymization, secrets management, and audit logging.
    """

    def __init__(
        self,
        key_rotation_days: int = 90,
        audit_log_name: str = "security",
    ):
        self.key_manager = KeyManager(rotation_days=key_rotation_days)
        self.encryption = EncryptionService(self.key_manager)
        self.masker = DataMasker()
        self.tokenizer = TokenizationService()
        self.anonymizer = AnonymizationService()
        self.secrets = SecretsManager(self.key_manager)
        self.audit_log = ImmutableAuditLog(audit_log_name)
        self.transport_config = TransportSecurity.create_secure_config()

    def secure_record(
        self,
        record: Dict[str, Any],
        sensitive_fields: List[str],
        strategy: str = "encrypt",
    ) -> Dict[str, Any]:
        """Apply the specified security strategy to a record."""
        if strategy == "encrypt":
            return self.encryption.encrypt_record(record, sensitive_fields)
        elif strategy == "mask":
            strategies = {f: MaskingStrategy.PARTIAL_MASK for f in sensitive_fields}
            return self.masker.mask_record(record, strategies)
        elif strategy == "tokenize":
            return self.tokenizer.tokenize_record(record, sensitive_fields)
        elif strategy == "anonymize":
            return self.anonymizer.anonymize_record(record, sensitive_fields)
        elif strategy == "pseudonymize":
            return self.anonymizer.anonymize_record(
                record, sensitive_fields, strategy="pseudonymize"
            )
        return record

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "key_manager": self.key_manager.stats,
            "tokenizer_vault_size": self.tokenizer.vault_size,
            "audit_log": self.audit_log.stats,
            "secrets": self.secrets.stats,
            "transport": {
                "min_tls_version": self.transport_config.min_version,
                "hostname_verification": self.transport_config.hostname_verification,
            },
        }