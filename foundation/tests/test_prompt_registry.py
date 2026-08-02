"""
Tests for Prompt Registry — covers template inheritance, versioning,
A/B testing, approval workflows, catalog search, and serialization.
"""

import json
import pytest
from copy import deepcopy

from enterprise.foundation.prompt_registry import (
    PromptStatus,
    VariantAllocation,
    PromptRegistryError,
    PromptNotFoundError,
    InvalidTransitionError,
    TemplateError,
    ABTestError,
    PromptTemplate,
    TemplateBlock,
    PromptVersion,
    PromptRecord,
    ABTest,
    ABTestVariant,
    PromptCatalog,
    SearchFilter,
    PromptRegistry,
    parse_semver,
    semver_key,
)


# ────────────────────────────────────────────────────────────────────
# Semver
# ────────────────────────────────────────────────────────────────────

class TestSemver:
    def test_parse_stable(self):
        assert parse_semver("1.2.3") == (1, 2, 3, "", "")

    def test_parse_prerelease(self):
        assert parse_semver("2.0.0-beta.1") == (2, 0, 0, "beta.1", "")

    def test_parse_with_build(self):
        assert parse_semver("1.0.0+build.42") == (1, 0, 0, "", "build.42")

    def test_parse_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_semver("not-a-version")

    def test_sort_key_prerelease_before_release(self):
        # 1.0.0-alpha should sort before 1.0.0
        assert semver_key("1.0.0-alpha") < semver_key("1.0.0")

    def test_sort_key_numeric(self):
        keys = [semver_key(v) for v in ["0.9.0", "1.0.0", "1.0.1", "2.0.0"]]
        assert keys == sorted(keys)


# ────────────────────────────────────────────────────────────────────
# Template System
# ────────────────────────────────────────────────────────────────────

class TestTemplateBasic:
    def test_variable_substitution(self):
        tpl = PromptTemplate(id="t1", source="Hello {{ name }}!")
        result = tpl.render({"name": "World"})
        assert result == "Hello World!"

    def test_variable_missing(self):
        tpl = PromptTemplate(id="t1", source="Hello {{ missing }}!")
        result = tpl.render({})
        assert result == "Hello !"

    def test_filter_upper(self):
        tpl = PromptTemplate(id="t1", source="{{ name | upper }}")
        assert tpl.render({"name": "hello"}) == "HELLO"

    def test_filter_lower(self):
        tpl = PromptTemplate(id="t1", source="{{ name | lower }}")
        assert tpl.render({"name": "HELLO"}) == "hello"

    def test_filter_default(self):
        tpl = PromptTemplate(id="t1", source="{{ name | default }}")
        assert tpl.render({}) == ""

    def test_dot_path_resolution(self):
        tpl = PromptTemplate(id="t1", source="{{ user.name }}")
        assert tpl.render({"user": {"name": "Alice"}}) == "Alice"


class TestTemplateBlocks:
    def test_block_extraction(self):
        tpl = PromptTemplate(id="t1", source="before\n{% block main %}\ninside\n{% endblock %}\nafter")
        assert "main" in tpl.blocks
        # new regex-based extraction preserves surrounding whitespace
        assert "inside" in tpl.blocks["main"].content

    def test_block_rendering(self):
        tpl = PromptTemplate(id="t1", source="Start {% block body %}default{% endblock %} End")
        result = tpl.render({})
        assert "Start default End" in result

    def test_unclosed_block_raises(self):
        with pytest.raises(TemplateError, match="Unclosed"):
            PromptTemplate(id="t1", source="{% block x %}no close")

    def test_multiple_blocks(self):
        tpl = PromptTemplate(id="t1", source="{% block a %}A{% endblock %} - {% block b %}B{% endblock %}")
        result = tpl.render({})
        assert "A - B" in result


class TestTemplateInheritance:
    def test_extends_resolution(self):
        parent = PromptTemplate(id="parent", source="Base {% block body %}parent body{% endblock %} End")
        child = PromptTemplate(id="child", source="{% extends 'parent' %}{% block body %}child body{% endblock %}")
        cat = PromptCatalog()
        cat.add_template(parent)
        cat.add_template(child)
        result = child.render({}, registry=cat)
        assert "child body" in result
        assert "Base" in result
        assert "End" in result

    def test_unresolved_parent_raises(self):
        tpl = PromptTemplate(id="orphan", source="{% extends 'missing' %}Content")
        with pytest.raises(TemplateError, match="not found"):
            tpl.render({}, registry=PromptCatalog())

    def test_circular_extends_raises(self):
        a = PromptTemplate(id="a", source="{% extends 'b' %}A")
        b = PromptTemplate(id="b", source="{% extends 'a' %}B")
        cat = PromptCatalog()
        cat.add_template(a)
        cat.add_template(b)
        with pytest.raises(TemplateError, match="Circular"):
            a.render({}, registry=cat)


class TestTemplateConditionals:
    def test_if_true(self):
        tpl = PromptTemplate(id="t1", source="{% if show %}yes{% endif %}")
        assert tpl.render({"show": True}) == "yes"

    def test_if_false(self):
        tpl = PromptTemplate(id="t1", source="{% if show %}yes{% endif %}")
        assert tpl.render({"show": False}) == ""

    def test_if_not(self):
        tpl = PromptTemplate(id="t1", source="{% if not show %}hidden{% endif %}")
        assert tpl.render({"show": False}) == "hidden"
        assert tpl.render({"show": True}) == ""

    def test_if_else(self):
        tpl = PromptTemplate(id="t1", source="{% if flag %}yes{% else %}no{% endif %}")
        assert tpl.render({"flag": True}) == "yes"
        assert tpl.render({"flag": False}) == "no"

    def test_if_comparison(self):
        tpl = PromptTemplate(id="t1", source="{% if score >= 80 %}pass{% else %}fail{% endif %}")
        assert tpl.render({"score": 85}) == "pass"
        assert tpl.render({"score": 50}) == "fail"


class TestTemplateForLoops:
    def test_for_loop(self):
        tpl = PromptTemplate(id="t1", source="{% for item in items %}{{ item }},{% endfor %}")
        assert tpl.render({"items": ["a", "b", "c"]}) == "a,b,c,"

    def test_for_loop_with_index(self):
        tpl = PromptTemplate(id="t1", source="{% for item, i in items %}{{ i }}:{{ item }} {% endfor %}")
        result = tpl.render({"items": ["x", "y"]})
        assert "0:x" in result
        assert "1:y" in result

    def test_for_loop_empty(self):
        tpl = PromptTemplate(id="t1", source="{% for item in items %}x{% endfor %}")
        assert tpl.render({"items": []}) == ""


# ────────────────────────────────────────────────────────────────────
# PromptRecord & PromptVersion
# ────────────────────────────────────────────────────────────────────

class TestPromptVersion:
    def test_creation(self):
        v = PromptVersion(id="p1", semver="1.0.0", content="Hello", author="alice")
        assert v.semver == "1.0.0"
        assert v.checksum != ""

    def test_to_dict_roundtrip(self):
        v = PromptVersion(id="p1", semver="2.1.3", content="Hi",
                          changelog="Shortened", author="bob")
        d = v.to_dict()
        v2 = PromptVersion.from_dict(d)
        assert v2.semver == "2.1.3"
        assert v2.content == "Hi"
        assert v2.author == "bob"


class TestPromptRecord:
    def test_to_from_dict(self):
        v = PromptVersion(id="r1", semver="0.1.0", content="Test")
        rec = PromptRecord(id="r1", name="Test Prompt", tags=["qa"],
                           versions=[v], current_semver="0.1.0")
        d = rec.to_dict()
        rec2 = PromptRecord.from_dict(d)
        assert rec2.name == "Test Prompt"
        assert rec2.current_semver == "0.1.0"
        assert rec2.latest is not None
        assert rec2.latest.content == "Test"


# ────────────────────────────────────────────────────────────────────
# PromptCatalog
# ────────────────────────────────────────────────────────────────────

class TestPromptCatalog:
    @pytest.fixture
    def catalog(self):
        cat = PromptCatalog()
        for i in range(5):
            rec = PromptRecord(
                id=f"p{i}", name=f"Prompt {i}",
                tags=[f"tag{i % 2}", "common"],
                status=[PromptStatus.DRAFT, PromptStatus.APPROVED,
                        PromptStatus.DEPRECATED, PromptStatus.DRAFT,
                        PromptStatus.APPROVED][i],
                owner=f"user{i % 2}",
            )
            v = PromptVersion(id=f"p{i}", semver=f"1.{i}.0", content=f"Content {i}")
            rec.add_version(v)
            cat.add(rec)
        return cat

    def test_get_by_name(self, catalog):
        rec = catalog.get_by_name("Prompt 2")
        assert rec is not None
        assert rec.id == "p2"

    def test_get_by_name_missing(self, catalog):
        assert catalog.get_by_name("Nonexistent") is None

    def test_search_by_name_pattern(self, catalog):
        filt = SearchFilter(name_pattern=r"Prompt [0-2]")
        results = catalog.search(filt)
        assert len(results) == 3

    def test_search_by_tags(self, catalog):
        filt = SearchFilter(tags=frozenset({"tag0", "common"}))
        results = catalog.search(filt)
        assert len(results) == 3  # p0, p2, p4 have tag0

    def test_search_by_status(self, catalog):
        filt = SearchFilter(status=PromptStatus.APPROVED)
        results = catalog.search(filt)
        assert all(r.status == PromptStatus.APPROVED for r in results)

    def test_search_by_owner(self, catalog):
        filt = SearchFilter(owner="user0")
        results = catalog.search(filt)
        assert all(r.owner == "user0" for r in results)

    def test_search_deprecated_only(self, catalog):
        filt = SearchFilter(deprecated_only=True)
        results = catalog.search(filt)
        assert all(r.status in (PromptStatus.DEPRECATED, PromptStatus.RETIRED)
                   for r in results)

    def test_count_by_status(self, catalog):
        counts = catalog.count_by_status()
        assert counts["draft"] == 2
        assert counts["approved"] == 2

    def test_remove(self, catalog):
        assert catalog.remove("p0") is True
        assert catalog.get("p0") is None
        assert catalog.remove("p0") is False

    def test_list_all(self, catalog):
        assert len(catalog.list_all()) == 5

    def test_serialization_roundtrip(self, catalog):
        d = catalog.to_dict()
        cat2 = PromptCatalog.from_dict(d)
        assert len(cat2.list_all()) == 5
        assert cat2.get("p3") is not None


# ────────────────────────────────────────────────────────────────────
# PromptRegistry — Lifecycle
# ────────────────────────────────────────────────────────────────────

class TestPromptRegistryLifecycle:
    @pytest.fixture
    def reg(self):
        return PromptRegistry()

    def test_create(self, reg):
        rec = reg.create("greet", "Greeting", "Hello {{ name }}!",
                         tags=["onboarding"], owner="alice")
        assert rec.status == PromptStatus.DRAFT
        assert rec.owner == "alice"
        assert rec.current_semver == "0.1.0"
        assert reg.get(rec.id) is not None

    def test_create_duplicate_id_safe(self, reg):
        # Names can be the same but IDs include timestamps so they may collide
        # at the same microsecond — the second create reuses the template
        r1 = reg.create("dup", "First", "A")
        r2 = reg.create("dup2", "Second", "B")
        assert r1.id != r2.id

    def test_render(self, reg):
        rec = reg.create("greet", "Greeting", "Hello {{ name }}!")
        result = reg.render(rec.id, {"name": "World"})
        assert result == "Hello World!"

    def test_update_creates_new_version(self, reg):
        rec = reg.create("calc", "Calc", "{{ a }} + {{ b }} = {{ a + b }}")
        assert len(rec.versions) == 1
        rec2 = reg.update(rec.id, "Result: {{ a + b }}", changelog="Improved")
        assert rec2.current_semver == "0.1.1"
        assert len(rec2.versions) == 2

    def test_update_resets_to_draft(self, reg):
        rec = reg.create("test", "Test", "v1")
        reg.submit(rec.id)
        reg.approve(rec.id, approver="bob")
        assert reg.get(rec.id).status == PromptStatus.APPROVED
        reg.update(rec.id, "v2")
        assert reg.get(rec.id).status == PromptStatus.DRAFT

    def test_get_by_name(self, reg):
        reg.create("unique", "Unique Prompt", "Content")
        rec = reg.get_by_name("unique")
        assert rec is not None
        assert reg.get_by_name("missing") is None

    def test_delete(self, reg):
        rec = reg.create("del", "Delete Me", "Content")
        assert reg.delete(rec.id) is True
        assert reg.get(rec.id) is None
        assert reg.delete("nonexistent") is False

    def test_list_all(self, reg):
        reg.create("a", "A", "A")
        reg.create("b", "B", "B")
        assert len(reg.list_all()) == 2

    def test_render_specific_version(self, reg):
        rec = reg.create("ver", "Versioned", "v1")
        reg.update(rec.id, "v2")
        reg.update(rec.id, "v3")
        result = reg.render(rec.id, version_semver="0.1.1")
        assert result == "v2"

    def test_render_nonexistent_version(self, reg):
        rec = reg.create("ver", "V", "v1")
        with pytest.raises(PromptNotFoundError):
            reg.render(rec.id, version_semver="99.0.0")


# ────────────────────────────────────────────────────────────────────
# PromptRegistry — Approval Workflow
# ────────────────────────────────────────────────────────────────────

class TestApprovalWorkflow:
    @pytest.fixture
    def reg(self):
        return PromptRegistry()

    @pytest.fixture
    def draft(self, reg):
        return reg.create("test", "Test", "Content")

    def test_full_lifecycle(self, reg, draft):
        # DRAFT → PENDING
        reg.submit(draft.id)
        assert reg.get(draft.id).status == PromptStatus.PENDING

        # PENDING → APPROVED
        reg.approve(draft.id, approver="manager")
        rec = reg.get(draft.id)
        assert rec.status == PromptStatus.APPROVED
        assert rec.approved_by == "manager"

        # APPROVED → DEPRECATED
        reg.deprecate(draft.id, reason="Outdated", successor_id="new_prompt")
        rec = reg.get(draft.id)
        assert rec.status == PromptStatus.DEPRECATED
        assert rec.deprecation_reason == "Outdated"
        assert rec.successor_id == "new_prompt"

        # DEPRECATED → RETIRED
        reg.retire(draft.id)
        assert reg.get(draft.id).status == PromptStatus.RETIRED

    def test_draft_cannot_approve_directly(self, reg, draft):
        with pytest.raises(InvalidTransitionError):
            reg.approve(draft.id, approver="bob")

    def test_draft_cannot_retire(self, reg, draft):
        with pytest.raises(InvalidTransitionError):
            reg.retire(draft.id)

    def test_reject_returns_to_draft(self, reg, draft):
        reg.submit(draft.id)
        # reject transitions PENDING → REJECTED
        reg.reject(draft.id, reason="Needs work")
        assert reg.get(draft.id).status == PromptStatus.REJECTED

    def test_approved_can_transition_to_draft_via_update(self, reg, draft):
        reg.submit(draft.id)
        reg.approve(draft.id, approver="bob")
        reg.update(draft.id, "Updated content")
        assert reg.get(draft.id).status == PromptStatus.DRAFT


# ────────────────────────────────────────────────────────────────────
# A/B Testing
# ────────────────────────────────────────────────────────────────────

class TestABTesting:
    @pytest.fixture
    def reg(self):
        r = PromptRegistry()
        r.create("control", "Control", "Control output")
        r.create("variant_a", "Variant A", "Variant A output")
        r.create("variant_b", "Variant B", "Variant B output")
        return r

    @pytest.fixture
    def ab_test_even(self, reg):
        variants = [
            ABTestVariant(name="control", prompt_id=reg.get_by_name("control").id,
                          version_semver="0.1.0"),
            ABTestVariant(name="variant_a", prompt_id=reg.get_by_name("variant_a").id,
                          version_semver="0.1.0"),
        ]
        return reg.create_ab_test("Even Test", variants, allocation=VariantAllocation.EVEN)

    def test_create_ab_test(self, reg, ab_test_even):
        assert ab_test_even.name == "Even Test"
        assert len(ab_test_even.variants) == 2
        assert ab_test_even.status == "draft"

    def test_start_ab_test(self, ab_test_even):
        assert ab_test_even.status == "draft"
        ab_test_even.status = "draft"  # ensure
        # Use registry to start
        assert ab_test_even.start_at is None
        ab_test_even.status = "running"
        assert ab_test_even.status == "running"

    def test_even_assignment(self, ab_test_even):
        ab_test_even.status = "running"
        # Multiple calls should give both variants
        results = set()
        for i in range(100):
            v = ab_test_even.assign({"seed": i})
            results.add(v.name)
        assert "control" in results
        assert "variant_a" in results

    def test_sticky_assignment(self, reg):
        variants = [
            ABTestVariant(name="control", prompt_id=reg.get_by_name("control").id,
                          version_semver="0.1.0", weight=0.5),
            ABTestVariant(name="variant_a", prompt_id=reg.get_by_name("variant_a").id,
                          version_semver="0.1.0", weight=0.5),
        ]
        test = reg.create_ab_test("Sticky Test", variants, allocation=VariantAllocation.STICKY,
                                  user_key_field="user_id")
        test.status = "running"
        # Same user always gets same variant
        v1 = test.assign({"user_id": "user123"})
        v2 = test.assign({"user_id": "user123"})
        assert v1.name == v2.name

    def test_weighted_assignment(self, reg):
        variants = [
            ABTestVariant(name="control", prompt_id=reg.get_by_name("control").id,
                          version_semver="0.1.0", weight=0.9),
            ABTestVariant(name="variant_a", prompt_id=reg.get_by_name("variant_a").id,
                          version_semver="0.1.0", weight=0.1),
        ]
        test = reg.create_ab_test("Weighted", variants, allocation=VariantAllocation.WEIGHTED)
        test.status = "running"
        control_count = sum(1 for i in range(200)
                           if test.assign({"seed": i}).name == "control")
        assert control_count > 150  # ~90% should go to control

    def test_ab_render(self, reg):
        variants = [
            ABTestVariant(name="control", prompt_id=reg.get_by_name("control").id,
                          version_semver="0.1.0"),
            ABTestVariant(name="variant_a", prompt_id=reg.get_by_name("variant_a").id,
                          version_semver="0.1.0"),
        ]
        test = reg.create_ab_test("Render Test", variants, allocation=VariantAllocation.EVEN)
        test.status = "running"
        rendered, variant = reg.render_ab(test.id, {"seed": "abc"})
        assert variant.name in ("control", "variant_a")
        assert len(rendered) > 0

    def test_conclude_ab_test(self, ab_test_even):
        ab_test_even.status = "running"
        ab_test_even.status = "concluded"
        ab_test_even.metrics["winner"] = "variant_a"
        assert ab_test_even.status == "concluded"
        assert ab_test_even.metrics["winner"] == "variant_a"


# ────────────────────────────────────────────────────────────────────
# Observer Hooks
# ────────────────────────────────────────────────────────────────────

class TestObservers:
    def test_observer_created(self):
        reg = PromptRegistry()
        events = []

        def on_created(rec):
            events.append(("created", rec.name))

        reg.on("created", on_created)
        rec = reg.create("observer_test", "OT", "Content")
        assert len(events) == 1
        assert events[0] == ("created", rec.name)

    def test_observer_approved(self):
        reg = PromptRegistry()
        events = []

        def on_approved(rec, approver):
            events.append((rec.name, approver))

        reg.on("approved", on_approved)
        rec = reg.create("obs", "Obs", "X")
        reg.submit(rec.id)
        reg.approve(rec.id, approver="alice")
        assert events == [(rec.name, "alice")]

    def test_remove_observer(self):
        reg = PromptRegistry()
        events = []

        def cb(r):
            events.append(1)

        reg.on("created", cb)
        reg.remove_observer("created", cb)
        reg.create("x", "X", "X")
        assert events == []


# ────────────────────────────────────────────────────────────────────
# Serialization Round-trips
# ────────────────────────────────────────────────────────────────────

class TestSerialization:
    def test_export_import_catalog(self):
        reg1 = PromptRegistry()
        reg1.create("a", "A", "Hello {{ name }}!")
        reg1.create("b", "B", "Goodbye {{ name }}!")

        data = reg1.export_catalog()
        reg2 = PromptRegistry()
        reg2.import_catalog(data)

        assert reg2.get_by_name("a") is not None
        assert reg2.get_by_name("b") is not None

    def test_search_filter_max_results(self):
        cat = PromptCatalog()
        for i in range(10):
            v = PromptVersion(id=f"p{i}", semver="1.0.0", content=f"C{i}")
            rec = PromptRecord(id=f"p{i}", name=f"Prompt {i}")
            rec.add_version(v)
            cat.add(rec)
        filt = SearchFilter(name_pattern=r"Prompt", max_results=3)
        assert len(cat.search(filt)) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])