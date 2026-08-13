# Troubleshooting

Scope: symptoms you'll actually hit running ARGUS locally, and the specific fix. For normal setup steps, see [deployment.md](deployment.md).

## Backend won't start / `RuntimeError: Neo4j driver not initialized`

The backend's `lifespan` calls `connect_neo4j()` and `connect_redis()` at startup, each of which calls `verify_connectivity()`/`ping()` — if either datastore is unreachable, startup fails outright (by design; there's no degraded-startup mode). Confirm both containers are actually healthy, not just running:

```bash
docker compose ps
docker compose logs neo4j
docker compose logs redis
```

`GET /api/health` (the one unauthenticated route) reports which datastore is failing once the process *is* up: `{"status": "degraded", "neo4j": false, "redis": true}`.

## Neo4j takes a long time to become healthy

The `neo4j` service's healthcheck has a 30s `start_period` and polls every 10s — GDS plugin installation adds real startup time on first container creation. Don't run `generate_world.py` until `docker compose ps` shows `neo4j` as `healthy`, not just `running`; connecting before the plugin has finished loading produces confusing GDS procedure errors rather than a clean connection refusal.

## `gds.pageRank.stream` / any GDS procedure "not found" or "unauthorized"

The `graph-data-science` plugin must be both installed (`NEO4J_PLUGINS` in `docker-compose.yml`) and allowlisted (`NEO4J_dbms_security_procedures_unrestricted`/`_allowlist: gds.*`) — Neo4j sandboxes GDS's procedures by default. If you're running Neo4j outside the provided `docker-compose.yml` (a bare install, a different container), you must replicate both settings yourself, not just install the plugin jar.

## `401 Unauthorized` on every API call

`ARGUS_API_TOKEN` (backend) and `NEXT_PUBLIC_ARGUS_API_TOKEN` (frontend) must match exactly — they're two separate environment variables, one per process, and nothing enforces they stay in sync. If you changed one in `.env` without restarting the corresponding process (`NEXT_PUBLIC_*` values are baked in at Next.js build/dev-server start), restart it.

## Scenario Generator fails immediately / `generate_scenario.py` not found

`app/services/scenario.py` hardcodes `GENERATOR_PYTHON = generator/.venv/bin/python3` — an exact path, not "whatever Python is on PATH." If you deleted or never created `generator/.venv`, or created it with a different tool that names the interpreter differently, the subprocess exec fails. Fix: `cd generator && python3 -m venv .venv && pip install -r requirements.txt` and leave that virtualenv in place permanently — see [generator.md](generator.md#running-the-generator-standalone).

## Scenario Generator fails with "Not enough existing low-risk persons" or "Not enough existing locations"

`build_scenario` fetches existing `Person` nodes with `risk_score < 40` (and, for `supply_chain_divergence`, existing `Location` nodes) directly from the live graph to reuse as scenario participants — it never creates new persons. If you've run many high-complexity scenarios in a row, or seeded a very small world, the pool of low-risk persons can run out. Fix: regenerate the base world (`generate_world.py --seed 42`) to reset the pool, or lower scenario complexity.

## Map basemap doesn't render / MapLibre canvas stays blank

Two independent causes have been confirmed in this stack, and both matter:

1. **`maplibre-gl` version** — must stay on `^3.6.2` (see `frontend/package.json`). Newer major versions break deck.gl's shared WebGL context; if you bump this dependency, verify the map still renders before assuming it's a code regression elsewhere.
2. **Headless/CI browser environments** — a headless Chromium instance used for automated screenshot testing needs software WebGL explicitly enabled (Chromium's `--enable-unsafe-swiftshader` launch flag) or the canvas silently fails to initialize. This is a browser-launch-configuration issue in a test harness, not an application bug — a real user's browser with normal GPU/software rendering doesn't need this flag.

## Timeline page looks empty despite data existing

`GET /api/timeline/events` deliberately samples rather than returning everything: 500 flagged transactions/communications plus a 300-item random baseline, all events randomly sampled, but **not** the full ~60K generated events/transactions/communications. If you're checking for a specific transaction and it's not flagged, it may simply not be in this run's random baseline sample — look it up directly via the entity's own timeline (`/entities/{id}` → Activity tab) instead, which is exhaustive for that one entity.

## `next dev` console error: "Cannot read properties of null (reading 'notify')" on `/graph`

A known, non-blocking, **dev-mode-only** artifact from React StrictMode's mount/unmount/remount cycle interacting with Cytoscape.js's internal event system during rapid client-side navigation. Confirmed absent in a production build (`next build && next start`). If you see this in `npm run dev`, it is not a regression to chase — verify against a production build before treating it as a real bug.

## Map renders without a basemap

Symptom: the Map page shows entity points and route arcs floating on an empty background, and the network panel reports `net::ERR_ABORTED` for `basemaps.cartocdn.com/.../style.json`.

The aborted request is usually a red herring. React StrictMode mounts, tears down, and remounts the effect that constructs the MapLibre `Map`, and the discarded first instance's in-flight style fetch is cancelled — that abort is expected and harmless, because the surviving instance issues its own fetch which succeeds.

**Do not add a retry or a `setStyle()` guard for this.** A previous attempt to "fix" the abort by re-issuing `setStyle()` on a timer raced with the already-succeeding load and was itself the cause of intermittent blank basemaps; removing it made the map load reliably. If the basemap genuinely fails, verify outbound network access to `basemaps.cartocdn.com` first (`curl -I https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json`) before touching `ArgusMap.tsx`.

## Ollama / "Ask ARGUS" panel never appears

This is expected, not a bug, if you haven't installed Ollama. The panel (`⌘J`) only renders when `GET /api/ai/assistant-status` reports `available: true`, which requires a local Ollama process reachable at `OLLAMA_BASE_URL` (default `http://localhost:11434`). Install Ollama, `ollama pull llama3.2:3b` (the model `app/services/ollama.py` requests by name), and confirm `curl http://localhost:11434/api/tags` succeeds. Every other ARGUS feature works identically with Ollama absent — see [ai-layer.md](ai-layer.md).

## Python version / dependency conflicts

Backend requires Python ≥3.12 (`backend/pyproject.toml`). The generator has no explicit minimum but is tested against the same interpreter. Keep the backend's and generator's virtualenvs **separate** (`backend/.venv` and `generator/.venv`) — they intentionally have non-overlapping dependency sets (see [architecture.md](architecture.md#why-three-separate-deployables-instead-of-one)); installing one project's dependencies into the other's virtualenv is not supported and not necessary.

## Frontend build/type errors after a Next.js or dependency bump

Read `frontend/AGENTS.md` before assuming a Next.js API works the way you remember — this project pins Next.js 16, which has breaking changes from earlier majors most training data and cached knowledge assumes.

## General performance notes

Query- and render-level limits are intentional, fixed guardrails for a single-machine deployment, not bugs to work around:

| Limit | Value | Where |
|---|---|---|
| Graph Explorer neighborhood size | 500 nodes | `graph_repo.py::MAX_NEIGHBORHOOD_NODES` |
| Shortest path hop bound | 8 hops | `graph_repo.py::shortest_path` |
| Cycle detection path length | 3–6 hops, 25 results | `analytics_repo.py::run_cycle_detection` |
| Timeline flagged-activity limit | 500 items | `timeline_repo.py::get_global_timeline` |
| Timeline baseline sample | 300 items | same |
| Analytics job poll interval | 1.2s | `frontend/src/hooks/useAnalytics.ts` |
| Scenario job poll interval | 0.9s | `frontend/src/hooks/useScenario.ts` |

If you scale the generator well beyond its defaults (see [generator.md](generator.md#scale-configuration)), revisit Neo4j's heap/page-cache settings in `docker-compose.yml` before assuming a slow query is a code bug.
