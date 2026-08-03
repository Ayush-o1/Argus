# API Reference

Scope: every HTTP endpoint the backend exposes. Base URL `http://localhost:8000` in local development. All routes except `GET /api/health` require `Authorization: Bearer <ARGUS_API_TOKEN>` (see [deployment.md](deployment.md#environment-variables)). All responses are wrapped in the [Envelope shape](backend.md#response-envelope).

Interactive docs (Swagger UI, generated from the same FastAPI app) are available at `http://localhost:8000/docs` whenever the backend is running — this file is the narrative companion, not a replacement.

## Envelope shape

```json
{ "data": { /* endpoint-specific */ }, "meta": { "total": 0, "page": 1, "page_size": 50 } | null, "error": null }
```

`meta` is present only on paginated list endpoints.

## Health

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/health` | none | `{status: ok\|degraded, neo4j: bool, redis: bool}` — actively probes both datastores. |

## Entities — `app/api/routes/entities.py`

| Method | Path | Params | Description |
|---|---|---|---|
| GET | `/api/entities` | `type` (default `Person`), `risk_min` (default 0), `city`, `page`, `page_size` | Paginated, risk-sorted list of Person/Organization/Vehicle/Device. |
| GET | `/api/entities/{entity_id}` | — | Full node by human ID (any type), plus a `connections` map (`{label: count}`). 404 if not found. |
| GET | `/api/entities/{entity_id}/graph` | `depth` (default 1) | Subgraph = the entity plus its `depth`-hop neighborhood. |
| GET | `/api/entities/{entity_id}/timeline` | — | Person/Organization activity feed (events, transactions, communications), newest first. |

## Graph — `app/api/routes/graph.py`

| Method | Path | Params | Description |
|---|---|---|---|
| GET | `/api/graph/subgraph` | `entity_id`, `depth` | Same as the entity graph endpoint, entity-agnostic entry point. |
| GET | `/api/graph/overview` | — | Default Graph Explorer view: the 25 highest-risk Person/Organization nodes and their immediate neighbors. |
| GET | `/api/graph/shortest-path` | `from_id`, `to_id` | Shortest path (≤8 hops) between any two entities, or `null` if none exists. |
| GET | `/api/graph/neighbors` | `entity_id`, `depth` | Alias of the subgraph endpoint. |

## Dashboard — `app/api/routes/dashboard.py`

| Method | Path | Description |
|---|---|---|
| GET | `/api/dashboard/summary` | Aggregate counts (persons, orgs, transactions, flagged entities, active cases, open alerts, avg risk), risk-band distribution, 6 most recent incidents and cases. |

## Search — `app/api/routes/search.py`

| Method | Path | Params | Description |
|---|---|---|---|
| GET | `/api/search` | `q`, `limit` (default 20) | Fuzzy full-text search over Person/Organization/Location/Vehicle names (Neo4j `entity_name` fulltext index, `~` fuzzy match). |

## Map — `app/api/routes/map.py`

| Method | Path | Params | Description |
|---|---|---|---|
| GET | `/api/map/entities` | `type` (`Person`\|`Organization`, optional) | Every geo-located Person/Organization (`lat`/`lng` not null). |
| GET | `/api/map/shipments` | — | Shipment routes with resolved origin/destination coordinates and names. |

## Timeline — `app/api/routes/timeline.py`

| Method | Path | Description |
|---|---|---|
| GET | `/api/timeline/events` | Global activity: flagged transactions/communications + a random baseline sample (300 each) + all events (random sample) + all incidents. See [database.md](database.md) for why this is sampled rather than exhaustive. |

## Cases — `app/api/routes/cases.py`

| Method | Path | Body | Description |
|---|---|---|---|
| GET | `/api/cases` | — (`status`, `page`, `page_size` query) | Paginated case list. |
| POST | `/api/cases` | `{title, priority?, notes?}` | Creates a `Draft` case with an auto-incrementing `CASE-NNNN` ID. |
| GET | `/api/cases/{case_id}` | — | Case detail + `linked_entities` (evidence board). 404 if missing. |
| PUT | `/api/cases/{case_id}` | `{status?, priority?, notes?, assigned_analyst?}` | Partial update — only non-null fields are applied. |
| POST | `/api/cases/{case_id}/entities` | `{entity_id, reason?}` | Links an entity to the case's evidence board (`MERGE ... LINKED_TO`). |
| DELETE | `/api/cases/{case_id}/entities/{entity_id}` | — | Unlinks an entity. |

## Alerts — `app/api/routes/alerts.py`

Alerts are High/Critical-severity `Incident` nodes — there is no separate Alert entity. See [analytics.md](analytics.md#alerts).

| Method | Path | Params / Body | Description |
|---|---|---|---|
| GET | `/api/alerts` | `status`, `priority` (severity), `page`, `page_size` | Paginated alert queue, each with up to 5 involved entities. |
| PUT | `/api/alerts/{alert_id}/review` | `{status: Open\|UnderInvestigation\|Closed}` | Analyst review action. |

## Analytics — `app/api/routes/analytics.py`

All `POST` routes here return `{job_id, status: "running"}` immediately — see [analytics.md](analytics.md) for what each algorithm computes, and [backend.md#background-jobs](backend.md#background-jobs) for the polling contract.

| Method | Path | Body | Result shape |
|---|---|---|---|
| POST | `/api/analytics/pagerank` | — | Ranked list `{id, name, label, account_id, score}` |
| POST | `/api/analytics/betweenness` | — | Same shape as PageRank |
| POST | `/api/analytics/louvain` | — | `{communities: [{community_id, size, avg_risk_score, top_entity}], total_communities}` |
| POST | `/api/analytics/similar/{entity_id}` | `top_k` query (default 10) | Ranked list `{id, name, label, similarity}` |
| POST | `/api/analytics/risk-propagation` | `{seed_ids: string[], max_hops?: 3}` | `{seeds: [...], propagated: [{id, name, label, propagated_risk}]}` |
| POST | `/api/analytics/cycle-detection` | — | List of `{length, total_amount, members: [{account_id, name, label, id}]}` |
| POST | `/api/analytics/anomalies` | — | List of `{id, name, label, account_id, tx_count, total_amount, max_burst_count, burst_window_hours, burst_baseline_mean, burst_baseline_std, z_score}` |
| GET | `/api/analytics/results/{job_id}` | — | `{job_type, status: running\|done\|failed, result, error}` |

## AI — `app/api/routes/ai.py`

See [ai-layer.md](ai-layer.md) for the full design of every endpoint here.

| Method | Path | Body | Description |
|---|---|---|---|
| POST | `/api/ai/entity-summary/{entity_id}` | — | Deterministic template narrative (no network call). `{summary: string}` |
| POST | `/api/ai/case-summary/{case_id}` | — | Same, for a case. |
| GET | `/api/ai/assistant-status` | — | `{available: bool}` — probes local Ollama at `settings.ollama_base_url`. |
| POST | `/api/ai/ask` | `{question: string}` | 503 if Ollama unreachable; otherwise `{answer: string}` grounded in dashboard-summary context. |

## Scenario — `app/api/routes/scenario.py`

See [generator.md](generator.md#on-demand-scenario-generation) for what runs underneath.

| Method | Path | Body | Description |
|---|---|---|---|
| GET | `/api/scenario/types` | — | `{types: string[], complexities: ["Low","Medium","High"]}` |
| POST | `/api/scenario/generate` | `{type, complexity?: "Medium", seed?: int}` | 400 if `type`/`complexity` invalid. Returns `{job_id, status: "running"}`. |
| GET | `/api/scenario/status/{job_id}` | — | `{status, result: {storyline_id, type, severity, description, case_id, key_entity_id, key_entity_name, node_counts, seed, stages}, error, stages}` |

## Error responses

| Status | When |
|---|---|
| 401 | Missing/incorrect bearer token on any authenticated route |
| 404 | Entity, case, or alert not found by ID |
| 400 | Invalid scenario `type`/`complexity` |
| 503 | `/api/ai/ask` called while Ollama is unreachable |
| 500 | Unhandled exception — surfaces as FastAPI's default error response |
