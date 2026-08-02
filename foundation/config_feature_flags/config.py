"""
Central configuration management with layered config resolution.

Layers (highest to lowest priority):
    1. Runtime overrides  (set programmatically at runtime)
    2. Environment vars    (OS environment variables)
    3. File-based config   (YAML or JSON config files)
    4. Defaults            (hardcoded sensible defaults)

Supports:
    - YAML and JSON config file loading
    - Schema-based validation
    - Environment-specific configs (dev, staging, prod)
    - Dot-notation key access
    - Config watching / hot-reload
"""

from __future__ import annotations

import copy
import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type, Union

try:
    import yaml

    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class ConfigLayer(Enum):
    """Priority-ordered configuration source layers."""
    DEFAULTS = auto()
    FILE = auto()
    ENVIRONMENT = auto()
    RUNTIME = auto()


class ConfigValidationError(Exception):
    """Raised when configuration fails schema validation."""

    def __init__(self, errors: List[str], raw_data: Optional[Dict] = None):
        self.errors = errors
        self.raw_data = raw_data
        super().__init__("\n".join(errors))


@dataclass
class ConfigSchema:
    """Schema definition for configuration validation.

    Attributes:
        required_keys: Set of keys that must be present.
        types: Mapping of key -> expected Python type.
        allowed_values: Mapping of key -> set of allowed values.
        validators: Mapping of key -> list of custom validation callbacks.
            Each callback receives (value, full_config) and returns
            Optional[str] (error message if invalid, None if valid).
        regex_patterns: Mapping of key -> regex pattern string.
        dependent_required: Mapping of key -> list of keys that must
            be present when the parent key is present.
    """

    required_keys: Set[str] = field(default_factory=set)
    types: Dict[str, Type] = field(default_factory=dict)
    allowed_values: Dict[str, Set[Any]] = field(default_factory=dict)
    validators: Dict[str, List[Callable[[Any, dict], Optional[str]]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    regex_patterns: Dict[str, str] = field(default_factory=dict)
    dependent_required: Dict[str, List[str]] = field(default_factory=dict)

    def validate(self, config: Dict[str, Any]) -> List[str]:
        """Validate *config* against this schema.

        Returns a list of error strings (empty if valid).
        """
        errors: List[str] = []

        # Required keys
        for key in self.required_keys:
            if key not in config:
                errors.append(f"Missing required key: '{key}'")

        for key, value in config.items():
            # Type checking
            if key in self.types:
                expected = self.types[key]
                if not isinstance(value, expected):
                    errors.append(
                        f"Key '{key}': expected {expected.__name__}, "
                        f"got {type(value).__name__}"
                    )

            # Allowed values
            if key in self.allowed_values:
                if value not in self.allowed_values[key]:
                    errors.append(
                        f"Key '{key}': value '{value}' not in allowed: "
                        f"{self.allowed_values[key]}"
                    )

            # Regex patterns
            if key in self.regex_patterns:
                pattern = self.regex_patterns[key]
                if isinstance(value, str) and not re.match(pattern, value):
                    errors.append(
                        f"Key '{key}': '{value}' does not match pattern '{pattern}'"
                    )

            # Custom validators
            for validator in self.validators.get(key, []):
                err = validator(value, config)
                if err is not None:
                    errors.append(f"Key '{key}': {err}")

        # Dependent required keys
        for parent, deps in self.dependent_required.items():
            if parent in config:
                for dep in deps:
                    if dep not in config:
                        errors.append(
                            f"Key '{parent}' requires '{dep}' to also be present"
                        )

        return errors


# ---------------------------------------------------------------------------
# ConfigManager
# ---------------------------------------------------------------------------


@dataclass
class _LayerSnapshot:
    """Internal snapshot of a config layer for history tracking."""
    data: Dict[str, Any]
    timestamp: float
    source: str


class ConfigManager:
    """Central configuration manager with layered resolution.

    Usage::

        mgr = ConfigManager()

        # Load defaults
        mgr.set_defaults({"host": "localhost", "port": 8080})

        # Load file (YAML or JSON)
        mgr.load_file("config.yaml")

        # Set runtime overrides
        mgr.set_override("host", "prod.example.com")

        # Resolve final value
        host = mgr.get("host")

        # Dot-notation access
        db_host = mgr.get("database.host", "fallback")

        # Validate with schema
        mgr.validate(schema)
    """

    def __init__(self, env: Optional[str] = None, env_prefix: str = "APP_"):
        """Initialize configuration manager.

        Args:
            env: Current environment name (dev, staging, prod, etc.).
                 Defaults to APP_ENV or ENVIRONMENT env var, else 'dev'.
            env_prefix: Prefix to strip from environment variables
                        when mapping to config keys (case-insensitive).
        """
        self._env: str = env or os.environ.get("APP_ENV", os.environ.get("ENVIRONMENT", "dev"))
        self._env_prefix: str = env_prefix

        # Layer storage
        self._defaults: Dict[str, Any] = {}
        self._file_configs: Dict[str, Dict[str, Any]] = {}
        self._runtime_overrides: Dict[str, Any] = {}

        # History of changes (list of snapshots per layer)
        self._history: List[Tuple[str, _LayerSnapshot]] = []
        self._max_history: int = 100

    # ------------------------------------------------------------------
    # Property access
    # ------------------------------------------------------------------

    @property
    def env(self) -> str:
        """Return the active environment name."""
        return self._env

    @env.setter
    def env(self, value: str) -> None:
        self._env = value

    # ------------------------------------------------------------------
    # Setters
    # ------------------------------------------------------------------

    def set_defaults(self, defaults: Dict[str, Any]) -> None:
        """Set the defaults layer (lowest priority)."""
        self._defaults = copy.deepcopy(defaults)
        self._record_history("defaults", self._defaults)

    def set_override(self, key: str, value: Any) -> None:
        """Set a runtime override for *key* (highest priority).

        *key* may use dot notation for nested dicts, e.g.
        ``set_override("database.host", "db.local")``.
        """
        self._set_nested(self._runtime_overrides, key, value)
        self._record_history("runtime", self._runtime_overrides)

    def set_overrides(self, overrides: Dict[str, Any]) -> None:
        """Bulk-set runtime overrides from a flat or nested dict."""
        for key, value in overrides.items():
            if isinstance(value, dict):
                for sub_key, sub_value in self._flatten(value, prefix=key):
                    self._set_nested(self._runtime_overrides, sub_key, sub_value)
            else:
                self._runtime_overrides[key] = value
        self._record_history("runtime", self._runtime_overrides)

    def remove_override(self, key: str) -> None:
        """Remove a runtime override."""
        self._delete_nested(self._runtime_overrides, key)
        self._record_history("runtime", self._runtime_overrides)

    def clear_overrides(self) -> None:
        """Remove all runtime overrides."""
        self._runtime_overrides.clear()
        self._record_history("runtime", self._runtime_overrides)

    # ------------------------------------------------------------------
    # File loading
    # ------------------------------------------------------------------

    def load_file(self, path: Union[str, Path]) -> Dict[str, Any]:
        """Load configuration from a YAML or JSON file.

        Returns the loaded dict for inspection.
        Raises FileNotFoundError if the file does not exist.
        Raises ValueError if the format is unsupported.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read()

        if path.suffix in (".yaml", ".yml"):
            if not _HAS_YAML:
                raise ImportError(
                    "PyYAML is required to load YAML config files. "
                    "Install it with: pip install pyyaml"
                )
            data = yaml.safe_load(raw) or {}
        elif path.suffix == ".json":
            data = json.loads(raw)
        else:
            raise ValueError(f"Unsupported config file format: {path.suffix}")

        self._file_configs[path.name] = data
        self._record_history("file", data)
        return data

    def load_env_specific(self, base_dir: Union[str, Path]) -> Optional[Dict[str, Any]]:
        """Load environment-specific config file from *base_dir*.

        Looks for a file named ``<env>.yaml``, ``<env>.yml``, or ``<env>.json``.
        Returns the loaded data or None if no file is found.
        """
        base = Path(base_dir)
        for suffix in (".yaml", ".yml", ".json"):
            candidate = base / f"{self._env}{suffix}"
            if candidate.exists():
                return self.load_file(candidate)
        return None

    # ------------------------------------------------------------------
    # Getters
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """Resolve *key* through all layers and return the final value.

        Dot-notation is supported: ``get("db.host")`` navigates nested
        dicts.  Returns *default* if the key is not found in any layer.
        """
        parts = key.split(".")

        # Priority order: runtime > env > file > defaults
        for source_data in (
            self._runtime_overrides,
            self._get_env_vars_as_dict(),
            self._merged_file_config(),
            self._defaults,
        ):
            value = self._resolve_parts(source_data, parts, _MISSING)
            if value is not _MISSING:
                return value

        return default

    def get_int(self, key: str, default: int = 0) -> int:
        """Resolve *key* and coerce to int."""
        return int(self.get(key, default))

    def get_float(self, key: str, default: float = 0.0) -> float:
        """Resolve *key* and coerce to float."""
        return float(self.get(key, default))

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Resolve *key* and coerce to bool.

        Supports common truthy/falsy string representations:
        'true', '1', 'yes', 'on' (case-insensitive) -> True.
        """
        raw = self.get(key, default)
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.lower() in ("true", "1", "yes", "on")
        return bool(raw)

    def get_list(self, key: str, default: Optional[List] = None) -> List:
        """Resolve *key* and coerce to list."""
        val = self.get(key, default if default is not None else [])
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            return [item.strip() for item in val.split(",") if item.strip()]
        return [val]

    def get_all(self) -> Dict[str, Any]:
        """Return a fully resolved (deep-merged) dict of all config keys."""
        merged = copy.deepcopy(self._defaults)
        # Merge file configs
        for fdata in self._file_configs.values():
            merged = _deep_merge(merged, fdata)
        # Merge env vars
        merged = _deep_merge(merged, self._get_env_vars_as_dict())
        # Merge runtime overrides
        merged = _deep_merge(merged, self._runtime_overrides)
        return merged

    def keys(self) -> Set[str]:
        """Return the set of all known top-level config keys."""
        return set(self.get_all().keys())

    # ------------------------------------------------------------------
    # Schema validation
    # ------------------------------------------------------------------

    def validate(self, schema: ConfigSchema) -> List[str]:
        """Validate the fully resolved configuration against *schema*.

        Returns a list of error strings (empty if valid).
        """
        return schema.validate(self.get_all())

    def validate_or_raise(self, schema: ConfigSchema) -> None:
        """Validate and raise ConfigValidationError on failure."""
        errors = self.validate(schema)
        if errors:
            raise ConfigValidationError(errors)

    # ------------------------------------------------------------------
    # Layer introspection
    # ------------------------------------------------------------------

    def get_layer(self, key: str) -> ConfigLayer:
        """Return which layer provided the value for *key*."""
        parts = key.split(".")
        if self._resolve_parts(self._runtime_overrides, parts, _MISSING) is not _MISSING:
            return ConfigLayer.RUNTIME
        if self._resolve_parts(self._get_env_vars_as_dict(), parts, _MISSING) is not _MISSING:
            return ConfigLayer.ENVIRONMENT
        if self._resolve_parts(self._merged_file_config(), parts, _MISSING) is not _MISSING:
            return ConfigLayer.FILE
        return ConfigLayer.DEFAULTS

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        """Return a snapshot of all layers for debugging."""
        return {
            "defaults": copy.deepcopy(self._defaults),
            "file": copy.deepcopy(self._merged_file_config()),
            "environment": copy.deepcopy(self._get_env_vars_as_dict()),
            "runtime": copy.deepcopy(self._runtime_overrides),
            "resolved": self.get_all(),
        }

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(self, limit: int = 50) -> List[Tuple[str, _LayerSnapshot]]:
        """Return recent change history."""
        return self._history[-limit:]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_env_vars_as_dict(self) -> Dict[str, Any]:
        """Collect env vars matching the prefix into a nested dict."""
        result: Dict[str, Any] = {}
        prefix = self._env_prefix.lower()
        for key, value in os.environ.items():
            if key.lower().startswith(prefix):
                config_key = key[len(self._env_prefix):].lower().replace("__", ".")
                # Try to parse JSON values
                try:
                    value = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    pass
                self._set_nested(result, config_key, value)
        return result

    def _merged_file_config(self) -> Dict[str, Any]:
        """Deep-merge all loaded file configs."""
        merged: Dict[str, Any] = {}
        for fdata in self._file_configs.values():
            merged = _deep_merge(merged, fdata)
        return merged

    def _record_history(self, source: str, data: Dict[str, Any]) -> None:
        """Record a snapshot in the change history."""
        import time

        snapshot = _LayerSnapshot(
            data=copy.deepcopy(data), timestamp=time.time(), source=source
        )
        self._history.append((source, snapshot))
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    @staticmethod
    def _resolve_parts(
        source: Dict[str, Any], parts: List[str], default: Any
    ) -> Any:
        """Walk *source* dict following *parts*; return *default* on miss."""
        current: Any = source
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default
        return current

    @staticmethod
    def _set_nested(target: Dict[str, Any], key: str, value: Any) -> None:
        """Set a value using dot-notation key in a nested dict."""
        parts = key.split(".")
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value

    @staticmethod
    def _delete_nested(target: Dict[str, Any], key: str) -> None:
        """Delete a value using dot-notation key."""
        parts = key.split(".")
        for part in parts[:-1]:
            if part not in target:
                return
            target = target[part]
        target.pop(parts[-1], None)

    @staticmethod
    def _flatten(
        nested: Dict[str, Any], prefix: str = ""
    ) -> List[Tuple[str, Any]]:
        """Flatten a nested dict into dot-notation key-value pairs."""
        result: List[Tuple[str, Any]] = []
        for key, value in nested.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                result.extend(ConfigManager._flatten(value, full_key))
            else:
                result.append((full_key, value))
        return result


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

_MISSING = object()  # sentinel


def _deep_merge(base: Dict, override: Dict) -> Dict:
    """Recursively merge *override* into *base* and return *base*."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = copy.deepcopy(value)
    return base