# ARGUS

A privacy-first synthetic intelligence platform — a graph-native investigation and analytics simulator built entirely on procedurally generated data.

ARGUS is set in **real Indian geography** (real cities, states, coordinates), but every person, organization, phone number, account, transaction, and document inside it is **100% synthetic**. No real individual or real company is represented. There is no scraping, no OSINT, and no surveillance functionality — this is an educational engineering demonstration of graph analytics, investigation workflow design, and connected data visualization.

See [`ARGUS_PLAN.md`](./ARGUS_PLAN.md) for the full product architecture, data model, and technology decisions (including the `[v2/v3 REVISION]` notes documenting changes from the original plan).

## Features

- **Dashboard** — live risk distribution, recent incidents/cases, headline stats
- **Graph Explorer** — Cytoscape.js canvas over the live Neo4j graph, shortest-path, neighborhood expansion
- **Search** — full-text entity search with type/risk facets
- **Map** — MapLibre + deck.gl over real India geography: entity locations, shipment routes
- **Timeline** — flagged activity vs. an evenly-sampled baseline across the 180-day world window
- **Analytics Engine** — PageRank, Betweenness, Louvain communities, Node2Vec similarity, custom risk propagation, and cycle detection, all backed by Neo4j GDS running as async background jobs; plus Isolation Forest + z-score transaction-anomaly detection (scikit-learn) that independently rediscovers injected storylines without reading their ground-truth labels
- **Cases & Alerts** — investigation workspace with an evidence board, notes, and an alert review queue over the same Incident data
- **Local Intelligence Layer** — deterministic template-composed entity/case narratives (no LLM), plus an entirely optional local-LLM "Ask ARGUS" panel (via Ollama) that the rest of the app has zero dependency on
- **Scenario Generator** — creates a new, real synthetic investigation storyline on demand by running the actual generation engine as a background job against the live graph, not a canned demo

## Stack

- **Frontend** — Next.js 16 (App Router), TypeScript, vanilla CSS design system, Cytoscape.js, MapLibre GL + deck.gl, Recharts/VisX, TanStack Query, Zustand, Framer Motion
- **Backend** — FastAPI (Python), async Neo4j driver, Redis-backed async job status
- **Database** — Neo4j Community Edition + Graph Data Science (GDS) plugin, self-hosted via Docker
- **Data Generation** — Python + Faker (`en_IN` locale), deterministic and seeded — ~20K nodes / ~90K relationships at default scale
- **Intelligence** — Neo4j GDS algorithms, scikit-learn (Isolation Forest), deterministic template NLG — all local, all run on ARGUS's own synthetic data. An optional local LLM (Ollama) is the *only* AI dependency anywhere in the product, and it's off by default: every other feature works with it absent (see `ARGUS_PLAN.md` Phase 10)

## Running locally

This project is **local-first** — everything runs via Docker Compose plus the Next.js dev server. There is no live hosted deployment yet (a deliberate choice; see Phase 11 of the plan).

```bash
cp .env.example .env

docker compose up -d neo4j redis   # graph database (with GDS) + cache

cd generator
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 generate_world.py --seed 42   # populates the graph (~20K nodes, ~90K relationships, ~15s)

cd ../backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload   # or: docker compose up -d backend

cd ../frontend
npm install
npm run dev
```

- Frontend: http://localhost:3000
- Backend API docs: http://localhost:8000/docs
- Neo4j Browser: http://localhost:7474

> The Scenario Generator page (`/scenario`) runs `generator/generate_scenario.py` as a
> subprocess using `generator/.venv` directly — keep that virtualenv in place (the
> `python3 -m venv .venv` step above) even after the initial world generation is done.

## Repository layout

```
argus/
├── ARGUS_PLAN.md      # Full architecture, data model, and roadmap
├── docker-compose.yml # Neo4j+GDS, Redis, backend
├── frontend/          # Next.js app
├── backend/           # FastAPI app
└── generator/         # Synthetic data generation engine
```
