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
	@echo -e ""
	@echo -e "  $(CYAN)ARGUS — available make commands$(RESET)"
	@echo -e ""
	@echo -e "  $(CYAN)Setup$(RESET)"
	@echo -e "    make setup            First-time setup: env, backend venv, generator venv, npm install"
	@echo -e "    make setup-generator  Set up generator venv + populate Neo4j (~15s)"
	@echo -e ""
	@echo -e "  $(CYAN)Local development$(RESET)"
	@echo -e "    make infra-up         Start Neo4j + Redis + PostgreSQL (background)"
	@echo -e "    make infra-down       Stop the databases"
	@echo -e "    make infra-logs       Tail Docker logs for the databases"
	@echo -e "    make backend          Start FastAPI backend (dev mode, --reload)"
	@echo -e "    make frontend         Start Next.js frontend (dev mode)"
	@echo -e "    make dev              Print instructions for running all services"
	@echo -e ""
	@echo -e "  $(CYAN)Docker (full stack)$(RESET)"
	@echo -e "    make docker-build     Build backend Docker image (includes generator)"
	@echo -e "    make docker-up        Start full stack via Docker Compose (local dev)"
	@echo -e "    make docker-down      Stop full Docker stack"
	@echo -e ""
	@echo -e "  $(CYAN)Generator$(RESET)"
	@echo -e "    make world            (Re)generate the synthetic world — WIPES existing graph"
	@echo -e "    make world-no-wipe    Additive world generation (keeps existing data)"
	@echo -e ""
	@echo -e "  $(CYAN)Checks$(RESET)"
	@echo -e "    make lint             Run ruff + eslint"
	@echo -e "    make typecheck        Run mypy (backend)"
	@echo -e "    make test             Run pytest (backend)"
	@echo -e "    make health           Probe http://localhost:8000/api/health"
	@echo -e "    make security         pip-audit + bandit + npm audit"
	@echo -e "    make verify           Verify the audit hash chain"
	@echo -e "    make ci               Everything CI runs, in CI's order"
	@echo -e ""
	@echo -e "  $(CYAN)Lifecycle$(RESET)"
	@echo -e "    make seed             Generate the world and attribute it to its source"
	@echo -e "    make stop             Stop backend, frontend and databases (keeps data)"
	@echo -e "    make reset            Destroy all local data and start over"
	@echo -e ""
	@echo -e "  $(CYAN)Frontend build$(RESET)"
	@echo -e "    make build-frontend   Production build of the Next.js app"
	@echo -e ""

# ─── Setup ────────────────────────────────────────────────────────────────────
.PHONY: setup
setup:
	@echo -e "$(CYAN)▶ Copying .env.example → .env (if .env doesn't exist)$(RESET)"
	@test -f .env || cp .env.example .env

	@echo -e "$(CYAN)▶ Setting up backend virtualenv$(RESET)"
	@cd backend && python3 -m venv .venv && .venv/bin/pip install --quiet -e ".[dev]"

	@echo -e "$(CYAN)▶ Setting up generator virtualenv$(RESET)"
	@cd generator && python3 -m venv .venv && .venv/bin/pip install --quiet -r requirements.txt

	@echo -e "$(CYAN)▶ Installing frontend dependencies$(RESET)"
	@cd frontend && npm install --silent

	@echo -e ""
	@echo -e "  ✅  Setup complete."
	@echo -e "  Next: run 'make infra-up' to start the databases,"
	@echo -e "        then 'make world' to populate the graph,"
	@echo -e "        then run backend and frontend in separate terminals."
	@echo -e ""

.PHONY: setup-generator
setup-generator:
	@echo -e "$(CYAN)▶ Setting up generator virtualenv$(RESET)"
	@cd generator && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	@echo -e "$(CYAN)▶ Waiting for Neo4j to be healthy before generating world...$(RESET)"
	@for i in $$(seq 1 30); do \
		if docker compose ps neo4j 2>/dev/null | grep -q "healthy"; then break; fi; \
		echo "  Waiting for Neo4j... ($${i}/30)"; \
		sleep 5; \
	done
	@echo -e "$(CYAN)▶ Populating Neo4j with synthetic world (seed=42)$(RESET)"
	@cd generator && .venv/bin/python3 generate_world.py --seed 42

# ─── Infrastructure ───────────────────────────────────────────────────────────
# Postgres is not optional. It holds identity, the audit chain, provenance,
# ingestion and entity resolution — without it the backend cannot authenticate
# a single request. This target used to start only Neo4j and Redis, which meant
# following `make help` produced a stack that could not serve anything.
.PHONY: infra-up
infra-up:
	@echo -e "$(CYAN)▶ Starting Neo4j + Redis + PostgreSQL$(RESET)"
	docker compose up -d neo4j redis postgres
	@echo -e "  Waiting for services to become healthy (may take 30s on first run)..."
	@for i in $$(seq 1 40); do \
		ready=$$(docker compose ps --format '{{.Service}} {{.Health}}' 2>/dev/null | grep -c healthy); \
		if [ "$$ready" -ge 3 ]; then break; fi; \
		sleep 3; \
	done
	@docker compose ps

.PHONY: infra-down
infra-down:
	docker compose stop neo4j redis postgres

.PHONY: infra-logs
infra-logs:
	docker compose logs -f neo4j redis postgres

# ─── Local Development ────────────────────────────────────────────────────────
.PHONY: backend
backend:
	@echo -e "$(CYAN)▶ Starting FastAPI backend (dev mode)$(RESET)"
	@cd backend && .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

.PHONY: frontend
frontend:
	@echo -e "$(CYAN)▶ Starting Next.js frontend (dev mode)$(RESET)"
	@cd frontend && npm run dev

.PHONY: dev
dev:
	@echo -e ""
	@echo -e "  $(CYAN)Run each of these in a separate terminal:$(RESET)"
	@echo -e ""
	@echo -e "  Terminal 1 — Infrastructure"
	@echo -e "    make infra-up"
	@echo -e ""
	@echo -e "  Terminal 2 — Backend"
	@echo -e "    make backend"
	@echo -e ""
	@echo -e "  Terminal 3 — Frontend"
	@echo -e "    make frontend"
	@echo -e ""
	@echo -e "  Then open: http://localhost:3000"
	@echo -e "  API docs:  http://localhost:8000/docs"
	@echo -e ""

# ─── Generator ────────────────────────────────────────────────────────────────
.PHONY: world
world:
	@echo -e "$(CYAN)▶ Regenerating synthetic world (wipes existing graph)$(RESET)"
	@cd generator && .venv/bin/python3 generate_world.py --seed 42

.PHONY: world-no-wipe
world-no-wipe:
	@echo -e "$(CYAN)▶ Additive world generation (no wipe)$(RESET)"
	@cd generator && .venv/bin/python3 generate_world.py --seed 42 --no-wipe

# ─── Docker ───────────────────────────────────────────────────────────────────
.PHONY: docker-build
docker-build:
	@echo -e "$(CYAN)▶ Building backend Docker image (includes bundled generator)$(RESET)"
	docker compose build backend

.PHONY: docker-up
docker-up:
	@echo -e "$(CYAN)▶ Starting full Docker stack$(RESET)"
	docker compose up -d

.PHONY: docker-down
docker-down:
	docker compose down

# ─── Checks ───────────────────────────────────────────────────────────────────
.PHONY: lint
lint:
	@echo -e "$(CYAN)▶ Running ruff (backend)$(RESET)"
	@cd backend && .venv/bin/ruff check .
	@echo -e "$(CYAN)▶ Running eslint (frontend)$(RESET)"
	@cd frontend && npm run lint

.PHONY: typecheck
typecheck:
	@echo -e "$(CYAN)▶ Running mypy (backend)$(RESET)"
	@cd backend && .venv/bin/mypy app

.PHONY: test
test:
	@echo -e "$(CYAN)▶ Running pytest (backend)$(RESET)"
	@cd backend && .venv/bin/pytest

.PHONY: health
health:
	@curl -s http://localhost:8000/api/health | python3 -m json.tool

# ─── Lifecycle ────────────────────────────────────────────────────────────────

.PHONY: stop
stop:
	@echo -e "$(CYAN)▶ Stopping backend, frontend and infrastructure$(RESET)"
	@-lsof -ti:8000 | xargs kill 2>/dev/null || true
	@-lsof -ti:3000 | xargs kill 2>/dev/null || true
	@docker compose stop
	@echo -e "  Stopped. Data is preserved — use 'make reset' to discard it."

# Destroys every local volume. Named explicitly rather than folded into `stop`
# so it can never be run by reflex: it discards the graph, the audit chain and
# every account.
.PHONY: reset
reset:
	@echo -e "$(CYAN)▶ Destroying local data (graph, identity, audit, provenance)$(RESET)"
	docker compose down -v
	@echo -e "  Gone. Run 'make infra-up' then 'make world' to rebuild."

.PHONY: seed
seed:
	@echo -e "$(CYAN)▶ Generating the world and attributing it to its source$(RESET)"
	@cd generator && .venv/bin/python3 generate_world.py --seed 42
	@cd backend && .venv/bin/python3 -m app.cli backfill-provenance

# ─── Verification ─────────────────────────────────────────────────────────────

# Everything CI runs, in the same order, so a red pipeline can be reproduced
# before pushing rather than after.
.PHONY: ci
ci: lint typecheck test security build-frontend
	@echo -e ""
	@echo -e "  ✅  Full CI-equivalent suite passed."
	@echo -e ""

.PHONY: security
security:
	@echo -e "$(CYAN)▶ Backend security (pip-audit, bandit)$(RESET)"
	@cd backend && .venv/bin/pip-audit --desc --skip-editable
	@cd backend && .venv/bin/bandit -r app -ll --skip B101
	@echo -e "$(CYAN)▶ Frontend security (npm audit)$(RESET)"
	@cd frontend && npm audit --audit-level=high

.PHONY: verify
verify:
	@echo -e "$(CYAN)▶ Audit chain$(RESET)"
	@cd backend && .venv/bin/python3 -m app.cli verify-audit

# ─── Frontend Build ───────────────────────────────────────────────────────────
.PHONY: build-frontend
build-frontend:
	@echo -e "$(CYAN)▶ Building frontend for production$(RESET)"
	@cd frontend && npm run build
