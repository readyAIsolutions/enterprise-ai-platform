"""
Tests for ModuleRegistry
========================
"""

import unittest

from enterprise.foundation.module_registry.registry import (
    ActivationCondition,
    ModuleMeta,
    ModulePermission,
    ModuleRegistry,
    ModuleState,
)


class TestModuleMeta(unittest.TestCase):
    """Tests for the ModuleMeta dataclass."""

    def test_create_valid_module(self) -> None:
        m = ModuleMeta(module_id="test_mod", version="1.0.0")
        self.assertEqual(m.module_id, "test_mod")
        self.assertEqual(m.version, "1.0.0")
        self.assertEqual(m.state, ModuleState.REGISTERED)
        self.assertEqual(m.dependencies, frozenset())
        self.assertEqual(m.inputs, frozenset())
        self.assertEqual(m.outputs, frozenset())

    def test_version_tuple(self) -> None:
        m = ModuleMeta(module_id="vtest", version="3.14.2")
        self.assertEqual(m.version_tuple, (3, 14, 2))

    def test_version_tuple_invalid(self) -> None:
        m = ModuleMeta(module_id="vtest", version="abc")
        self.assertEqual(m.version_tuple, (0, 0, 0))

    def test_invalid_module_id_raises(self) -> None:
        with self.assertRaises(ValueError):
            ModuleMeta(module_id="123bad", version="1.0.0")

    def test_module_id_with_underscores(self) -> None:
        m = ModuleMeta(module_id="my_module_2", version="1.0.0")
        self.assertEqual(m.module_id, "my_module_2")

    def test_conditional_without_callable_raises(self) -> None:
        with self.assertRaises(ValueError):
            ModuleMeta(
                module_id="cond_test",
                version="1.0.0",
                activation_condition=ActivationCondition.CONDITIONAL,
            )

    def test_conditional_with_callable_succeeds(self) -> None:
        m = ModuleMeta(
            module_id="cond_ok",
            version="1.0.0",
            activation_condition=ActivationCondition.CONDITIONAL,
            activation_callable=lambda: True,
        )
        self.assertIsNotNone(m.activation_callable)

    def test_required_permissions_not_in_permissions_raises(self) -> None:
        perm = ModulePermission(name="read:data", level=1)
        with self.assertRaises(ValueError):
            ModuleMeta(
                module_id="perm_test",
                permissions=frozenset({perm}),
                required_permissions=frozenset({"write:data"}),
            )

    def test_hash_and_eq(self) -> None:
        a = ModuleMeta(module_id="mod_a", version="1.0.0")
        b = ModuleMeta(module_id="mod_a", version="2.0.0")
        c = ModuleMeta(module_id="mod_b", version="1.0.0")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertEqual(hash(a), hash(b))
        self.assertEqual(len({a, b, c}), 2)

    def test_full_module_meta(self) -> None:
        perms = frozenset({
            ModulePermission(name="read:config", description="Read config", category="io", level=2),
            ModulePermission(name="write:config", description="Write config", category="io", level=5),
        })
        m = ModuleMeta(
            module_id="full_mod",
            version="2.5.1",
            display_name="Full Module",
            description="A fully specified module for testing",
            author="Test Team",
            dependencies=frozenset({"dep_a", "dep_b"}),
            inputs=frozenset({"config_data", "user_input"}),
            outputs=frozenset({"results", "logs"}),
            permissions=perms,
            required_permissions=frozenset({"read:config"}),
            activation_condition=ActivationCondition.DEPENDENCIES_READY,
            entry_point="run",
            metadata={"key": "value"},
        )
        self.assertEqual(m.display_name, "Full Module")
        self.assertEqual(len(m.permissions), 2)
        self.assertEqual(m.required_permissions, frozenset({"read:config"}))


class TestModulePermission(unittest.TestCase):
    """Tests for the ModulePermission dataclass."""

    def test_valid_permission(self) -> None:
        p = ModulePermission(name="read:db", description="Read database", category="data", level=3)
        self.assertEqual(p.name, "read:db")
        self.assertEqual(p.level, 3)

    def test_invalid_level_low(self) -> None:
        with self.assertRaises(ValueError):
            ModulePermission(name="bad", level=-1)

    def test_invalid_level_high(self) -> None:
        with self.assertRaises(ValueError):
            ModulePermission(name="bad", level=11)

    def test_permission_equality_by_name(self) -> None:
        a = ModulePermission(name="perm_a", level=1)
        b = ModulePermission(name="perm_a", level=9)
        self.assertEqual(a, b)
        self.assertEqual(hash(a), hash(b))

    def test_permission_inequality_by_name(self) -> None:
        a = ModulePermission(name="perm_a")
        b = ModulePermission(name="perm_b")
        self.assertNotEqual(a, b)


class TestModuleRegistryRegistration(unittest.TestCase):
    """Tests for module registration, lookup, and unregistration."""

    def setUp(self) -> None:
        self.registry = ModuleRegistry()

    def test_register_module(self) -> None:
        m = ModuleMeta(module_id="core", version="1.0.0")
        self.registry.register(m)
        self.assertEqual(self.registry.module_count, 1)
        self.assertIs(self.registry.get("core"), m)

    def test_register_duplicate_raises(self) -> None:
        self.registry.register(ModuleMeta(module_id="dup"))
        with self.assertRaises(ValueError):
            self.registry.register(ModuleMeta(module_id="dup", version="2.0.0"))

    def test_update_module(self) -> None:
        self.registry.register(ModuleMeta(module_id="upd", version="1.0.0"))
        updated = ModuleMeta(module_id="upd", version="2.0.0")
        self.registry.update(updated)
        self.assertEqual(self.registry.get("upd").version, "2.0.0")

    def test_update_unregistered_raises(self) -> None:
        with self.assertRaises(KeyError):
            self.registry.update(ModuleMeta(module_id="nope"))

    def test_unregister_module(self) -> None:
        self.registry.register(ModuleMeta(module_id="rm"))
        removed = self.registry.unregister("rm")
        self.assertEqual(removed.module_id, "rm")
        self.assertIsNone(self.registry.get("rm"))

    def test_unregister_with_dependents_raises(self) -> None:
        self.registry.register(ModuleMeta(module_id="base"))
        self.registry.register(ModuleMeta(
            module_id="child",
            dependencies=frozenset({"base"}),
        ))
        with self.assertRaises(ValueError):
            self.registry.unregister("base")

    def test_list_all(self) -> None:
        self.registry.register(ModuleMeta(module_id="a"))
        self.registry.register(ModuleMeta(module_id="b"))
        self.assertEqual(len(self.registry.list_all()), 2)

    def test_filter_by_state(self) -> None:
        self.registry.register(ModuleMeta(module_id="a"))
        self.registry.register(ModuleMeta(module_id="b"))
        self.registry.enable("a")
        enabled = self.registry.filter_by_state(ModuleState.ENABLED)
        self.assertEqual(len(enabled), 1)
        self.assertEqual(enabled[0].module_id, "a")


class TestModuleRegistryDependencies(unittest.TestCase):
    """Tests for dependency queries and resolution."""

    def setUp(self) -> None:
        self.registry = ModuleRegistry()
        self.registry.register(ModuleMeta(module_id="A"))
        self.registry.register(ModuleMeta(module_id="B", dependencies=frozenset({"A"})))
        self.registry.register(ModuleMeta(module_id="C", dependencies=frozenset({"B"})))
        self.registry.register(ModuleMeta(module_id="D"))
        self.registry.register(ModuleMeta(
            module_id="E", dependencies=frozenset({"A", "D"})
        ))

    def test_dependencies_of(self) -> None:
        self.assertEqual(self.registry.dependencies_of("B"), frozenset({"A"}))
        self.assertEqual(self.registry.dependencies_of("A"), frozenset())

    def test_dependents_of(self) -> None:
        self.assertEqual(self.registry.dependents_of("A"), frozenset({"B", "E"}))
        self.assertEqual(self.registry.dependents_of("C"), frozenset())

    def test_all_dependencies_transitive(self) -> None:
        deps = self.registry.all_dependencies("C")
        self.assertIn("B", deps)
        self.assertIn("A", deps)
        self.assertNotIn("C", deps)  # Not self-referential
        self.assertNotIn("D", deps)

    def test_all_dependencies_leaf(self) -> None:
        deps = self.registry.all_dependencies("A")
        self.assertEqual(deps, frozenset())


class TestModuleRegistryTopologicalSort(unittest.TestCase):
    """Tests for topological sort (activation order)."""

    def setUp(self) -> None:
        self.registry = ModuleRegistry()
        # Build a diamond: A -> B, A -> C; B -> D; C -> D
        self.registry.register(ModuleMeta(module_id="A"))
        self.registry.register(ModuleMeta(module_id="B", dependencies=frozenset({"A"})))
        self.registry.register(ModuleMeta(module_id="C", dependencies=frozenset({"A"})))
        self.registry.register(ModuleMeta(module_id="D", dependencies=frozenset({"B", "C"})))

    def test_linearisation(self) -> None:
        order = [m.module_id for m in self.registry.resolve_activation_order()]
        # A must come before B and C
        self.assertLess(order.index("A"), order.index("B"))
        self.assertLess(order.index("A"), order.index("C"))
        # B and C must come before D
        self.assertLess(order.index("B"), order.index("D"))
        self.assertLess(order.index("C"), order.index("D"))

    def test_subset_resolution(self) -> None:
        order = [m.module_id for m in self.registry.resolve_activation_order(["D"])]
        self.assertIn("A", order)
        self.assertIn("B", order)
        self.assertIn("C", order)
        self.assertIn("D", order)
        self.assertLess(order.index("A"), order.index("B"))
        self.assertLess(order.index("C"), order.index("D"))

    def test_single_leaf_resolution(self) -> None:
        order = [m.module_id for m in self.registry.resolve_activation_order(["B"])]
        self.assertEqual(order, ["A", "B"])

    def test_circular_dependency_detected(self) -> None:
        # Create cycle: X -> Y -> X
        self.registry.register(ModuleMeta(module_id="X", dependencies=frozenset({"Y"})))
        self.registry.register(ModuleMeta(module_id="Y", dependencies=frozenset({"X"})))
        self.assertTrue(self.registry.has_cycles())

    def test_find_cycle(self) -> None:
        self.registry.register(ModuleMeta(module_id="X", dependencies=frozenset({"Y"})))
        self.registry.register(ModuleMeta(module_id="Y", dependencies=frozenset({"X"})))
        cycle = self.registry.find_cycle()
        self.assertIsNotNone(cycle)
        self.assertIn("X", cycle)
        self.assertIn("Y", cycle)

    def test_no_cycle_in_acyclic(self) -> None:
        self.assertFalse(self.registry.has_cycles())
        self.assertIsNone(self.registry.find_cycle())

    def test_resolve_with_cycle_raises(self) -> None:
        self.registry.register(ModuleMeta(module_id="X", dependencies=frozenset({"Y"})))
        self.registry.register(ModuleMeta(module_id="Y", dependencies=frozenset({"X"})))
        with self.assertRaises(ValueError):
            self.registry.resolve_activation_order()


class TestModuleRegistryLifecycle(unittest.TestCase):
    """Tests for enable, disable, activate, deactivate."""

    def setUp(self) -> None:
        self.registry = ModuleRegistry()
        self.registry.register(ModuleMeta(module_id="base"))
        self.registry.register(ModuleMeta(
            module_id="child",
            dependencies=frozenset({"base"}),
        ))

    def test_enable_module(self) -> None:
        self.registry.enable("base")
        self.assertEqual(self.registry.get("base").state, ModuleState.ENABLED)

    def test_enable_with_disabled_dependency_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.registry.enable("child")

    def test_enable_chain(self) -> None:
        self.registry.enable("base")
        self.registry.enable("child")
        self.assertEqual(self.registry.get("child").state, ModuleState.ENABLED)

    def test_enable_already_enabled_is_noop(self) -> None:
        self.registry.enable("base")
        self.registry.enable("base")  # Should not raise
        self.assertEqual(self.registry.get("base").state, ModuleState.ENABLED)

    def test_disable_module(self) -> None:
        self.registry.enable("base")
        self.registry.disable("base")
        self.assertEqual(self.registry.get("base").state, ModuleState.DISABLED)

    def test_disable_with_active_dependent_raises(self) -> None:
        self.registry.enable("base")
        self.registry.enable("child")
        self.registry.activate("base")
        self.registry.activate("child")
        with self.assertRaises(ValueError):
            self.registry.disable("base")

    def test_activate_module(self) -> None:
        self.registry.enable("base")
        self.registry.activate("base")
        self.assertEqual(self.registry.get("base").state, ModuleState.ACTIVE)

    def test_activate_without_enable_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.registry.activate("base")

    def test_deactivate_module(self) -> None:
        self.registry.enable("base")
        self.registry.activate("base")
        self.registry.deactivate("base")
        self.assertEqual(self.registry.get("base").state, ModuleState.ENABLED)

    def test_deactivate_with_active_dependent_raises(self) -> None:
        self.registry.enable("base")
        self.registry.enable("child")
        self.registry.activate("base")
        self.registry.activate("child")
        with self.assertRaises(ValueError):
            self.registry.deactivate("base")

    def test_set_error(self) -> None:
        self.registry.enable("base")
        self.registry.set_error("base", "Something went wrong")
        self.assertEqual(self.registry.get("base").state, ModuleState.ERROR)
        self.assertEqual(self.registry.get("base").metadata["error"], "Something went wrong")

    def test_activate_with_never_condition_raises(self) -> None:
        self.registry.register(ModuleMeta(
            module_id="never_mod",
            activation_condition=ActivationCondition.NEVER,
        ))
        # Must enable first
        never_mod = self.registry.get("never_mod")
        never_mod.state = ModuleState.ENABLED
        self.registry._modules["never_mod"] = never_mod
        with self.assertRaises(ValueError):
            self.registry.activate("never_mod")

    def test_activate_with_conditional_callable(self) -> None:
        self.registry.register(ModuleMeta(
            module_id="cond_mod",
            activation_condition=ActivationCondition.CONDITIONAL,
            activation_callable=lambda: True,
        ))
        cond_mod = self.registry.get("cond_mod")
        cond_mod.state = ModuleState.ENABLED
        self.registry._modules["cond_mod"] = cond_mod
        self.registry.activate("cond_mod")
        self.assertEqual(self.registry.get("cond_mod").state, ModuleState.ACTIVE)

    def test_activate_with_failing_callable_raises(self) -> None:
        self.registry.register(ModuleMeta(
            module_id="fail_mod",
            activation_condition=ActivationCondition.CONDITIONAL,
            activation_callable=lambda: False,
        ))
        fail_mod = self.registry.get("fail_mod")
        fail_mod.state = ModuleState.ENABLED
        self.registry._modules["fail_mod"] = fail_mod
        with self.assertRaises(ValueError):
            self.registry.activate("fail_mod")


class TestModuleRegistryVersionManagement(unittest.TestCase):
    """Tests for version querying and comparison."""

    def setUp(self) -> None:
        self.registry = ModuleRegistry()
        self.registry.register(ModuleMeta(module_id="lib", version="2.1.0"))

    def test_get_version(self) -> None:
        self.assertEqual(self.registry.get_version("lib"), "2.1.0")

    def test_get_version_unregistered_raises(self) -> None:
        with self.assertRaises(KeyError):
            self.registry.get_version("nope")

    def test_check_version_satisfies_ok(self) -> None:
        self.assertTrue(self.registry.check_version_satisfies("lib", "2.0.0"))
        self.assertTrue(self.registry.check_version_satisfies("lib", "2.1.0"))

    def test_check_version_satisfies_fail(self) -> None:
        self.assertFalse(self.registry.check_version_satisfies("lib", "3.0.0"))

    def test_check_version_satisfies_partial(self) -> None:
        # 2.1.0 >= 2.1 (pad with zeros)
        self.assertTrue(self.registry.check_version_satisfies("lib", "2.1"))

    def test_check_version_satisfies_invalid_required(self) -> None:
        self.assertFalse(self.registry.check_version_satisfies("lib", "abc"))


if __name__ == "__main__":
    unittest.main()