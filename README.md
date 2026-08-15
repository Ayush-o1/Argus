# ARGUS

A graph-native investigation and analytics platform built entirely on procedurally generated synthetic data.

ARGUS models a **global operating picture**: 70 real cities across 50 countries and 10 regions, with real coordinates and real trade geography. Every person, organization, phone number, account, transaction, shipment, and document inside it is **100% synthetic**. No real individual or real company is represented. There is no scraping, no OSINT, and no surveillance functionality — this is an engineering demonstration of graph database design, graph analytics, and investigation-workflow tooling.

South Asia is the heaviest-weighted region by design — it is the declared **area of interest**, not the whole world model. An analyst moves World → Region → Country → City → Entity → Relationship → Event → Case, and the application preserves that context across the graph, map, search and case surfaces.

`ARGUS_PLAN.md` in this repository is the original pre-build design proposal — architecture rationale and phase-by-phase reasoning, kept for historical context. **The `docs/` directory below is the current, maintained source of truth** for how the system actually works.

## What this is

An analyst-facing tool for exploring a connected dataset of people, organizations, accounts, devices, vehicles, and their relationships: search and profile any entity, explore the graph interactively, run graph algorithms (PageRank, community detection, cycle detection, ML-based anomaly detection) against the live data, manage investigations as cases with an evidence board, and review system-generated alerts. A Scenario Generator can inject new, realistic investigation storylines into the live graph on demand, using the same generation engine that built the world.

## Key capabilities

- **Command Center** — one workspace rather than a card grid: a situation statement in prose before any figure, a regional strip that *filters* the queue beside it, and a master-detail lead panel that answers "why am I seeing this" from the scorer's own recorded factors, the alerts and cases already referencing the entity, and its real connections.
- **Graph Explorer** — Cytoscape.js canvas over the live Neo4j graph. Opens on a risk-led overview rather than the whole graph; entity type and risk are encoded as independent channels (fill vs. border ring); labels are gated by zoom and importance; focus mode isolates a neighborhood; clicking an edge explains *why* two entities are connected. Plus neighborhood expansion, shortest-path finding, and multiple layouts.
- **Analytics Engine** — PageRank, Betweenness, Louvain communities, Node2Vec similarity, custom risk propagation, and cycle detection via Neo4j Graph Data Science; plus Isolation Forest + z-score transaction-anomaly detection that independently rediscovers injected anomalies without reading their ground-truth labels.
- **Cases & Alerts** — alerts are a triage workspace where the queue selects and the detail argues: what happened, why it matters, what is affected, where it spreads (distinct countries and regions across the involved entities), and which other alerts share its storyline. A case opens with its footprint — reach across countries and regions, plus the alerts involving anything on its evidence board.
- **Provenance & confidence** — every displayed value resolves to the source that reported it, or is explicitly marked *inferred*, *modified* or *unattributed*. Sources carry Admiralty reliability (A–F) and claims carry credibility (1–6), kept as two independent readings and never averaged into one figure. Contradictory claims render side by side with no automatic winner, and "what did ARGUS believe on date D" is answerable. The synthetic data generator is itself a registered source, flagged as such, so generated ground truth can never be mistaken for discovered intelligence.
- **Local Intelligence Layer** — deterministic, template-composed entity/case narratives (no model, no network call), plus an entirely optional local-LLM assistant that the rest of the product has zero dependency on.
- **Scenario Generator** — creates a new synthetic investigation storyline on demand by running the real generation engine as a background job against the live graph.
- **Map** — a global geospatial workspace (MapLibre + deck.gl) with three scale tiers that swap datasets rather than restyle one: regions and trade corridors at world zoom, country aggregates at regional zoom, individual entities and shipment routes locally. Routes and the ranked context panel scope to the visible extent, so drilling in actually narrows what you see. Clicking a flagged route explains *why* it was flagged.
- **Timeline** — a temporal investigation workspace: daily volume with burst detection (days above 2σ of flagged volume), time-range and per-lane filters, and a ranked panel of what actually happened inside the current selection.

See [docs/analytics.md](docs/analytics.md) and [docs/ai-layer.md](docs/ai-layer.md) for how these actually work.

## Architecture at a glance

```mermaid
flowchart LR
    FE["Next.js 16 frontend"] -- "REST, httpOnly session cookie + CSRF" --> BE["FastAPI backend"]
    BE -- "Bolt" --> Neo4j[(Neo4j 5 + GDS)]
    BE -- "job status" --> Redis[(Redis)]
    BE -- "identity, audit, provenance" --> PG[(PostgreSQL 16)]
    Gen["generator/ (Python)"] -- "Bolt, direct write" --> Neo4j
    BE -- "subprocess" --> Gen
    BE -. "optional, probed at runtime" .-> Ollama["local Ollama"]
```

No hosted AI dependency anywhere in ARGUS Core — every "intelligence" feature is a graph algorithm, a classical ML model trained fresh on ARGUS's own synthetic data, or a deterministic template composer. The one optional LLM surface talks only to a local Ollama instance you run yourself. Full rationale: [docs/architecture.md](docs/architecture.md#local-first--no-hosted-ai-dependency).

## Technology stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16 (App Router), TypeScript, vanilla CSS Modules, Cytoscape.js, MapLibre GL + deck.gl, @visx/Recharts, TanStack Query, Zustand, Framer Motion |
| Backend | FastAPI (Python 3.12), async Neo4j driver, async Redis client |
| Database | Neo4j 5 Community Edition + Graph Data Science (GDS) plugin, self-hosted via Docker |
| Identity & provenance | PostgreSQL 16 — users, sessions, the append-only audit log, and the observation/assertion store |
| Auth | Argon2id password hashing, TOTP MFA, httpOnly session cookies, CSRF double-submit, six-role RBAC |
| Data generation | Python + Faker (per-region locales), deterministic/seeded |
| Intelligence | Neo4j GDS algorithms, scikit-learn (Isolation Forest), deterministic template NLG; optional local LLM via Ollama |

## Repository layout

```
argus/
├── ARGUS_PLAN.md       # Original design proposal — historical rationale
├── docs/                # Current technical documentation (start here)
├── docker-compose.yml   # Neo4j+GDS, Redis, PostgreSQL, backend
├── backend/             # FastAPI app
├── frontend/            # Next.js app
└── generator/           # Synthetic data generation engine (own venv)
```

## Running locally

```bash
cp .env.example .env

docker compose up -d neo4j redis postgres   # graph + cache + identity/provenance store

# 1. Generate the synthetic world.
cd generator
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export NEO4J_PASSWORD=argus_dev_password   # credentials come from the env, never argv
python3 generate_world.py --seed 42        # ~20K nodes, ~90K relationships, ~15s

# 2. Start the backend. Schema migrations for both databases run automatically
#    at startup, so there is nothing to apply by hand.
cd ../backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload   # or: docker compose up -d backend

# 3. Create the first account. Every endpoint requires authentication, so
#    without this there is nobody who can sign in and no way to fix that
#    through the product. You will be prompted for a password.
python3 -m app.cli create-user --username you --role administrator

#    An administrator manages users but deliberately cannot read intelligence,
#    so create an analyst to actually use the app:
python3 -m app.cli create-user --username analyst --role analyst

# 4. Attribute the generated world to the source that produced it. Optional but
#    recommended: without it, entity surfaces correctly report every value as
#    unattributed, because nothing yet records where it came from.
python3 -m app.cli backfill-provenance

cd ../frontend
npm install
npm run dev
```

- Frontend: http://localhost:3000 — sign in with the account from step 3
- Backend API docs: http://localhost:8000/docs
- Neo4j Browser: http://localhost:7474

> Roles are least-privilege and separated on purpose: an **administrator** manages users and cannot
> read intelligence, and an **auditor** reads the audit log and cannot change anything. If a page
> tells you your role cannot open it, that is the design rather than a fault — sign in as an analyst.

> Keep `generator/.venv` in place after initial world generation — the Scenario Generator (`/scenario` page) invokes it directly as a subprocess. See [docs/deployment.md](docs/deployment.md).

## Configuration

Every environment variable, its default, and what it affects is documented in [docs/deployment.md](docs/deployment.md#environment-variables). Copy `.env.example` to `.env` and adjust as needed; the defaults work out of the box for local development.

## Development workflow

- Backend: `ruff check .` / `mypy app` / `pytest` from `backend/` (dev extras: `pip install -e ".[dev]"`).
- Frontend: `npm run lint`, `npx tsc --noEmit`, `npm run build` from `frontend/`.
- `make lint` / `make typecheck` / `make test` run the equivalent checks from the repo root.
- GitHub Actions (`.github/workflows/ci.yml`) runs all of the above on every push and PR to `main`.
- Schema changes are numbered, forward-only migrations applied at startup — Neo4j in `backend/app/database/migrations/`, PostgreSQL in `backend/app/database/pg_migrations/`. They are deliberately not a side effect of running the generator, whose default path rewrites the graph.
- `python -m app.cli verify-audit` recomputes the audit hash chain; it is the check that makes the log tamper-*evident* rather than merely tamper-resistant.
- See [docs/backend.md](docs/backend.md#adding-a-new-endpoint) and [docs/generator.md](docs/generator.md) for where to add new endpoints or storyline types.

## What this is not

ARGUS is a portfolio engineering demonstration on synthetic data, and it is worth being precise about
the difference between that and an intelligence platform:

- **The risk score is not an assessment.** The generator assigns it from storyline membership — from
  its own answer key — and nothing recomputes it from evidence. The UI now says so wherever the
  number appears, marked *inferred* and rated F6 ("cannot be judged"), rather than letting it read as
  an analytic conclusion. Replacing it with a derived, calibrated, explainable score is planned work,
  not something already here.
- **Correlation is planted, not discovered.** Two alerts are "related" because they share a
  generator-written `storyline_id`, which would not exist in real data.
- **Single-instance, single-tenant.** Rate limiting is per-process, the job queue is in-process
  asyncio, and audit logs are stored locally rather than shipped off-host. See
  [docs/deployment.md](docs/deployment.md#what-would-need-to-change-for-a-real-multi-tenanthosted-deployment).

The provenance layer exists precisely so these limits are visible in the product rather than only in
this README.

## Documentation index

| Document | Covers |
|---|---|
| [docs/architecture.md](docs/architecture.md) | System boundaries, request/job flows, key design decisions |
| [docs/backend.md](docs/backend.md) | FastAPI structure, services, background jobs, DI |
| [docs/frontend.md](docs/frontend.md) | Next.js routes, hooks, state management, Graph/Map/Timeline internals |
| [docs/database.md](docs/database.md) | Neo4j labels, relationships, indexes, schema rationale |
| [docs/api.md](docs/api.md) | Every HTTP endpoint |
| [docs/generator.md](docs/generator.md) | World generation pipeline + on-demand scenario injection |
| [docs/analytics.md](docs/analytics.md) | Every graph algorithm, anomaly detection, case/alert workflow |
| [docs/ai-layer.md](docs/ai-layer.md) | Template narratives + the optional local-LLM assistant |
| [docs/deployment.md](docs/deployment.md) | Running locally, Docker, every environment variable |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Common failure modes and fixes |
| [ARGUS_PLAN.md](ARGUS_PLAN.md) | Original design proposal (historical) |

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `⌘K` / `Ctrl+K` | Open the command palette — filterable jump-to-any-page |
| `⌘J` / `Ctrl+J` | Open Ask ARGUS (only appears if a local Ollama instance is detected) |
| `Escape` | Close whichever overlay (command palette, modal) is open |

## Ethics note

ARGUS contains no real personal data, no scraped data, and no surveillance functionality of any kind. Every entity, relationship, shipment and event is procedurally generated and fictional. Real geography — city names, coordinates, country dialing codes, corporate legal forms, trade corridors — is used only to ground the synthetic world in plausible places, so that a generated dataset reads coherently to an analyst. No real individual or organization is represented, and nothing here describes real events.
