"""
Config Manager — Versioned, schema-validated experiment configurations.

Provides:
- Configuration versioning with semantic versioning
- JSON Schema validation for experiment configs
- Config inheritance and composition
- Diff/patch between config versions
- Integration with experiment tracker
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger("enterprise.mlops_lifecycle.config_manager")


@dataclass
class ConfigSchema:
    """JSON Schema for configuration validation."""

    schema: Dict[str, Any]
    version: str = "1.0.0"
    description: str = ""

    def validate(self, config: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate config against schema. Returns (is_valid, errors)."""
        errors = []

        def check_type(value: Any, expected: str, path: str) -> None:
            type_map = {
                "string": str,
                "number": (int, float),
                "integer": int,
                "boolean": bool,
                "array": list,
                "object": dict,
            }
            if expected in type_map:
                expected_type = type_map[expected]
                if not isinstance(value, expected_type):
                    errors.append(f"{path}: expected {expected}, got {type(value).__name__}")

        def validate_object(obj: Dict[str, Any], schema_obj: Dict[str, Any], path: str) -> None:
            required = schema_obj.get("required", [])
            properties = schema_obj.get("properties", {})

            for req in required:
                if req not in obj:
                    errors.append(f"{path}.{req}: required field missing")

            for key, value in obj.items():
                if key in properties:
                    prop_schema = properties[key]
                    prop_path = f"{path}.{key}" if path else key
                    if "type" in prop_schema:
                        check_type(value, prop_schema["type"], prop_path)
                    if "enum" in prop_schema and value not in prop_schema["enum"]:
                        errors.append(f"{prop_path}: value not in enum {prop_schema['enum']}")
                    if prop_schema.get("type") == "object" and "properties" in prop_schema:
                        validate_object(value, prop_schema, prop_path)
                    if prop_schema.get("type") == "array" and "items" in prop_schema:
                        for i, item in enumerate(value):
                            if "type" in prop_schema["items"]:
                                check_type(item, prop_schema["items"]["type"], f"{prop_path}[{i}]")

        validate_object(config, self.schema, "")
        return len(errors) == 0, errors


@dataclass
class ConfigVersion:
    """A versioned configuration snapshot."""

    version_id: str
    config_id: str
    version: str  # Semantic version (e.g., "1.2.3")
    config: Dict[str, Any]
    schema_version: str
    created_at: datetime
    created_by: str
    parent_version_id: Optional[str] = None
    changelog: str = ""
    tags: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version_id": self.version_id,
            "config_id": self.config_id,
            "version": self.version,
            "config": self.config,
            "schema_version": self.schema_version,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "parent_version_id": self.parent_version_id,
            "changelog": self.changelog,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ConfigVersion:
        return cls(
            version_id=data["version_id"],
            config_id=data["config_id"],
            version=data["version"],
            config=data["config"],
            schema_version=data["schema_version"],
            created_at=datetime.fromisoformat(data["created_at"]),
            created_by=data["created_by"],
            parent_version_id=data.get("parent_version_id"),
            changelog=data.get("changelog", ""),
            tags=data.get("tags", {}),
        )


@dataclass
class ExperimentConfiguration:
    """Complete experiment configuration with metadata."""

    config_id: str
    name: str
    description: str
    current_version: ConfigVersion
    schema: ConfigSchema
    versions: List[ConfigVersion] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "config_id": self.config_id,
            "name": self.name,
            "description": self.description,
            "current_version": self.current_version.to_dict(),
            "schema": {
                "schema": self.schema.schema,
                "version": self.schema.version,
                "description": self.schema.description,
            },
            "versions": [v.to_dict() for v in self.versions],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ExperimentConfiguration:
        schema_data = data["schema"]
        schema = ConfigSchema(
            schema=schema_data["schema"],
            version=schema_data["version"],
            description=schema_data.get("description", ""),
        )
        versions = [ConfigVersion.from_dict(v) for v in data.get("versions", [])]
        current = ConfigVersion.from_dict(data["current_version"])
        return cls(
            config_id=data["config_id"],
            name=data["name"],
            description=data["description"],
            current_version=current,
            schema=schema,
            versions=versions,
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )


class ConfigValidator:
    """Validates configurations against schemas with detailed reporting."""

    def __init__(self):
        self._schemas: Dict[str, ConfigSchema] = {}

    def register_schema(self, name: str, schema: ConfigSchema) -> None:
        """Register a schema for validation."""
        self._schemas[name] = schema

    def validate(self, config: Dict[str, Any], schema_name: str) -> Tuple[bool, List[str]]:
        """Validate config against a registered schema."""
        if schema_name not in self._schemas:
            return False, [f"Schema '{schema_name}' not registered"]
        return self._schemas[schema_name].validate(config)

    def validate_experiment_config(
        self, config: ExperimentConfiguration
    ) -> Tuple[bool, List[str]]:
        """Validate an experiment configuration against its own schema."""
        return config.schema.validate(config.current_version.config)


class ConfigManager:
    """
    Manages versioned, validated experiment configurations.

    Features:
    - Semantic versioning (major.minor.patch)
    - Schema validation on every version
    - Config inheritance (base + overrides)
    - Diff/patch between versions
    - SQLite persistence
    """

    # Default schema for experiment configs
    DEFAULT_EXPERIMENT_SCHEMA = ConfigSchema(
        schema={
            "type": "object",
            "required": ["agent_type", "model_config", "prompt_config", "eval_config"],
            "properties": {
                "agent_type": {"type": "string", "enum": ["react", "plan_and_execute", "hierarchical", "swarm"]},
                "model_config": {
                    "type": "object",
                    "required": ["provider", "model_name", "temperature"],
                    "properties": {
                        "provider": {"type": "string"},
                        "model_name": {"type": "string"},
                        "temperature": {"type": "number"},
                        "max_tokens": {"type": "integer"},
                        "top_p": {"type": "number"},
                    },
                },
                "prompt_config": {
                    "type": "object",
                    "required": ["system_prompt", "user_prompt_template"],
                    "properties": {
                        "system_prompt": {"type": "string"},
                        "user_prompt_template": {"type": "string"},
                        "few_shot_examples": {"type": "array", "items": {"type": "object"}},
                    },
                },
                "tool_config": {
                    "type": "object",
                    "properties": {
                        "enabled_tools": {"type": "array", "items": {"type": "string"}},
                        "tool_timeouts": {"type": "object"},
                        "tool_retries": {"type": "object"},
                    },
                },
                "eval_config": {
                    "type": "object",
                    "required": ["metrics", "thresholds"],
                    "properties": {
                        "metrics": {"type": "array", "items": {"type": "string"}},
                        "thresholds": {"type": "object"},
                        "eval_dataset": {"type": "string"},
                    },
                },
                "rollout_config": {
                    "type": "object",
                    "properties": {
                        "strategy": {"type": "string", "enum": ["canary", "blue_green", "progressive"]},
                        "initial_percentage": {"type": "number"},
                        "max_percentage": {"type": "number"},
                        "step_percentage": {"type": "number"},
                        "health_check_interval": {"type": "integer"},
                    },
                },
            },
        },
        version="1.0.0",
        description="Default experiment configuration schema",
    )

    def __init__(self, db_path: str = "mlops_configs.db"):
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        self._validator = ConfigValidator()
        self._validator.register_schema("experiment", self.DEFAULT_EXPERIMENT_SCHEMA)
        self._init_db()

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS configs (
                    config_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    current_version_json TEXT NOT NULL,
                    schema_json TEXT NOT NULL,
                    versions_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """
            )
            conn.commit()

    @contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def create_config(
        self,
        name: str,
        config: Dict[str, Any],
        schema: Optional[ConfigSchema] = None,
        description: str = "",
        created_by: str = "system",
        version: str = "1.0.0",
    ) -> ExperimentConfiguration:
        """Create a new versioned configuration."""
        schema = schema or self.DEFAULT_EXPERIMENT_SCHEMA

        # Validate initial config
        is_valid, errors = schema.validate(config)
        if not is_valid:
            raise ValueError(f"Config validation failed: {errors}")

        config_id = f"cfg-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        version_obj = ConfigVersion(
            version_id=f"ver-{uuid.uuid4().hex[:12]}",
            config_id=config_id,
            version=version,
            config=config,
            schema_version=schema.version,
            created_at=now,
            created_by=created_by,
            changelog="Initial version",
        )

        exp_config = ExperimentConfiguration(
            config_id=config_id,
            name=name,
            description=description,
            current_version=version_obj,
            schema=schema,
            versions=[version_obj],
            created_at=now,
            updated_at=now,
        )

        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO configs
                (config_id, name, description, current_version_json, schema_json,
                 versions_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    config_id,
                    name,
                    description,
                    json.dumps(version_obj.to_dict()),
                    json.dumps({"schema": schema.schema, "version": schema.version, "description": schema.description}),
                    json.dumps([v.to_dict() for v in exp_config.versions]),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            conn.commit()

        logger.info(f"Created config {config_id}: {name} v{version}")
        return exp_config

    def get_config(self, config_id: str) -> Optional[ExperimentConfiguration]:
        """Retrieve a configuration by ID."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM configs WHERE config_id = ?", (config_id,)
            ).fetchone()
            if not row:
                return None
            return self._row_to_config(row)

    def update_config(
        self,
        config_id: str,
        new_config: Dict[str, Any],
        created_by: str = "system",
        changelog: str = "",
        version_bump: str = "patch",  # major, minor, patch
    ) -> ExperimentConfiguration:
        """Create a new version of an existing configuration."""
        exp_config = self.get_config(config_id)
        if not exp_config:
            raise ValueError(f"Config {config_id} not found")

        # Validate new config
        is_valid, errors = exp_config.schema.validate(new_config)
        if not is_valid:
            raise ValueError(f"Config validation failed: {errors}")

        # Compute new version
        current_ver = exp_config.current_version.version
        major, minor, patch = map(int, current_ver.split("."))
        if version_bump == "major":
            major += 1
            minor = 0
            patch = 0
        elif version_bump == "minor":
            minor += 1
            patch = 0
        else:
            patch += 1
        new_version = f"{major}.{minor}.{patch}"

        now = datetime.now(timezone.utc)
        new_version_obj = ConfigVersion(
            version_id=f"ver-{uuid.uuid4().hex[:12]}",
            config_id=config_id,
            version=new_version,
            config=new_config,
            schema_version=exp_config.schema.version,
            created_at=now,
            created_by=created_by,
            parent_version_id=exp_config.current_version.version_id,
            changelog=changelog,
        )

        exp_config.versions.append(new_version_obj)
        exp_config.current_version = new_version_obj
        exp_config.updated_at = now

        with self._get_conn() as conn:
            conn.execute(
                """
                UPDATE configs SET
                    current_version_json = ?,
                    versions_json = ?,
                    updated_at = ?
                WHERE config_id = ?
            """,
                (
                    json.dumps(new_version_obj.to_dict()),
                    json.dumps([v.to_dict() for v in exp_config.versions]),
                    now.isoformat(),
                    config_id,
                ),
            )
            conn.commit()

        logger.info(f"Updated config {config_id} to v{new_version}")
        return exp_config

    def get_version(self, config_id: str, version: str) -> Optional[ConfigVersion]:
        """Get a specific version of a configuration."""
        exp_config = self.get_config(config_id)
        if not exp_config:
            return None
        for v in exp_config.versions:
            if v.version == version:
                return v
        return None

    def diff_versions(
        self, config_id: str, version_a: str, version_b: str
    ) -> Dict[str, Any]:
        """Compute diff between two config versions."""
        ver_a = self.get_version(config_id, version_a)
        ver_b = self.get_version(config_id, version_b)
        if not ver_a or not ver_b:
            raise ValueError("One or both versions not found")

        return self._compute_diff(ver_a.config, ver_b.config)

    def _compute_diff(self, old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
        """Compute recursive diff between two dicts."""
        diff = {"added": {}, "removed": {}, "changed": {}, "unchanged": {}}
        all_keys = set(old.keys()) | set(new.keys())

        for key in all_keys:
            if key not in old:
                diff["added"][key] = new[key]
            elif key not in new:
                diff["removed"][key] = old[key]
            elif old[key] != new[key]:
                if isinstance(old[key], dict) and isinstance(new[key], dict):
                    nested = self._compute_diff(old[key], new[key])
                    if any(nested.values()):
                        diff["changed"][key] = nested
                    else:
                        diff["unchanged"][key] = old[key]
                else:
                    diff["changed"][key] = {"from": old[key], "to": new[key]}
            else:
                diff["unchanged"][key] = old[key]

        return diff

    def apply_patch(self, config_id: str, base_version: str, patch: Dict[str, Any]) -> ExperimentConfiguration:
        """Apply a patch to a base version to create a new version."""
        base_ver = self.get_version(config_id, base_version)
        if not base_ver:
            raise ValueError(f"Base version {base_version} not found")

        new_config = self._apply_patch_dict(base_ver.config, patch)
        return self.update_config(config_id, new_config, changelog=f"Applied patch to v{base_version}")

    def _apply_patch_dict(self, base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively apply patch to base dict."""
        result = base.copy()
        for key, value in patch.items():
            if isinstance(value, dict) and "from" in value and "to" in value:
                # Direct value change
                result[key] = value["to"]
            elif isinstance(value, dict) and key in result and isinstance(result[key], dict):
                # Nested patch
                result[key] = self._apply_patch_dict(result[key], value)
            else:
                result[key] = value
        return result

    def list_configs(
        self, limit: int = 100, offset: int = 0
    ) -> List[ExperimentConfiguration]:
        """List all configurations."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM configs ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [self._row_to_config(row) for row in rows]

    def delete_config(self, config_id: str) -> bool:
        """Delete a configuration and all its versions."""
        with self._get_conn() as conn:
            cursor = conn.execute("DELETE FROM configs WHERE config_id = ?", (config_id,))
            conn.commit()
            return cursor.rowcount > 0

    def _row_to_config(self, row: sqlite3.Row) -> ExperimentConfiguration:
        return ExperimentConfiguration.from_dict({
            "config_id": row["config_id"],
            "name": row["name"],
            "description": row["description"],
            "current_version": json.loads(row["current_version_json"]),
            "schema": json.loads(row["schema_json"]),
            "versions": json.loads(row["versions_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        })

    def register_custom_schema(self, name: str, schema: ConfigSchema) -> None:
        """Register a custom schema for validation."""
        self._validator.register_schema(name, schema)

    def validate_config(self, config: Dict[str, Any], schema_name: str = "experiment") -> Tuple[bool, List[str]]:
        """Validate a config dict against a registered schema."""
        return self._validator.validate(config, schema_name)


def create_config_manager(db_path: str = "mlops_configs.db") -> ConfigManager:
    """Factory function to create a ConfigManager."""
    return ConfigManager(db_path)