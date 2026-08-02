"""
Tests for ConfigManager.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

import sys
from pathlib import Path

# Ensure the project root is on the import path
_project_root = Path(__file__).resolve().parents[5]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from enterprise.foundation.config_feature_flags.config import (
    ConfigLayer,
    ConfigManager,
    ConfigSchema,
    ConfigValidationError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def manager():
    """Return a fresh ConfigManager for each test."""
    return ConfigManager(env="test", env_prefix="TEST_")


@pytest.fixture
def temp_yaml():
    """Create a temporary YAML file and return its path."""
    try:
        import yaml
    except ImportError:
        pytest.skip("PyYAML not installed")

    content = {
        "host": "yaml.example.com",
        "port": 9090,
        "database": {
            "host": "db.yaml.internal",
            "name": "mydb",
        },
        "features": {
            "dark_mode": True,
            "beta": False,
        },
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as fh:
        yaml.dump(content, fh)
        path = fh.name
    yield Path(path)
    os.unlink(path)


@pytest.fixture
def temp_json():
    """Create a temporary JSON file and return its path."""
    content = {
        "host": "json.example.com",
        "port": 8080,
        "log_level": "debug",
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
        json.dump(content, fh)
        path = fh.name
    yield Path(path)
    os.unlink(path)


# ---------------------------------------------------------------------------
# Basic resolution tests
# ---------------------------------------------------------------------------

class TestConfigManagerBasic:
    """Tests for basic get/set resolution."""

    def test_defaults(self, manager):
        manager.set_defaults({"host": "localhost", "port": 8000})
        assert manager.get("host") == "localhost"
        assert manager.get("port") == 8000
        assert manager.get("nonexistent", "fallback") == "fallback"

    def test_runtime_override(self, manager):
        manager.set_defaults({"host": "localhost"})
        manager.set_override("host", "override.example.com")
        assert manager.get("host") == "override.example.com"

    def test_env_var_override(self, manager):
        manager.set_defaults({"host": "localhost"})
        os.environ["TEST_HOST"] = "env.example.com"
        try:
            assert manager.get("host") == "env.example.com"
        finally:
            del os.environ["TEST_HOST"]

    def test_nested_dot_notation(self, manager):
        manager.set_defaults({"db": {"host": "localhost", "port": 5432}})
        assert manager.get("db.host") == "localhost"
        assert manager.get("db.port") == 5432
        assert manager.get("db.nonexistent", "default") == "default"

    def test_get_all(self, manager):
        manager.set_defaults({"a": 1, "b": 2})
        manager.set_override("c", 3)
        all_config = manager.get_all()
        assert all_config["a"] == 1
        assert all_config["c"] == 3

    def test_get_typed_methods(self, manager):
        manager.set_defaults({
            "int_val": "42",
            "float_val": "3.14",
            "bool_val": "true",
            "list_val": "a,b,c",
        })
        assert manager.get_int("int_val") == 42
        assert abs(manager.get_float("float_val") - 3.14) < 0.001
        assert manager.get_bool("bool_val") is True
        assert manager.get_list("list_val") == ["a", "b", "c"]

    def test_bool_parsing(self, manager):
        for true_val in ("true", "True", "1", "yes", "on"):
            manager.set_override("test", true_val)
            assert manager.get_bool("test") is True
        for false_val in ("false", "False", "0", "no", "off", "anything_else"):
            manager.set_override("test", false_val)
            assert manager.get_bool("test") is False


# ---------------------------------------------------------------------------
# Layer introspection tests
# ---------------------------------------------------------------------------

class TestConfigLayers:
    """Tests for layer introspection."""

    def test_get_layer_defaults(self, manager):
        manager.set_defaults({"key": "default"})
        assert manager.get_layer("key") == ConfigLayer.DEFAULTS

    def test_get_layer_runtime(self, manager):
        manager.set_defaults({"key": "default"})
        manager.set_override("key", "override")
        assert manager.get_layer("key") == ConfigLayer.RUNTIME

    def test_get_layer_env(self, manager):
        manager.set_defaults({"key": "default"})
        os.environ["TEST_KEY"] = "env_val"
        try:
            assert manager.get_layer("key") == ConfigLayer.ENVIRONMENT
        finally:
            del os.environ["TEST_KEY"]

    def test_snapshot(self, manager):
        manager.set_defaults({"a": 1})
        manager.set_override("b", 2)
        snap = manager.snapshot()
        assert "defaults" in snap
        assert "runtime" in snap
        assert "environment" in snap
        assert "resolved" in snap
        assert snap["defaults"]["a"] == 1
        assert snap["runtime"]["b"] == 2


# ---------------------------------------------------------------------------
# File loading tests
# ---------------------------------------------------------------------------

class TestFileLoading:
    """Tests for YAML/JSON file loading."""

    def test_load_yaml(self, manager, temp_yaml):
        manager.load_file(temp_yaml)
        assert manager.get("host") == "yaml.example.com"
        assert manager.get("port") == 9090
        assert manager.get("database.host") == "db.yaml.internal"

    def test_load_json(self, manager, temp_json):
        manager.load_file(temp_json)
        assert manager.get("host") == "json.example.com"
        assert manager.get("port") == 8080
        assert manager.get("log_level") == "debug"

    def test_load_nonexistent_file(self, manager):
        with pytest.raises(FileNotFoundError):
            manager.load_file("/nonexistent/path/config.yaml")

    def test_load_unsupported_format(self, manager):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as fh:
            fh.write("hello")
            path = fh.name
        try:
            with pytest.raises(ValueError, match="Unsupported"):
                manager.load_file(path)
        finally:
            os.unlink(path)

    def test_multiple_files_merged(self, manager, temp_yaml, temp_json):
        manager.load_file(temp_yaml)
        manager.load_file(temp_json)
        # host from JSON should override YAML (JSON loaded second)
        assert manager.get("host") == "json.example.com"
        # YAML-only key should remain
        assert manager.get("database.host") == "db.yaml.internal"

    def test_env_specific_load(self, manager, temp_yaml):
        # Rename temp_yaml to test.yaml (matching env)
        import shutil
        base_dir = temp_yaml.parent
        dest = base_dir / "test.yaml"
        shutil.copy(temp_yaml, dest)
        try:
            result = manager.load_env_specific(base_dir)
            assert result is not None
            assert result["host"] == "yaml.example.com"
        finally:
            os.unlink(dest)


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    """Tests for ConfigSchema validation."""

    def test_required_keys(self, manager):
        schema = ConfigSchema(required_keys={"host", "port"})
        manager.set_defaults({"host": "localhost"})
        errors = manager.validate(schema)
        assert any("Missing required key" in e for e in errors)
        assert any("port" in e for e in errors)

    def test_type_checking(self, manager):
        schema = ConfigSchema(types={"port": int})
        manager.set_defaults({"port": "not_an_int"})
        errors = manager.validate(schema)
        assert any("expected int" in e for e in errors)

    def test_allowed_values(self, manager):
        schema = ConfigSchema(allowed_values={"env": {"dev", "staging", "prod"}})
        manager.set_defaults({"env": "invalid"})
        errors = manager.validate(schema)
        assert any("not in allowed" in e for e in errors)

    def test_regex_patterns(self, manager):
        schema = ConfigSchema(
            regex_patterns={"email": r"^[^@]+@[^@]+\.[^@]+$"}
        )
        manager.set_defaults({"email": "not-an-email"})
        errors = manager.validate(schema)
        assert any("does not match pattern" in e for e in errors)

        manager.set_defaults({"email": "user@example.com"})
        errors = manager.validate(schema)
        assert len(errors) == 0

    def test_custom_validators(self, manager):
        def port_in_range(value, config):
            if not (1 <= value <= 65535):
                return f"Port {value} out of range"
            return None

        schema = ConfigSchema(types={"port": int})
        schema.validators["port"].append(port_in_range)

        manager.set_defaults({"port": 99999})
        errors = manager.validate(schema)
        assert any("out of range" in e for e in errors)

    def test_dependent_required(self, manager):
        schema = ConfigSchema(
            required_keys={"db_host"},
            dependent_required={"use_ssl": ["ssl_cert_path"]},
        )
        manager.set_defaults({"db_host": "localhost", "use_ssl": True})
        errors = manager.validate(schema)
        assert any("requires" in e for e in errors)

    def test_validate_or_raise(self, manager):
        schema = ConfigSchema(required_keys={"must_exist"})
        with pytest.raises(ConfigValidationError):
            manager.validate_or_raise(schema)

    def test_valid_config_passes(self, manager):
        schema = ConfigSchema(
            required_keys={"host"},
            types={"host": str, "port": int},
            allowed_values={"env": {"dev", "prod"}},
        )
        manager.set_defaults({"host": "localhost", "port": 8080, "env": "dev"})
        errors = manager.validate(schema)
        assert len(errors) == 0


# ---------------------------------------------------------------------------
# Override management tests
# ---------------------------------------------------------------------------

class TestOverrideManagement:
    """Tests for runtime override management."""

    def test_set_nested_override(self, manager):
        manager.set_override("a.b.c", 42)
        assert manager.get("a.b.c") == 42

    def test_bulk_overrides(self, manager):
        manager.set_defaults({"x": 0, "y": 0, "z": 0})
        manager.set_overrides({"x": 1, "y": 2})
        assert manager.get("x") == 1
        assert manager.get("y") == 2
        assert manager.get("z") == 0  # unchanged

    def test_remove_override(self, manager):
        manager.set_defaults({"key": "default"})
        manager.set_override("key", "override")
        assert manager.get("key") == "override"
        manager.remove_override("key")
        assert manager.get("key") == "default"

    def test_clear_overrides(self, manager):
        manager.set_defaults({"a": 1, "b": 2})
        manager.set_overrides({"a": 10, "b": 20})
        manager.clear_overrides()
        assert manager.get("a") == 1
        assert manager.get("b") == 2

    def test_remove_nonexistent_override(self, manager):
        # Should not raise
        manager.remove_override("nonexistent.key")


# ---------------------------------------------------------------------------
# History tests
# ---------------------------------------------------------------------------

class TestHistory:
    """Tests for change history."""

    def test_history_recorded(self, manager):
        manager.set_defaults({"key": "v1"})
        manager.set_defaults({"key": "v2"})
        history = manager.get_history()
        assert len(history) >= 1

    def test_history_truncation(self, manager):
        manager._max_history = 5
        for i in range(10):
            manager.set_override(f"key_{i}", i)
        assert len(manager.get_history()) <= 5


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge case tests."""

    def test_empty_manager(self, manager):
        assert manager.get("anything") is None
        assert manager.get("anything", "fallback") == "fallback"
        assert manager.get_all() == {}

    def test_env_var_json_values(self, manager):
        os.environ["TEST_DATA"] = '{"nested": {"key": 123}}'
        try:
            val = manager.get("data")
            assert val == {"nested": {"key": 123}}
        finally:
            del os.environ["TEST_DATA"]

    def test_env_var_double_underscore(self, manager):
        os.environ["TEST_DB__HOST"] = "pg.local"
        try:
            assert manager.get("db.host") == "pg.local"
        finally:
            del os.environ["TEST_DB__HOST"]

    def test_env_prefix_override(self):
        mgr = ConfigManager(env_prefix="MYAPP_")
        mgr.set_defaults({"key": "default"})
        os.environ["MYAPP_KEY"] = "from_env"
        try:
            assert mgr.get("key") == "from_env"
        finally:
            del os.environ["MYAPP_KEY"]

    def test_keys_method(self, manager):
        manager.set_defaults({"a": 1, "b": 2})
        manager.set_override("c", 3)
        assert "a" in manager.keys()
        assert "b" in manager.keys()
        assert "c" in manager.keys()

    def test_default_env_from_os(self):
        os.environ["APP_ENV"] = "staging"
        try:
            mgr = ConfigManager()
            assert mgr.env == "staging"
        finally:
            del os.environ["APP_ENV"]