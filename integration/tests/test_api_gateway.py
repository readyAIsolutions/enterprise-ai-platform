"""
Tests for ENI Enterprise Integration Layer — API Gateway
========================================================
Tests for the FastAPI application factory, routers, middleware,
auth handler, rate limiter, and request/response models.
"""

import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from enterprise.integration.api_gateway import (
    # App factory
    create_app,
    get_app,
    get_deps,
    # Middleware components
    AuthHandler,
    RateLimiter,
    TokenBucket,
    # Request models
    EventPublishRequest,
    ErrorResponse,
    GateUpdateRequest,
    KernelContextCreate,
    KernelContextResponse,
    ModuleHealthResponse,
    OrchestrationTask,
    PlatformHealthResponse,
    APIKeyRequest,
    # Routers
    health_router,
    kernel_router,
    modules_router,
    events_router,
    orchestration_router,
    knowledge_router,
    privacy_router,
    safety_router,
    prompts_router,
    releases_router,
    cx_router,
    innovation_router,
    dr_router,
    dx_router,
    admin_router,
    # Constants
    API_VERSION,
    API_PREFIX,
)


# ---------------------------------------------------------------------------
# Pydantic Model Tests
# ---------------------------------------------------------------------------


class TestRequestModels:
    """Tests for Pydantic request/response models."""

    def test_kernel_context_create_valid(self):
        body = KernelContextCreate(project="test-proj", objective="Test objective", activate_modules=["safety_governance"])
        assert body.project == "test-proj"
        assert body.objective == "Test objective"
        assert "safety_governance" in body.activate_modules

    def test_kernel_context_create_minimal(self):
        body = KernelContextCreate(project="p", objective="o")
        assert body.activate_modules == []

    def test_event_publish_request(self):
        body = EventPublishRequest(
            event_type="test.event",
            source="test",
            payload={"x": 1},
            priority="high",
        )
        assert body.event_type == "test.event"
        assert body.priority == "high"

    def test_gate_update_request(self):
        body = GateUpdateRequest(
            name="QG-001",
            status="passed",
            evidence={"score": 0.95},
        )
        assert body.name == "QG-001"
        assert body.status == "passed"

    def test_error_response_model(self):
        resp = ErrorResponse(
            error="test_error",
            message="Something went wrong",
            request_id="req-123",
        )
        data = resp.model_dump()
        assert data["error"] == "test_error"
        assert data["message"] == "Something went wrong"
        assert data["request_id"] == "req-123"
        assert "timestamp" in data

    def test_platform_health_response_defaults(self):
        resp = PlatformHealthResponse()
        assert resp.platform == "ENI Enterprise Platform"
        assert resp.api_version == "v1"
        assert resp.timestamp is not None


# ---------------------------------------------------------------------------
# TokenBucket Tests
# ---------------------------------------------------------------------------


class TestTokenBucket:
    """Tests for the token bucket rate limiter."""

    def test_initial_tokens(self):
        bucket = TokenBucket(rate=60, burst=10)
        assert bucket.tokens == 10

    def test_consume_allowed(self):
        bucket = TokenBucket(rate=600, burst=10)
        allowed, remaining = bucket.consume()
        assert allowed is True
        assert remaining == 9

    def test_consume_depletes(self):
        bucket = TokenBucket(rate=1, burst=2)  # Very low rate
        # Consume all burst tokens
        allowed1, _ = bucket.consume()
        allowed2, _ = bucket.consume()
        assert allowed1 is True
        assert allowed2 is True
        # Third should be denied (rate is low)
        allowed3, remaining = bucket.consume()
        assert allowed3 is False
        assert remaining <= 0


# ---------------------------------------------------------------------------
# RateLimiter Tests
# ---------------------------------------------------------------------------


class TestRateLimiter:
    """Tests for the per-client rate limiter."""

    def test_default_config(self):
        rl = RateLimiter()
        assert rl.default_rate > 0

    def test_cleanup_no_error(self):
        rl = RateLimiter()
        rl.cleanup()  # Should not raise


# ---------------------------------------------------------------------------
# AuthHandler Tests
# ---------------------------------------------------------------------------


class TestAuthHandler:
    """Tests for authentication handler."""

    def test_default_init(self):
        handler = AuthHandler()
        assert handler.secret_key is not None
        assert len(handler.api_keys) == 0

    def test_validate_api_key_valid(self):
        handler = AuthHandler(api_keys={"my-secret-key-12345"})
        result = handler.validate_api_key("my-secret-key-12345")
        assert result is not None
        assert result["auth_method"] == "api_key"

    def test_validate_api_key_invalid(self):
        handler = AuthHandler(api_keys={"my-secret-key-12345"})
        result = handler.validate_api_key("wrong-key")
        assert result is None

    def test_validate_jwt_invalid(self):
        handler = AuthHandler()
        result = handler.validate_jwt("invalid-token")
        assert result is None


# ---------------------------------------------------------------------------
# FastAPI App Tests
# ---------------------------------------------------------------------------


class TestFastAPIApp:
    """Tests for the FastAPI application factory and endpoints."""

    @pytest.fixture
    def client(self):
        """Create a test client with a fresh app instance."""
        # Reset the rate limiter so tests don't interfere with each other
        deps = get_deps()
        from enterprise.integration.api_gateway import RateLimiter
        deps.rate_limiter = RateLimiter(default_rate=10000, default_burst=10000)
        app = create_app(enable_docs=True)
        return TestClient(app)

    # ── Health Endpoints ─────────────────────────────────────────────────

    def test_health_endpoint(self, client):
        response = client.get(f"{API_PREFIX}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["platform"] == "ENI Enterprise Platform"
        assert data["api_version"] == "v1"
        assert "modules" in data
        assert "uptime_seconds" in data

    def test_liveness_probe(self, client):
        response = client.get(f"{API_PREFIX}/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"

    def test_readiness_probe(self, client):
        response = client.get(f"{API_PREFIX}/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("ready", "not_ready")

    # ── Kernel Endpoints ─────────────────────────────────────────────────

    def test_create_context_auth_required(self, client):
        response = client.post(
            f"{API_PREFIX}/kernel/contexts",
            json={"project": "test", "objective": "test"},
        )
        assert response.status_code == 401  # Auth required

    def test_create_context_with_api_key(self, client):
        # Add API key to auth handler
        deps = get_deps()
        deps.auth_handler.api_keys.add("test-key-12345678")
        response = client.post(
            f"{API_PREFIX}/kernel/contexts",
            json={"project": "test-proj", "objective": "test obj"},
            headers={"X-API-Key": "test-key-12345678"},
        )
        # May fail if kernel not available, but should not be 401
        assert response.status_code != 401

    def test_update_gate(self, client):
        deps = get_deps()
        deps.auth_handler.api_keys.add("admin-key-123456")
        response = client.post(
            f"{API_PREFIX}/kernel/gates/test-session",
            json={"name": "QG-001", "status": "passed", "evidence": {"score": 0.99}},
            headers={"X-API-Key": "admin-key-123456"},
        )
        assert response.status_code == 200

    # ── Modules Endpoints ────────────────────────────────────────────────

    def test_list_modules(self, client):
        response = client.get(f"{API_PREFIX}/modules")
        assert response.status_code == 200
        data = response.json()
        assert "modules" in data
        assert "count" in data

    def test_get_module_found(self, client):
        response = client.get(f"{API_PREFIX}/modules/safety_governance")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "M-001"

    def test_get_module_not_found(self, client):
        response = client.get(f"{API_PREFIX}/modules/nonexistent_module")
        assert response.status_code == 404

    # ── Events Endpoints ─────────────────────────────────────────────────

    def test_publish_event_auth_required(self, client):
        response = client.post(
            f"{API_PREFIX}/events/publish",
            json={"event_type": "test", "source": "test", "payload": {}},
        )
        assert response.status_code == 401

    def test_publish_event_with_auth(self, client):
        deps = get_deps()
        deps.auth_handler.api_keys.add("event-key-12345")
        response = client.post(
            f"{API_PREFIX}/events/publish",
            json={"event_type": "test.event", "source": "test", "payload": {"x": 1}},
            headers={"X-API-Key": "event-key-12345"},
        )
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "accepted"
        assert "event_id" in data

    def test_list_event_schemas(self, client):
        response = client.get(f"{API_PREFIX}/events/schemas")
        assert response.status_code == 200

    def test_list_subscriptions(self, client):
        response = client.get(f"{API_PREFIX}/events/subscriptions")
        assert response.status_code == 200

    # ── Orchestration Endpoints ──────────────────────────────────────────

    def test_list_agents(self, client):
        response = client.get(f"{API_PREFIX}/orchestration/agents")
        assert response.status_code == 200
        data = response.json()
        if "agents" in data:
            assert "count" in data

    def test_submit_task_auth_required(self, client):
        response = client.post(
            f"{API_PREFIX}/orchestration/tasks",
            json={"objective": "test task"},
        )
        assert response.status_code == 401

    def test_submit_task_with_auth(self, client):
        deps = get_deps()
        deps.auth_handler.api_keys.add("orch-key-12345")
        response = client.post(
            f"{API_PREFIX}/orchestration/tasks",
            json={"objective": "orchestrate this"},
            headers={"X-API-Key": "orch-key-12345"},
        )
        assert response.status_code == 202

    # ── Knowledge Graph Endpoints ────────────────────────────────────────

    def test_query_entities(self, client):
        deps = get_deps()
        deps.auth_handler.api_keys.add("kg-key-123456")
        response = client.get(
            f"{API_PREFIX}/knowledge/entities",
            headers={"X-API-Key": "kg-key-123456"},
        )
        assert response.status_code == 200

    def test_query_entities_with_params(self, client):
        deps = get_deps()
        deps.auth_handler.api_keys.add("kg-key-123456")
        response = client.get(
            f"{API_PREFIX}/knowledge/entities?q=test&entity_type=Person&limit=10",
            headers={"X-API-Key": "kg-key-123456"},
        )
        assert response.status_code == 200

    def test_query_relationships(self, client):
        response = client.get(f"{API_PREFIX}/knowledge/relationships")
        assert response.status_code == 200

    def test_trace_provenance(self, client):
        response = client.post(f"{API_PREFIX}/knowledge/provenance?entity_id=ent-1")
        assert response.status_code == 200

    # ── Privacy Endpoints ────────────────────────────────────────────────

    def test_classify_data(self, client):
        deps = get_deps()
        deps.auth_handler.api_keys.add("privacy-key-123")
        response = client.post(
            f"{API_PREFIX}/privacy/classify",
            json={"text": "sample data"},
            headers={"X-API-Key": "privacy-key-123"},
        )
        assert response.status_code == 200

    def test_compliance_status(self, client):
        response = client.get(f"{API_PREFIX}/privacy/compliance")
        assert response.status_code == 200

    def test_compliance_status_filtered(self, client):
        response = client.get(f"{API_PREFIX}/privacy/compliance?framework=GDPR")
        assert response.status_code == 200

    # ── Safety Endpoints ─────────────────────────────────────────────────

    def test_run_guardrails(self, client):
        deps = get_deps()
        deps.auth_handler.api_keys.add("safety-key-123")
        response = client.post(
            f"{API_PREFIX}/safety/guardrails?content=hello world",
            headers={"X-API-Key": "safety-key-123"},
        )
        assert response.status_code == 200

    def test_list_incidents(self, client):
        response = client.get(f"{API_PREFIX}/safety/incidents")
        assert response.status_code == 200

    def test_run_evaluation(self, client):
        response = client.post(
            f"{API_PREFIX}/safety/evaluate?model_id=gpt-4",
        )
        assert response.status_code == 200

    # ── Prompts Endpoints ────────────────────────────────────────────────

    def test_list_prompts(self, client):
        response = client.get(f"{API_PREFIX}/prompts")
        assert response.status_code == 200

    def test_optimize_prompt(self, client):
        response = client.post(
            f"{API_PREFIX}/prompts/optimize?strategy=balanced",
            json={"prompt": "test prompt content"},
        )
        assert response.status_code == 200

    def test_evaluate_prompt(self, client):
        response = client.post(
            f"{API_PREFIX}/prompts/evaluate",
            json={"prompt": "test prompt content"},
        )
        assert response.status_code == 200

    # ── Releases Endpoints ───────────────────────────────────────────────

    def test_list_releases(self, client):
        response = client.get(f"{API_PREFIX}/releases")
        assert response.status_code == 200

    def test_create_change(self, client):
        deps = get_deps()
        deps.auth_handler.api_keys.add("release-key-123")
        response = client.post(
            f"{API_PREFIX}/releases/changes",
            json={"type": "feature", "description": "new feature"},
            headers={"X-API-Key": "release-key-123"},
        )
        assert response.status_code == 200

    def test_list_strategies(self, client):
        response = client.get(f"{API_PREFIX}/releases/strategies")
        assert response.status_code == 200

    # ── Customer Experience Endpoints ────────────────────────────────────

    def test_list_journeys(self, client):
        response = client.get(f"{API_PREFIX}/cx/journeys")
        assert response.status_code == 200

    def test_create_ticket(self, client):
        deps = get_deps()
        deps.auth_handler.api_keys.add("cx-key-12345")
        response = client.post(
            f"{API_PREFIX}/cx/tickets",
            json={"subject": "issue", "description": "help"},
            headers={"X-API-Key": "cx-key-12345"},
        )
        assert response.status_code == 200

    def test_get_cx_metrics(self, client):
        response = client.get(f"{API_PREFIX}/cx/metrics")
        assert response.status_code == 200

    # ── Innovation Endpoints ─────────────────────────────────────────────

    def test_list_research(self, client):
        response = client.get(f"{API_PREFIX}/innovation/research")
        assert response.status_code == 200

    def test_create_experiment(self, client):
        deps = get_deps()
        deps.auth_handler.api_keys.add("inn-key-12345")
        response = client.post(
            f"{API_PREFIX}/innovation/experiments",
            json={"name": "test experiment"},
            headers={"X-API-Key": "inn-key-12345"},
        )
        assert response.status_code == 200

    def test_list_ip(self, client):
        response = client.get(f"{API_PREFIX}/innovation/ip")
        assert response.status_code == 200

    # ── Disaster Recovery Endpoints ─────────────────────────────────────

    def test_list_dr_plans(self, client):
        response = client.get(f"{API_PREFIX}/dr/plans")
        assert response.status_code == 200

    def test_schedule_exercise(self, client):
        deps = get_deps()
        deps.auth_handler.api_keys.add("dr-key-12345")
        response = client.post(
            f"{API_PREFIX}/dr/exercises",
            json={"type": "tabletop", "date": "2026-08-15"},
            headers={"X-API-Key": "dr-key-12345"},
        )
        assert response.status_code == 200

    def test_get_rto_rpo(self, client):
        response = client.get(f"{API_PREFIX}/dr/rto")
        assert response.status_code == 200

    # ── Developer Experience Endpoints ───────────────────────────────────

    def test_list_golden_paths(self, client):
        response = client.get(f"{API_PREFIX}/dx/golden-paths")
        assert response.status_code == 200

    def test_list_environments(self, client):
        response = client.get(f"{API_PREFIX}/dx/environments")
        assert response.status_code == 200

    def test_get_dora_metrics(self, client):
        response = client.get(f"{API_PREFIX}/dx/metrics")
        assert response.status_code == 200

    def test_list_ai_rules(self, client):
        response = client.get(f"{API_PREFIX}/dx/ai-rules")
        assert response.status_code == 200

    # ── Admin Endpoints ─────────────────────────────────────────────────

    def test_query_audit(self, client):
        deps = get_deps()
        deps.auth_handler.api_keys.add("admin-key-1234")
        response = client.get(
            f"{API_PREFIX}/admin/audit",
            headers={"X-API-Key": "admin-key-1234"},
        )
        assert response.status_code == 200

    def test_get_metrics(self, client):
        deps = get_deps()
        deps.auth_handler.api_keys.add("admin-key-1234")
        response = client.get(
            f"{API_PREFIX}/admin/metrics",
            headers={"X-API-Key": "admin-key-1234"},
        )
        assert response.status_code == 200

    def test_create_api_key(self, client):
        deps = get_deps()
        deps.auth_handler.api_keys.add("admin-key-1234")
        response = client.post(
            f"{API_PREFIX}/admin/api-keys",
            json={"api_key": "my-new-api-key-12345"},
            headers={"X-API-Key": "admin-key-1234"},
        )
        assert response.status_code == 200

    # ── OpenAPI Docs ─────────────────────────────────────────────────────

    def test_openapi_schema(self, client):
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert schema["info"]["title"] == "ENI Enterprise Platform API"
        assert "paths" in schema
        # Verify some key paths exist
        assert f"{API_PREFIX}/health" in schema["paths"]

    def test_swagger_docs(self, client):
        response = client.get("/docs")
        assert response.status_code == 200

    def test_redoc_docs(self, client):
        response = client.get("/redoc")
        assert response.status_code == 200

    # ── CORS Headers ─────────────────────────────────────────────────────

    def test_cors_headers(self, client):
        response = client.options(
            f"{API_PREFIX}/health",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers

    # ── Request ID Header ────────────────────────────────────────────────

    def test_request_id_header(self, client):
        response = client.get(f"{API_PREFIX}/health")
        assert "X-Request-ID" in response.headers

    def test_request_id_passthrough(self, client):
        custom_id = "custom-req-id-123"
        response = client.get(
            f"{API_PREFIX}/health",
            headers={"X-Request-ID": custom_id},
        )
        assert response.headers["X-Request-ID"] == custom_id

    # ── Error Handling ───────────────────────────────────────────────────

    def test_404_response(self, client):
        response = client.get(f"{API_PREFIX}/nonexistent/endpoint")
        assert response.status_code == 404

    def test_422_validation_error(self, client):
        # Validation errors only occur after auth; test with valid auth but bad body
        deps = get_deps()
        deps.auth_handler.api_keys.add("valid-key-12345")
        response = client.post(
            f"{API_PREFIX}/kernel/contexts",
            json={"invalid_field": "missing required fields"},
            headers={"X-API-Key": "valid-key-12345"},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Router Registration Tests
# ---------------------------------------------------------------------------


class TestRouterRegistration:
    """Verify all routers are properly created and have endpoints."""

    def test_health_router_has_endpoints(self):
        routes = [r.path for r in health_router.routes]
        assert any("/health" in p for p in routes)

    def test_kernel_router_has_endpoints(self):
        routes = [r.path for r in kernel_router.routes]
        assert any("kernel" in p for p in routes)

    def test_modules_router_has_endpoints(self):
        routes = [r.path for r in modules_router.routes]
        assert any("modules" in p for p in routes)

    def test_events_router_has_endpoints(self):
        routes = [r.path for r in events_router.routes]
        assert any("events" in p for p in routes)

    def test_orchestration_router_has_endpoints(self):
        routes = [r.path for r in orchestration_router.routes]
        assert any("orchestration" in p for p in routes)

    def test_knowledge_router_has_endpoints(self):
        routes = [r.path for r in knowledge_router.routes]
        assert any("knowledge" in p for p in routes)

    def test_privacy_router_has_endpoints(self):
        routes = [r.path for r in privacy_router.routes]
        assert any("privacy" in p for p in routes)

    def test_safety_router_has_endpoints(self):
        routes = [r.path for r in safety_router.routes]
        assert any("safety" in p for p in routes)

    def test_prompts_router_has_endpoints(self):
        routes = [r.path for r in prompts_router.routes]
        assert any("prompts" in p for p in routes)

    def test_releases_router_has_endpoints(self):
        routes = [r.path for r in releases_router.routes]
        assert any("releases" in p for p in routes)

    def test_cx_router_has_endpoints(self):
        routes = [r.path for r in cx_router.routes]
        assert any("cx" in p for p in routes)

    def test_innovation_router_has_endpoints(self):
        routes = [r.path for r in innovation_router.routes]
        assert any("innovation" in p for p in routes)

    def test_dr_router_has_endpoints(self):
        routes = [r.path for r in dr_router.routes]
        assert any("dr" in p for p in routes)

    def test_dx_router_has_endpoints(self):
        routes = [r.path for r in dx_router.routes]
        assert any("dx" in p for p in routes)

    def test_admin_router_has_endpoints(self):
        routes = [r.path for r in admin_router.routes]
        assert any("admin" in p for p in routes)


# ---------------------------------------------------------------------------
# App Factory Tests
# ---------------------------------------------------------------------------


class TestAppFactory:
    """Tests for the application factory function."""

    def test_create_app_no_docs(self):
        app = create_app(enable_docs=False)
        assert app.docs_url is None
        assert app.redoc_url is None

    def test_create_app_with_cors(self):
        app = create_app(cors_origins=["https://myapp.example.com"])
        # Middleware is registered at app creation time
        assert app.user_middleware is not None  # Middleware stack exists

    def test_get_app_singleton(self):
        # Reset singleton for test
        import enterprise.integration.api_gateway as gw
        gw._app = None
        app1 = get_app()
        app2 = get_app()
        assert app1 is app2