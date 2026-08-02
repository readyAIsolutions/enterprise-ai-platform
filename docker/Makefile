# =============================================================================
# ENI Enterprise Platform — Docker Makefile
# Build, run, test, and deploy the full containerized platform
# =============================================================================

SHELL := /bin/bash
.DEFAULT_GOAL := help

# ── Project context ─────────────────────────────────────────────────────────
PROJECT_NAME ?= eni-enterprise
DOCKER_IMAGE ?= eni-enterprise:latest
DOCKER_DEV_IMG ?= eni-enterprise:dev
REGISTRY     ?= ghcr.io/nous-research
COMPOSE_FILE := docker/docker-compose.yml
COMPOSE_DEV  := docker/docker-compose.dev.yml
CONTEXT      := .
DOCKER       := docker
COMPOSE      := docker compose
DOCKER_DIR   := docker

# ── Colors ───────────────────────────────────────────────────────────────────
GREEN  := \033[0;32m
YELLOW := \033[0;33m
RED    := \033[0;31m
BLUE   := \033[0;34m
CYAN   := \033[0;36m
NC     := \033[0m

# ── Default Help ─────────────────────────────────────────────────────────────
.PHONY: help
help: ## Print this help message
	@echo "$(CYAN)ENI Enterprise Platform — Docker Commands$(NC)"
	@echo "$(CYAN)==========================================$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-26s$(NC) %s\n", $$1, $$2}'

# =============================================================================
# BUILD TARGETS
# =============================================================================

.PHONY: build
build: ## Build production Docker image (multi-stage)
	@echo "$(YELLOW)Building production image: $(DOCKER_IMAGE)...$(NC)"
	$(DOCKER) build \
		-t $(DOCKER_IMAGE) \
		-f $(DOCKER_DIR)/Dockerfile \
		$(CONTEXT)
	@echo "$(GREEN)Production image built: $(DOCKER_IMAGE)$(NC)"

.PHONY: build-no-cache
build-no-cache: ## Build production image without layer cache
	@echo "$(YELLOW)Building production image (no cache)...$(NC)"
	$(DOCKER) build \
		--no-cache \
		-t $(DOCKER_IMAGE) \
		-f $(DOCKER_DIR)/Dockerfile \
		$(CONTEXT)
	@echo "$(GREEN)Production image built (no cache): $(DOCKER_IMAGE)$(NC)"

.PHONY: build-dev
build-dev: ## Build development image with hot-reload
	@echo "$(YELLOW)Building development image: $(DOCKER_DEV_IMG)...$(NC)"
	$(DOCKER) build \
		-t $(DOCKER_DEV_IMG) \
		-f $(DOCKER_DIR)/Dockerfile.dev \
		$(CONTEXT)
	@echo "$(GREEN)Development image built: $(DOCKER_DEV_IMG)$(NC)"

.PHONY: build-all
build-all: build build-dev ## Build both production and development images

.PHONY: build-service
build-service: ## Build a specific service only (usage: make build-service SVC=api-gateway)
	@echo "$(YELLOW)Building service: $(SVC)...$(NC)"
	$(COMPOSE) -f $(COMPOSE_FILE) build $(SVC)
	@echo "$(GREEN)Service built: $(SVC)$(NC)"

# =============================================================================
# RUN TARGETS
# =============================================================================

.PHONY: run
run: ## Start the full platform (all services, detached)
	@echo "$(YELLOW)Starting ENI Enterprise platform...$(NC)"
	$(COMPOSE) -f $(COMPOSE_FILE) up -d
	@echo "$(GREEN)Platform running. Use 'make status' to check health.$(NC)"
	@echo "$(BLUE)Services:$(NC)"
	@$(COMPOSE) -f $(COMPOSE_FILE) ps --format 'table {{.Name}}\t{{.Status}}\t{{.Ports}}'

.PHONY: run-core
run-core: ## Start core infrastructure only (kernel, redis, postgres, event-hub)
	@echo "$(YELLOW)Starting core infrastructure...$(NC)"
	$(COMPOSE) -f $(COMPOSE_FILE) up -d redis postgres kernel event-hub service-mesh
	@echo "$(GREEN)Core infrastructure running.$(NC)"

.PHONY: run-swarm
run-swarm: ## Start ENI Swarm ecosystem (swarm + turbocharger + free-router)
	@echo "$(YELLOW)Starting ENI Swarm ecosystem...$(NC)"
	$(COMPOSE) -f $(COMPOSE_FILE) up -d eni-swarm swarm-turbocharger free-router
	@echo "$(GREEN)ENI Swarm ecosystem running.$(NC)"

.PHONY: run-dev
run-dev: ## Start platform in development mode with hot-reload
	@echo "$(YELLOW)Starting ENI Enterprise platform (dev mode)...$(NC)"
	@test -f $(COMPOSE_DEV) && \
		$(COMPOSE) -f $(COMPOSE_FILE) -f $(COMPOSE_DEV) up -d || \
		$(COMPOSE) -f $(COMPOSE_FILE) up -d
	@echo "$(GREEN)Platform running in dev mode.$(NC)"

.PHONY: run-local
run-local: ## Run platform kernel locally (no Docker, for debugging)
	@echo "$(YELLOW)Starting kernel locally...$(NC)"
	cd $(CONTEXT) && python -m kernel

.PHONY: stop
stop: ## Stop all services (containers remain)
	@echo "$(YELLOW)Stopping ENI Enterprise platform...$(NC)"
	$(COMPOSE) -f $(COMPOSE_FILE) stop
	@echo "$(GREEN)Platform stopped.$(NC)"

.PHONY: down
down: ## Stop and remove all containers + networks
	@echo "$(YELLOW)Tearing down ENI Enterprise platform...$(NC)"
	$(COMPOSE) -f $(COMPOSE_FILE) down
	@echo "$(GREEN)Platform torn down.$(NC)"

.PHONY: down-volumes
down-volumes: ## Stop, remove containers + volumes (DESTRUCTIVE)
	@echo "$(RED)WARNING: This will delete all data volumes!$(NC)"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
		echo; \
		if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
			$(COMPOSE) -f $(COMPOSE_FILE) down -v --remove-orphans; \
			echo "$(GREEN)Containers, networks, and volumes removed.$(NC)"; \
		else \
			echo "$(YELLOW)Aborted.$(NC)"; \
		fi

.PHONY: restart
restart: down run ## Restart the full platform (fresh state)

.PHONY: rebuild
rebuild: build-no-cache down run ## Full rebuild and restart

# =============================================================================
# TEST TARGETS
# =============================================================================

.PHONY: test
test: ## Run unit tests inside containers
	@echo "$(YELLOW)Running unit tests...$(NC)"
	$(COMPOSE) -f $(COMPOSE_FILE) run --rm --no-deps kernel \
		pytest tests/ -v --tb=short --maxfail=10 $(TEST_ARGS)
	@echo "$(GREEN)Unit tests passed.$(NC)"

.PHONY: test-cov
test-cov: ## Run tests with coverage report
	@echo "$(YELLOW)Running tests with coverage...$(NC)"
	$(COMPOSE) -f $(COMPOSE_FILE) run --rm --no-deps kernel \
		pytest tests/ -v \
			--tb=short \
			--cov=. \
			--cov-report=term-missing \
			--cov-report=html \
			$(TEST_ARGS)
	@echo "$(GREEN)Coverage report generated.$(NC)"

.PHONY: test-integration
test-integration: ## Run integration tests against running platform
	@echo "$(YELLOW)Running integration tests...$(NC)"
	$(COMPOSE) -f $(COMPOSE_FILE) run --rm kernel \
		pytest tests/integration/ -v --tb=long $(TEST_ARGS)
	@echo "$(GREEN)Integration tests passed.$(NC)"

.PHONY: test-health
test-health: ## Run health checks against all services
	@echo "$(YELLOW)Checking service health...$(NC)"
	@for svc in kernel api-gateway dashboard eni-swarm event-hub service-mesh \
		swarm-turbocharger free-router claude-code-server; do \
		port=$$($(COMPOSE) -f $(COMPOSE_FILE) port $$svc 2>/dev/null | awk -F: '{print $$2}'); \
		if [ -n "$$port" ]; then \
			curl -sf "http://localhost:$$port/health" >/dev/null 2>&1 && \
				echo "  $(GREEN)[OK]$(NC)    $$svc ($$port)" || \
				echo "  $(RED)[FAIL]$(NC)  $$svc ($$port)"; \
		else \
			echo "  $(YELLOW)[N/A]$(NC)  $$svc (not exposed)"; \
		fi; \
	done || true

.PHONY: lint-docker
lint-docker: ## Lint Dockerfile with hadolint (if installed)
	@which hadolint >/dev/null 2>&1 && \
		hadolint $(DOCKER_DIR)/Dockerfile $(DOCKER_DIR)/Dockerfile.dev || \
		echo "$(YELLOW)hadolint not installed — skipping$(NC)"

# =============================================================================
# DEPLOY TARGETS
# =============================================================================

.PHONY: deploy
deploy: build ## Deploy to production (docker compose up -d)
	@echo "$(YELLOW)Deploying ENI Enterprise platform...$(NC)"
	$(COMPOSE) -f $(COMPOSE_FILE) up -d --force-recreate
	@echo "$(GREEN)Platform deployed.$(NC)"
	@$(MAKE) status

.PHONY: deploy-swarm
deploy-swarm: ## Deploy as Docker Swarm stack (if swarm is active)
	@echo "$(YELLOW)Deploying as Docker Swarm stack...$(NC)"
	$(DOCKER) stack deploy -c $(COMPOSE_FILE) $(PROJECT_NAME)
	@echo "$(GREEN)Stack deployed: $(PROJECT_NAME)$(NC)"

.PHONY: deploy-rolling
deploy-rolling: ## Rolling update of all services without downtime
	@echo "$(YELLOW)Performing rolling update...$(NC)"
	$(COMPOSE) -f $(COMPOSE_FILE) up -d --no-deps --force-recreate \
		api-gateway dashboard eni-swarm claude-code-server
	$(COMPOSE) -f $(COMPOSE_FILE) up -d --no-deps --force-recreate \
		swarm-turbocharger free-router
	$(COMPOSE) -f $(COMPOSE_FILE) up -d --no-deps --force-recreate \
		event-hub service-mesh
	@echo "$(GREEN)Rolling update complete.$(NC)"

.PHONY: push
push: build ## Tag and push image to container registry
	@echo "$(YELLOW)Pushing image to $(REGISTRY)/$(DOCKER_IMAGE)...$(NC)"
	$(DOCKER) tag $(DOCKER_IMAGE) $(REGISTRY)/$(DOCKER_IMAGE)
	$(DOCKER) push $(REGISTRY)/$(DOCKER_IMAGE)
	@echo "$(GREEN)Image pushed to $(REGISTRY)/$(DOCKER_IMAGE)$(NC)"

# =============================================================================
# LOGS & STATUS
# =============================================================================

.PHONY: logs
logs: ## Tail logs from all services
	$(COMPOSE) -f $(COMPOSE_FILE) logs -f

.PHONY: logs-service
logs-service: ## Tail logs for a specific service (usage: make logs-service SVC=eni-swarm)
	$(COMPOSE) -f $(COMPOSE_FILE) logs -f $(SVC)

.PHONY: ps
ps: ## Show running container status
	@$(COMPOSE) -f $(COMPOSE_FILE) ps --format 'table {{.Name}}\t{{.Status}}\t{{.Ports}}'

.PHONY: status
status: ## Show platform health status (HTTP checks)
	@echo "$(YELLOW)ENI Enterprise Platform — Health Status$(NC)"
	@echo "$(YELLOW)========================================$(NC)"
	@echo ""
	@echo "$(BLUE)Core:$(NC)"
	@curl -sf http://localhost:8000/health 2>/dev/null && echo "  $(GREEN)[OK]$(NC)  Kernel        (8000)" || echo "  $(RED)[DOWN]$(NC) Kernel        (8000)"
	@curl -sf http://localhost:8421/health 2>/dev/null && echo "  $(GREEN)[OK]$(NC)  API Gateway   (8421)" || echo "  $(RED)[DOWN]$(NC) API Gateway   (8421)"
	@curl -sf http://localhost:8900/health 2>/dev/null && echo "  $(GREEN)[OK]$(NC)  Event Hub     (8900)" || echo "  $(RED)[DOWN]$(NC) Event Hub     (8900)"
	@curl -sf http://localhost:8910/health 2>/dev/null && echo "  $(GREEN)[OK]$(NC)  Service Mesh  (8910)" || echo "  $(RED)[DOWN]$(NC) Service Mesh  (8910)"
	@echo ""
	@echo "$(BLUE)Swarm:$(NC)"
	@curl -sf http://localhost:8420/health 2>/dev/null && echo "  $(GREEN)[OK]$(NC)  ENI Swarm     (8420)" || echo "  $(RED)[DOWN]$(NC) ENI Swarm     (8420)"
	@curl -sf http://localhost:8922/health 2>/dev/null && echo "  $(GREEN)[OK]$(NC)  Turbocharger  (8922)" || echo "  $(RED)[DOWN]$(NC) Turbocharger  (8922)"
	@curl -sf http://localhost:8920/health 2>/dev/null && echo "  $(GREEN)[OK]$(NC)  Free Router   (8920)" || echo "  $(RED)[DOWN]$(NC) Free Router   (8920)"
	@echo ""
	@echo "$(BLUE)Claude Code:$(NC)"
	@curl -sf http://localhost:9120/health 2>/dev/null && echo "  $(GREEN)[OK]$(NC)  Claude Code Server (9120)" || echo "  $(RED)[DOWN]$(NC) Claude Code Server (9120)"
	@echo ""
	@echo "$(BLUE)Infrastructure:$(NC)"
	@docker exec eni-redis redis-cli ping 2>/dev/null | grep -q PONG && echo "  $(GREEN)[OK]$(NC)  Redis     (6379)" || echo "  $(RED)[DOWN]$(NC) Redis     (6379)"
	@docker exec eni-postgres pg_isready -U eni -d eni_enterprise 2>/dev/null | grep -q accepting && echo "  $(GREEN)[OK]$(NC)  Postgres  (5432)" || echo "  $(RED)[DOWN]$(NC) Postgres  (5432)"
	@echo ""
	@echo "$(BLUE)Monitoring:$(NC)"
	@curl -sf http://localhost:9090/-/healthy 2>/dev/null && echo "  $(GREEN)[OK]$(NC)  Prometheus (9090)" || echo "  $(YELLOW)[N/A]$(NC) Prometheus (9090)"
	@curl -sf http://localhost:3000/api/health 2>/dev/null && echo "  $(GREEN)[OK]$(NC)  Grafana    (3000)" || echo "  $(YELLOW)[N/A]$(NC) Grafana    (3000)"

# =============================================================================
# UTILITIES
# =============================================================================

.PHONY: shell
shell: ## Open a bash shell inside the kernel container
	$(COMPOSE) -f $(COMPOSE_FILE) exec kernel /bin/bash

.PHONY: shell-service
shell-service: ## Open a shell in a specific service (usage: make shell-service SVC=eni-swarm)
	$(COMPOSE) -f $(COMPOSE_FILE) exec $(SVC) /bin/bash

.PHONY: shell-db
shell-db: ## Open psql in the postgres container
	$(COMPOSE) -f $(COMPOSE_FILE) exec postgres psql -U eni -d eni_enterprise

.PHONY: shell-redis
shell-redis: ## Open redis-cli in the redis container
	$(COMPOSE) -f $(COMPOSE_FILE) exec redis redis-cli

.PHONY: stats
stats: ## Show live container resource usage (CPU, memory)
	$(DOCKER) stats --no-stream \
		eni-kernel eni-api-gateway eni-dashboard eni-eni-swarm \
		eni-event-hub eni-service-mesh eni-swarm-turbocharger \
		eni-free-router eni-claude-code-server eni-redis eni-postgres

.PHONY: clean
clean: ## Remove all build artifacts, caches, and temporary files
	@echo "$(YELLOW)Cleaning build artifacts...$(NC)"
	cd $(CONTEXT) && find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	cd $(CONTEXT) && find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	cd $(CONTEXT) && find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	cd $(CONTEXT) && find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	cd $(CONTEXT) && find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf htmlcov/ .coverage coverage.xml junit.xml 2>/dev/null || true
	@echo "$(GREEN)Clean complete.$(NC)"

.PHONY: clean-docker
clean-docker: ## Remove Docker build cache and dangling images
	@echo "$(YELLOW)Cleaning Docker artifacts...$(NC)"
	$(DOCKER) builder prune -f
	$(DOCKER) image prune -f
	@echo "$(GREEN)Docker clean complete.$(NC)"

.PHONY: clean-all
clean-all: down-volumes clean clean-docker ## Full clean: containers, volumes, caches, images
	@echo "$(GREEN)Full clean complete.$(NC)"

# =============================================================================
# COMPLETE PIPELINE
# =============================================================================

.PHONY: ci
ci: lint-docker build test test-health ## CI pipeline: lint docker, build, test, health check
	@echo "$(GREEN)CI pipeline passed.$(NC)"

.PHONY: ship
ship: build test push deploy ## Full ship pipeline: build -> test -> push -> deploy
	@echo "$(GREEN)Ship pipeline complete!$(NC)"