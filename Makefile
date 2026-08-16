# =============================================================================
# ENI Enterprise Platform — Makefile (ROOT WRAPPER)
# Delegates to docker/Makefile for all Docker operations.
# Also provides local Python dev targets.
# =============================================================================

SHELL := /bin/bash
.DEFAULT_GOAL := help

PYTHON   := python3
PIP      := $(PYTHON) -m pip
DOCKER   := docker
COMPOSE  := docker compose

PROJECT_NAME ?= eni-enterprise
DOCKER_DIR  ?= docker

GREEN  := \033[0;32m
YELLOW := \033[0;33m
RED    := \033[0;31m
CYAN   := \033[0;36m
NC     := \033[0m

.PHONY: help
help:
	@echo "$(CYAN)ENI Enterprise Platform$(NC)"
	@echo "$(CYAN)======================$(NC)"
	@echo ""
	@echo "$(GREEN)Docker targets (via docker/Makefile):$(NC)"
	@echo "  build         Build production image"
	@echo "  run           Start full platform"
	@echo "  stop          Stop platform"
	@echo "  restart       Restart platform"
	@echo "  test          Run tests in container"
	@echo "  deploy        Deploy to production"
	@echo "  status        Show platform health"
	@echo "  logs          Tail all logs"
	@echo "  clean         Remove artifacts"
	@echo ""
	@echo "$(GREEN)Local dev targets:$(NC)"
	@echo "  setup         Install Python dependencies"
	@echo "  lint          Run ruff linter"
	@echo "  typecheck     Run mypy"
	@echo "  test-local    Run tests locally"
	@echo ""
	@echo "For full list: make -f docker/Makefile help"

# ── Docker Delegation ────────────────────────────────────────────────────────
.PHONY: build run stop restart test deploy status logs clean build-dev run-dev run-core run-swarm down down-volumes rebuild

build:
	@$(MAKE) -f $(DOCKER_DIR)/Makefile build
build-dev:
	@$(MAKE) -f $(DOCKER_DIR)/Makefile build-dev
build-no-cache:
	@$(MAKE) -f $(DOCKER_DIR)/Makefile build-no-cache
run:
	@$(MAKE) -f $(DOCKER_DIR)/Makefile run
run-dev:
	@$(MAKE) -f $(DOCKER_DIR)/Makefile run-dev
run-core:
	@$(MAKE) -f $(DOCKER_DIR)/Makefile run-core
run-swarm:
	@$(MAKE) -f $(DOCKER_DIR)/Makefile run-swarm
run-local:
	@echo "$(YELLOW)Starting kernel locally...$(NC)"
	$(PYTHON) -m kernel
stop:
	@$(MAKE) -f $(DOCKER_DIR)/Makefile stop
down:
	@$(MAKE) -f $(DOCKER_DIR)/Makefile down
down-volumes:
	@$(MAKE) -f $(DOCKER_DIR)/Makefile down-volumes
restart:
	@$(MAKE) -f $(DOCKER_DIR)/Makefile restart
rebuild:
	@$(MAKE) -f $(DOCKER_DIR)/Makefile rebuild
test:
	@$(MAKE) -f $(DOCKER_DIR)/Makefile test
test-cov:
	@$(MAKE) -f $(DOCKER_DIR)/Makefile test-cov
test-integration:
	@$(MAKE) -f $(DOCKER_DIR)/Makefile test-integration
deploy:
	@$(MAKE) -f $(DOCKER_DIR)/Makefile deploy
push:
	@$(MAKE) -f $(DOCKER_DIR)/Makefile push
status:
	@$(MAKE) -f $(DOCKER_DIR)/Makefile status
logs:
	@$(MAKE) -f $(DOCKER_DIR)/Makefile logs
shell:
	@$(MAKE) -f $(DOCKER_DIR)/Makefile shell
clean:
	@$(MAKE) -f $(DOCKER_DIR)/Makefile clean
clean-all:
	@$(MAKE) -f $(DOCKER_DIR)/Makefile clean-all
ci:
	@$(MAKE) -f $(DOCKER_DIR)/Makefile ci
ship:
	@$(MAKE) -f $(DOCKER_DIR)/Makefile ship

# ── Local Python Development ─────────────────────────────────────────────────
.PHONY: setup setup-dev lint format typecheck test-local test-local-cov

setup: ## Install Python dependencies locally
	@echo "$(YELLOW)Installing dependencies...$(NC)"
	$(PIP) install --upgrade pip setuptools wheel
	$(PIP) install -r requirements.txt 2>/dev/null || $(PIP) install fastapi uvicorn[standard] pydantic pyyaml redis httpx psutil
	@echo "$(GREEN)Done.$(NC)"

setup-dev: setup ## Install dev tools locally
	@$(PIP) install ruff mypy pytest pytest-cov pre-commit
	@echo "$(GREEN)Dev tools installed.$(NC)"

lint: ## Run ruff linter locally
	$(PYTHON) -m ruff check . && $(PYTHON) -m ruff format --check .

format: ## Auto-format code with ruff
	$(PYTHON) -m ruff format . && $(PYTHON) -m ruff check --fix .

typecheck: ## Run mypy type checker locally
	$(PYTHON) -m mypy .

test-local: ## Run pytest locally
	$(PYTHON) -m pytest --tb=short --maxfail=10

test-local-cov: ## Run tests with coverage locally
	$(PYTHON) -m pytest --tb=short --cov=. --cov-report=term-missing

# ── SLICE C: Hermes portable skills/LSP/MCP/plugin pack ────────────────────
# Merged into the existing wrapper — does not override any target above.
.PHONY: skillspack-install skillspack-dryrun eni-install eni-doctor eni-status eni-up up-hermes

skillspack-install: ## Install the portable skills/LSP/MCP/plugin pack into ~/.hermes
	@bash scripts/install_skillspack.sh

skillspack-dryrun: ## Show what the skillspack installer would do (no copy)
	@bash scripts/install_skillspack.sh --dry-run

eni-install: ## CLI wrapper: deploy the portable pack (pass through --dry-run/--force)
	@$(PYTHON) scripts/eni_cli install

eni-doctor: ## CLI: report platform+kernel+pack health
	@$(PYTHON) scripts/eni_cli doctor

eni-status: ## CLI: print module count / healthy / tests from config
	@$(PYTHON) scripts/eni_cli status

eni-up: ## CLI: print docker compose bring-up instructions
	@$(PYTHON) scripts/eni_cli up

up-hermes: ## Bring up ONLY the Hermes portable layer (profiled, opt-in)
	@$(COMPOSE) -f docker-compose.yml --profile hermes up -d
# --- one-command operations (added 2026-08-16) ------------------------------
.PHONY: eni-setup eni-local eni-fleet eni-boot
eni-setup: ## One-command setup: skillspack + systemd services + verify
	@PYTHONPATH=. $(PYTHON) scripts/eni_cli setup
eni-local: ## Boot the side-by-side local stack (controller + mp + hermes local-agent)
	@PYTHONPATH=. $(PYTHON) scripts/eni_cli local
eni-fleet: ## Start a builder client (llm worker) on the multiplayer server
	@PYTHONPATH=. $(PYTHON) scripts/eni_cli fleet
eni-boot: ## Boot all enterprise servers (headless)
	@bash scripts/boot_all.sh --headless --no-builder
