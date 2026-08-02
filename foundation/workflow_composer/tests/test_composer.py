"""
Unit tests for WorkflowComposer.
"""

import pytest
import sys
import os

# Ensure the package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from composer import (
    WorkflowComposer,
    Module,
    ModuleCapability,
    ModuleConstraint,
    Stage,
    ComposedPipeline,
    CapabilityRequirement,
    ExecutionMode,
)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def summarizer_module():
    return Module(
        name="summarizer",
        capabilities=[
            ModuleCapability("text_summarization", confidence=0.95, tags={"nlp", "text"}),
        ],
        input_schema={"text": "str", "max_length": "int"},
        output_schema={"summary": "str"},
        estimated_tokens=500,
        dependencies=[],
    )


@pytest.fixture
def entity_extractor_module():
    return Module(
        name="entity_extractor",
        capabilities=[
            ModuleCapability("entity_extraction", confidence=0.90, tags={"nlp", "ner"}),
        ],
        input_schema={"text": "str"},
        output_schema={"entities": "list"},
        estimated_tokens=800,
        dependencies=[],
    )


@pytest.fixture
def code_generator_module():
    return Module(
        name="code_generator",
        capabilities=[
            ModuleCapability("code_generation", confidence=0.88, tags={"code"}),
        ],
        input_schema={"spec": "str", "language": "str"},
        output_schema={"code": "str"},
        estimated_tokens=1200,
        dependencies=[],
    )


@pytest.fixture
def classifier_module():
    return Module(
        name="classifier",
        capabilities=[
            ModuleCapability("text_classification", confidence=0.92, tags={"nlp"}),
            ModuleCapability("sentiment_analysis", confidence=0.85, tags={"nlp"}),
        ],
        input_schema={"text": "str", "labels": "list"},
        output_schema={"label": "str", "confidence": "float"},
        estimated_tokens=400,
        dependencies=[],
    )


@pytest.fixture
def validator_module():
    return Module(
        name="validator",
        capabilities=[
            ModuleCapability("validation", confidence=0.93, tags={"quality"}),
        ],
        input_schema={"data": "any", "rules": "list"},
        output_schema={"valid": "bool", "errors": "list"},
        estimated_tokens=300,
        constraints=[
            ModuleConstraint("requires_module", "summarizer", severity="hard"),
        ],
        dependencies=["summarizer"],
    )


@pytest.fixture
def composer(summarizer_module, entity_extractor_module, code_generator_module, classifier_module, validator_module):
    comp = WorkflowComposer()
    for mod in [summarizer_module, entity_extractor_module, code_generator_module, classifier_module, validator_module]:
        comp.register_module(mod)
    return comp


# ------------------------------------------------------------------
# Module Registry Tests
# ------------------------------------------------------------------

class TestModuleRegistry:
    """Tests for module registration and retrieval."""

    def test_register_module(self, composer, summarizer_module):
        assert "summarizer" in composer.modules
        assert composer.modules["summarizer"] is summarizer_module

    def test_register_duplicate_raises(self, composer, summarizer_module):
        with pytest.raises(ValueError, match="already registered"):
            composer.register_module(summarizer_module)

    def test_unregister_module(self, composer):
        composer.unregister_module("summarizer")
        assert "summarizer" not in composer.modules

    def test_unregister_missing_raises(self, composer):
        with pytest.raises(KeyError, match="not found"):
            composer.unregister_module("nonexistent")

    def test_get_module(self, composer):
        mod = composer.get_module("code_generator")
        assert mod.name == "code_generator"
        assert mod.estimated_tokens == 1200

    def test_get_module_missing_raises(self, composer):
        with pytest.raises(KeyError, match="not found"):
            composer.get_module("nonexistent")


# ------------------------------------------------------------------
# Capability Extraction Tests
# ------------------------------------------------------------------

class TestExtractRequirements:
    """Tests for requirement extraction from task descriptions."""

    def test_extract_summarization(self, composer):
        reqs = composer.extract_requirements("Please summarize this article")
        capabilities = [r.capability for r in reqs]
        assert "text_summarization" in capabilities

    def test_extract_entity_extraction(self, composer):
        reqs = composer.extract_requirements("Extract entities from the document")
        capabilities = [r.capability for r in reqs]
        assert "entity_extraction" in capabilities

    def test_extract_code_generation(self, composer):
        reqs = composer.extract_requirements("Write code to sort a list")
        capabilities = [r.capability for r in reqs]
        assert "code_generation" in capabilities

    def test_extract_classification(self, composer):
        reqs = composer.extract_requirements("Classify these documents by topic")
        capabilities = [r.capability for r in reqs]
        assert "text_classification" in capabilities

    def test_extract_multiple_requirements(self, composer):
        reqs = composer.extract_requirements(
            "Summarize the text, then extract entities, and classify the result"
        )
        capabilities = [r.capability for r in reqs]
        assert len(capabilities) >= 2
        assert "text_summarization" in capabilities

    def test_extract_no_match_returns_empty(self, composer):
        reqs = composer.extract_requirements("xyzzy foobar blarg")
        assert reqs == []


# ------------------------------------------------------------------
# Capability Matching Tests
# ------------------------------------------------------------------

class TestCapabilityMatching:
    """Tests for capability-to-module matching."""

    def test_find_modules_for_capability(self, composer):
        matches = composer.find_modules_for_capability("text_summarization")
        assert len(matches) == 1
        assert matches[0][0].name == "summarizer"

    def test_find_modules_min_confidence(self, composer):
        matches = composer.find_modules_for_capability("text_summarization", min_confidence=0.99)
        assert len(matches) == 0

    def test_find_modules_nonexistent_capability(self, composer):
        matches = composer.find_modules_for_capability("nonexistent_capability")
        assert matches == []

    def test_match_capabilities(self, composer):
        reqs = [
            CapabilityRequirement("text_summarization"),
            CapabilityRequirement("entity_extraction"),
        ]
        result = composer.match_capabilities(reqs)
        assert "text_summarization" in result
        assert "entity_extraction" in result

    def test_find_modules_by_tag(self, composer):
        mods = composer.find_modules_by_tag({"code"})
        assert len(mods) == 1
        assert mods[0].name == "code_generator"

    def test_find_modules_by_tag_multiple(self, composer):
        mods = composer.find_modules_by_tag({"nlp"})
        assert len(mods) >= 2  # summarizer, entity_extractor, classifier


# ------------------------------------------------------------------
# Constraint Tests
# ------------------------------------------------------------------

class TestConstraints:
    """Tests for constraint satisfaction."""

    def test_constraint_requires_module_satisfied(self, composer):
        ok, violations = composer._check_module_constraints(
            composer.get_module("validator"),
            selected_modules={"summarizer"},
        )
        assert ok is True
        assert violations == []

    def test_constraint_requires_module_unsatisfied(self, composer):
        ok, violations = composer._check_module_constraints(
            composer.get_module("validator"),
            selected_modules=set(),
        )
        assert ok is False
        assert len(violations) > 0

    def test_module_has_capability(self, composer):
        mod = composer.get_module("classifier")
        assert mod.has_capability("text_classification") is True
        assert mod.has_capability("code_generation") is False

    def test_module_capability_confidence(self, composer):
        mod = composer.get_module("summarizer")
        assert mod.capability_confidence("text_summarization") == 0.95
        assert mod.capability_confidence("unknown") == 0.0


# ------------------------------------------------------------------
# Pipeline Composition Tests
# ------------------------------------------------------------------

class TestCompose:
    """Tests for pipeline composition."""

    def test_compose_single_module(self, composer):
        pipeline = composer.compose("Summarize this text")
        assert len(pipeline.stages) == 1
        assert pipeline.stages[0].module_name == "summarizer"

    def test_compose_multiple_modules(self, composer):
        pipeline = composer.compose(
            "Summarize the text, extract entities, and classify the result"
        )
        assert len(pipeline.stages) >= 2

    def test_compose_respects_preferred_modules(self, composer):
        pipeline = composer.compose(
            "Summarize text",
            preferred_modules=["summarizer"],
        )
        assert pipeline.stages[0].module_name == "summarizer"

    def test_compose_respects_max_modules(self, composer):
        pipeline = composer.compose(
            "Summarize, extract entities, classify, and validate",
            max_modules=2,
        )
        assert len(pipeline.stages) <= 2

    def test_compose_populates_metadata(self, composer):
        pipeline = composer.compose("Summarize text")
        assert "task_description" in pipeline.metadata
        assert "requirements" in pipeline.metadata
        assert "rationale" in pipeline.metadata

    def test_compose_no_requirements_raises(self, composer):
        with pytest.raises(ValueError, match="No capability requirements"):
            composer.compose("xyzzy blarg")

    def test_compose_no_module_for_capability(self, composer):
        # Register a composer with no modules that can handle a known keyword
        empty = WorkflowComposer()
        with pytest.raises(ValueError, match="No module found"):
            empty.compose("summarize this")

    def test_compose_produces_outputs(self, composer):
        pipeline = composer.compose("Summarize text")
        assert len(pipeline.produced_outputs) > 0

    def test_compose_tracks_required_inputs(self, composer):
        pipeline = composer.compose("Summarize text")
        assert "text" in pipeline.required_inputs or len(pipeline.required_inputs) >= 1


# ------------------------------------------------------------------
# Dependency Resolution Tests
# ------------------------------------------------------------------

class TestDependencyResolution:
    """Tests for topological sorting / dependency resolution."""

    def test_resolve_dependency_order_simple(self, composer):
        ordered = composer._resolve_dependency_order(
            ["summarizer", "validator"]
        )
        # validator depends on summarizer, so summarizer must come first
        assert ordered.index("summarizer") < ordered.index("validator")

    def test_resolve_dependency_order_no_deps(self, composer):
        ordered = composer._resolve_dependency_order(
            ["summarizer", "classifier"]
        )
        assert len(ordered) == 2

    def test_resolve_circular_dependency_raises(self, composer):
        # Create a cycle
        mod_a = Module(name="A", dependencies=["B"], capabilities=[ModuleCapability("test")])
        mod_b = Module(name="B", dependencies=["A"], capabilities=[ModuleCapability("test")])
        comp = WorkflowComposer([mod_a, mod_b])
        with pytest.raises(ValueError, match="Circular dependency"):
            comp._resolve_dependency_order(["A", "B"])


# ------------------------------------------------------------------
# Edge Cases
# ------------------------------------------------------------------

class TestEdgeCases:
    """Edge case tests."""

    def test_empty_composer(self):
        comp = WorkflowComposer()
        assert len(comp.modules) == 0

    def test_module_with_zero_confidence(self):
        mod = Module(
            name="weak_mod",
            capabilities=[ModuleCapability("test", confidence=0.0)],
        )
        comp = WorkflowComposer([mod])
        matches = comp.find_modules_for_capability("test", min_confidence=0.0)
        assert len(matches) == 1

    def test_suggest_alternatives(self, composer):
        alts = composer.suggest_alternatives("summarizer", "text_summarization")
        assert len(alts) == 0  # No other module has this capability

    def test_suggest_alternatives_with_duplicate_caps(self, composer):
        # Add a second summarizer
        mod2 = Module(
            name="summarizer_v2",
            capabilities=[ModuleCapability("text_summarization", confidence=0.80)],
            input_schema={"text": "str"},
            output_schema={"summary": "str"},
            estimated_tokens=300,
        )
        composer.register_module(mod2)
        alts = composer.suggest_alternatives("summarizer", "text_summarization")
        assert len(alts) == 1
        assert alts[0].name == "summarizer_v2"


# ------------------------------------------------------------------
# ModuleCapability Tests
# ------------------------------------------------------------------

class TestModuleCapability:
    """Tests for the ModuleCapability dataclass."""

    def test_valid_confidence(self):
        cap = ModuleCapability("test", confidence=0.5)
        assert cap.confidence == 0.5

    def test_confidence_zero(self):
        cap = ModuleCapability("test", confidence=0.0)
        assert cap.confidence == 0.0

    def test_confidence_one(self):
        cap = ModuleCapability("test", confidence=1.0)
        assert cap.confidence == 1.0

    def test_confidence_below_zero(self):
        with pytest.raises(ValueError, match="Confidence must be"):
            ModuleCapability("test", confidence=-0.1)

    def test_confidence_above_one(self):
        with pytest.raises(ValueError, match="Confidence must be"):
            ModuleCapability("test", confidence=1.1)


# ------------------------------------------------------------------
# Module Tests
# ------------------------------------------------------------------

class TestModule:
    """Tests for the Module dataclass."""

    def test_matches_tags(self):
        mod = Module(
            name="test",
            capabilities=[ModuleCapability("cap1", tags={"nlp", "text"})],
        )
        assert mod.matches_tags({"nlp"}) is True
        assert mod.matches_tags({"code"}) is False

    def test_defaults(self):
        mod = Module(name="test")
        assert mod.capabilities == []
        assert mod.input_schema == {}
        assert mod.output_schema == {}
        assert mod.estimated_tokens == 0
        assert mod.dependencies == []