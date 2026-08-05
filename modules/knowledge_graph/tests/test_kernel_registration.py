"""Kernel lifecycle registration tests for knowledge_graph.

Verifies the module registers with the ENI Platform Kernel via the @module
decorator, that initialize() boots it to HEALTHY, and that health_check()
returns a valid HealthStatus.
"""
import sys
import asyncio
import importlib

import pytest

sys.path.insert(0, "/home/hunter/Desktop/Enterprise Builder")

from enterprise.platform_kernel import HealthStatus, ModuleRegistry

MODULE_NAME = "knowledge_graph"
MODULE_CLASS = "KnowledgeGraphModule"
FACTORY = "create_knowledge_graph_module"


def _module():
    return importlib.import_module("enterprise.modules.knowledge_graph")


def _init(inst):
    asyncio.run(inst.initialize())


def test_module_registers_with_kernel():
    mod = _module()
    assert hasattr(mod, MODULE_CLASS)
    cls = getattr(mod, MODULE_CLASS)
    # The @module decorator stamps the registry name onto the class.
    assert cls._meta_name == MODULE_NAME
    assert cls._meta_version


def test_discovery_binds_module_class():
    reg = ModuleRegistry()
    reg.discover()
    record = reg.get_record(MODULE_NAME)
    assert record is not None
    assert record.module_class is not None


def test_initialize_sets_healthy():
    mod = _module()
    inst = getattr(mod, FACTORY)({})
    _init(inst)
    assert inst.status == HealthStatus.HEALTHY


def test_health_check_returns_status():
    mod = _module()
    inst = getattr(mod, FACTORY)({})
    _init(inst)
    status = asyncio.run(inst.health_check())
    assert isinstance(status, HealthStatus)
    assert status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)


def test_shutdown():
    mod = _module()
    inst = getattr(mod, FACTORY)({})
    _init(inst)
    asyncio.run(inst.shutdown())
    assert inst._component is None
