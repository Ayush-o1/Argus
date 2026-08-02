# ARGUS

A synthetic intelligence analysis platform — a graph-native investigation and analytics simulator built entirely on procedurally generated data.

ARGUS is set in **real Indian geography** (real cities, states, coordinates), but every person, organization, phone number, account, transaction, and document inside it is **100% synthetic**. No real individual or real company is represented. There is no scraping, no OSINT, and no surveillance functionality — this is an educational engineering demonstration of graph analytics, investigation workflow design, and connected data visualization.

See [`ARGUS_PLAN.md`](./ARGUS_PLAN.md) for the full product architecture, data model, and technology decisions (including the `[v2 REVISION]` notes documenting changes from the original plan).

## Stack

- **Frontend** — Next.js 16 (App Router), TypeScript, vanilla CSS design system, Cytoscape.js, MapLibre GL + deck.gl, Recharts/VisX, TanStack Query, Zustand, Framer Motion
- **Backend** — FastAPI (Python), async Neo4j driver, Redis
- **Database** — Neo4j Community Edition + Graph Data Science (GDS) plugin, self-hosted via Docker
- **AI** — Google Gemini API (server-side only)

## Running locally

This project is **local-first** — everything runs via Docker Compose plus the Next.js dev server. There is no live hosted deployment yet (a deliberate choice; see Phase 11 of the plan).

```bash
cp .env.example .env          # fill in GEMINI_API_KEY if you want AI features

docker compose up -d neo4j redis   # graph database (with GDS) + cache
docker compose up -d backend       # or: cd backend && uvicorn app.main:app --reload

cd frontend
npm install
npm run dev
```

- Frontend: http://localhost:3000
- Backend API docs: http://localhost:8000/docs
- Neo4j Browser: http://localhost:7474

## Repository layout

```
argus/
├── ARGUS_PLAN.md      # Full architecture, data model, and roadmap
├── docker-compose.yml # Neo4j+GDS, Redis, backend
├── frontend/          # Next.js app
├── backend/           # FastAPI app
└── generator/         # Synthetic data generation engine
```
