# ARGUS — Development & Deployment Helper
# Run `make help` to see all available commands.
#
# Requires: docker, docker compose, python3 (>=3.12), node/npm

.DEFAULT_GOAL := help
SHELL         := /bin/bash

# ─── Colours ───────────────────────────────────────────────────────────────────
CYAN  := \033[0;36m
RESET := \033[0m

# ─── Help ──────────────────────────────────────────────────────────────────────
.PHONY: help
help:
	@echo ""
	@echo "  $(CYAN)ARGUS — available make commands$(RESET)"
	@echo ""
	@echo "  $(CYAN)Setup$(RESET)"
	@echo "    make setup            First-time setup: env, backend venv, generator venv, npm install"
	@echo "    make setup-generator  Set up generator venv + populate Neo4j (~15s)"
	@echo ""
	@echo "  $(CYAN)Local development$(RESET)"
	@echo "    make infra-up         Start Neo4j + Redis via Docker Compose (background)"
	@echo "    make infra-down       Stop Neo4j + Redis"
	@echo "    make infra-logs       Tail Docker logs for Neo4j and Redis"
	@echo "    make backend          Start FastAPI backend (dev mode, --reload)"
	@echo "    make frontend         Start Next.js frontend (dev mode)"
	@echo "    make dev              Print instructions for running all services"
	@echo ""
	@echo "  $(CYAN)Docker (full stack)$(RESET)"
	@echo "    make docker-build     Build backend Docker image (includes generator)"
	@echo "    make docker-up        Start full stack via Docker Compose (local dev)"
	@echo "    make docker-down      Stop full Docker stack"
	@echo ""
	@echo "  $(CYAN)Generator$(RESET)"
	@echo "    make world            (Re)generate the synthetic world — WIPES existing graph"
	@echo "    make world-no-wipe    Additive world generation (keeps existing data)"
	@echo ""
	@echo "  $(CYAN)Checks$(RESET)"
	@echo "    make lint             Run ruff + eslint"
	@echo "    make typecheck        Run mypy (backend)"
	@echo "    make test             Run pytest (backend)"
	@echo "    make health           Probe http://localhost:8000/api/health"
	@echo ""
	@echo "  $(CYAN)Frontend build$(RESET)"
	@echo "    make build-frontend   Production build of the Next.js app"
	@echo ""

# ─── Setup ────────────────────────────────────────────────────────────────────
.PHONY: setup
setup:
	@echo "$(CYAN)▶ Copying .env.example → .env (if .env doesn't exist)$(RESET)"
	@test -f .env || cp .env.example .env

	@echo "$(CYAN)▶ Setting up backend virtualenv$(RESET)"
	@cd backend && python3 -m venv .venv && .venv/bin/pip install --quiet -e ".[dev]"

	@echo "$(CYAN)▶ Setting up generator virtualenv$(RESET)"
	@cd generator && python3 -m venv .venv && .venv/bin/pip install --quiet -r requirements.txt

	@echo "$(CYAN)▶ Installing frontend dependencies$(RESET)"
	@cd frontend && npm install --silent

	@echo ""
	@echo "  ✅  Setup complete."
	@echo "  Next: run 'make infra-up' to start Neo4j and Redis,"
	@echo "        then 'make world' to populate the graph,"
	@echo "        then run backend and frontend in separate terminals."
	@echo ""

.PHONY: setup-generator
setup-generator:
	@echo "$(CYAN)▶ Setting up generator virtualenv$(RESET)"
	@cd generator && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	@echo "$(CYAN)▶ Waiting for Neo4j to be healthy before generating world...$(RESET)"
	@for i in $$(seq 1 30); do \
		if docker compose ps neo4j 2>/dev/null | grep -q "healthy"; then break; fi; \
		echo "  Waiting for Neo4j... ($${i}/30)"; \
		sleep 5; \
	done
	@echo "$(CYAN)▶ Populating Neo4j with synthetic world (seed=42)$(RESET)"
	@cd generator && .venv/bin/python3 generate_world.py --seed 42

# ─── Infrastructure ───────────────────────────────────────────────────────────
.PHONY: infra-up
infra-up:
	@echo "$(CYAN)▶ Starting Neo4j + Redis$(RESET)"
	docker compose up -d neo4j redis
	@echo "  Waiting for services to become healthy (may take 30s on first run)..."
	@docker compose ps

.PHONY: infra-down
infra-down:
	docker compose stop neo4j redis

.PHONY: infra-logs
infra-logs:
	docker compose logs -f neo4j redis

# ─── Local Development ────────────────────────────────────────────────────────
.PHONY: backend
backend:
	@echo "$(CYAN)▶ Starting FastAPI backend (dev mode)$(RESET)"
	@cd backend && .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

.PHONY: frontend
frontend:
	@echo "$(CYAN)▶ Starting Next.js frontend (dev mode)$(RESET)"
	@cd frontend && npm run dev

.PHONY: dev
dev:
	@echo ""
	@echo "  $(CYAN)Run each of these in a separate terminal:$(RESET)"
	@echo ""
	@echo "  Terminal 1 — Infrastructure"
	@echo "    make infra-up"
	@echo ""
	@echo "  Terminal 2 — Backend"
	@echo "    make backend"
	@echo ""
	@echo "  Terminal 3 — Frontend"
	@echo "    make frontend"
	@echo ""
	@echo "  Then open: http://localhost:3000"
	@echo "  API docs:  http://localhost:8000/docs"
	@echo ""

# ─── Generator ────────────────────────────────────────────────────────────────
.PHONY: world
world:
	@echo "$(CYAN)▶ Regenerating synthetic world (wipes existing graph)$(RESET)"
	@cd generator && .venv/bin/python3 generate_world.py --seed 42

.PHONY: world-no-wipe
world-no-wipe:
	@echo "$(CYAN)▶ Additive world generation (no wipe)$(RESET)"
	@cd generator && .venv/bin/python3 generate_world.py --seed 42 --no-wipe

# ─── Docker ───────────────────────────────────────────────────────────────────
.PHONY: docker-build
docker-build:
	@echo "$(CYAN)▶ Building backend Docker image (includes bundled generator)$(RESET)"
	docker compose build backend

.PHONY: docker-up
docker-up:
	@echo "$(CYAN)▶ Starting full Docker stack$(RESET)"
	docker compose up -d

.PHONY: docker-down
docker-down:
	docker compose down

# ─── Checks ───────────────────────────────────────────────────────────────────
.PHONY: lint
lint:
	@echo "$(CYAN)▶ Running ruff (backend)$(RESET)"
	@cd backend && .venv/bin/ruff check .
	@echo "$(CYAN)▶ Running eslint (frontend)$(RESET)"
	@cd frontend && npm run lint

.PHONY: typecheck
typecheck:
	@echo "$(CYAN)▶ Running mypy (backend)$(RESET)"
	@cd backend && .venv/bin/mypy app

.PHONY: test
test:
	@echo "$(CYAN)▶ Running pytest (backend)$(RESET)"
	@cd backend && .venv/bin/pytest

.PHONY: health
health:
	@curl -s http://localhost:8000/api/health | python3 -m json.tool

# ─── Frontend Build ───────────────────────────────────────────────────────────
.PHONY: build-frontend
build-frontend:
	@echo "$(CYAN)▶ Building frontend for production$(RESET)"
	@cd frontend && npm run build
