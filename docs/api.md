# API Reference

Scope: every HTTP endpoint the backend exposes. Base URL `http://localhost:8000` in local development. All responses are wrapped in the [Envelope shape](backend.md#response-envelope).

## Authentication

Every route except `/api/health`, `/livez`, `/readyz` and `POST /api/auth/login` requires an
authenticated session, **and** the permission its handler declares.

Authentication is a server-side session referenced by an **httpOnly cookie**. There is deliberately
no bearer token and no API key: the previous design put a single static token in
`NEXT_PUBLIC_ARGUS_API_TOKEN`, which Next.js inlines into the client bundle at build time — so the
credential guarding every endpoint was served as static text to anyone who loaded the page. It was
removed rather than rotated.

Because the credential is a cookie, the browser attaches it automatically to cross-site requests, so
**every unsafe method (POST/PUT/DELETE) also requires a CSRF token**: send the value of the
`argus_csrf` cookie in the `X-CSRF-Token` header. That cookie is readable by same-origin JavaScript
precisely so the SPA can echo it; an attacker's page can cause it to be *sent* but cannot read it.

```
POST /api/auth/login      {username, password, mfa_code?}  -> sets argus_session + argus_csrf
GET  /api/auth/me                                          -> current user, role and permissions
POST /api/auth/logout                                      -> revokes the session server-side
```

Roles and permissions are enumerated in `app/security/roles.py`. Two separations are deliberate: an
**administrator** holds no intelligence-read permission, and an **auditor** holds no write permission
of any kind — so a single compromised account cannot both act and erase the evidence of acting.

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
| GET | `/api/entities` | `type` (default `Person`), `risk_min` (default 0), `city`, `page`, `page_size` | Paginated, risk-sorted list. `type` must be one of `Person`, `Organization`, `Location`, `Vehicle`, `Device` (`graph_repo.BROWSABLE_LABELS`); anything else is a **400**. It previously fell back to `Person` for unrecognised values, which returned people labelled as the requested type. `risk_min` applies to **every** label — it was previously restricted to Person/Organization, so browsing any other type with a threshold returned a full unfiltered page presented as matching the filter. `city` applies to Person, Organization and Location, the labels that carry the property.  |
| GET | `/api/entities/{entity_id}` | — | Full node by human ID (any type), plus a `connections` map (`{label: count}`). 404 if not found. |
| GET | `/api/entities/{entity_id}/graph` | `depth` (default 1) | Subgraph = the entity plus its `depth`-hop neighborhood. |
| GET | `/api/entities/{entity_id}/timeline` | — | Person/Organization activity feed (events, transactions, communications), newest first. |
| GET | `/api/entities/{entity_id}/cases` | — | Cases this entity is linked to (reverses `Case-[:LINKED_TO]->Entity`), newest-opened first. |
| GET | `/api/entities/{entity_id}/alerts` | `limit` (default 20) | Alerts (High/Critical Incidents) this entity is involved in (reverses `Incident-[:INVOLVES]->Entity`), newest first. |
| GET | `/api/entities/{entity_id}/provenance` | — | Per-attribute provenance: for each property, the observations that reported it, any assertions about it, and whether the stored value still matches what the source said. Also returns `observations_examined` / `observations_total`, so a bounded read can never be mistaken for a complete one. |

## Provenance — `app/api/routes/provenance.py`

Requires `provenance:read`, which every intelligence-reading role holds — knowing that a figure came
from a synthetic source rated F is part of reading the figure.

| Method | Path | Params | Description |
|---|---|---|---|
| GET | `/api/provenance/sources` | — | The source registry: type, Admiralty reliability, the stated basis for that rating, independence group, and `is_synthetic`. |
| GET | `/api/provenance/summary` | — | Row counts and which registered sources are synthetic. Drives the "synthetic data" notice, so it disappears on its own when real sources replace generated ones. |
| GET | `/api/provenance/subjects/{ref}` | `as_of`, `include_ended`, `observation_limit` | Observations, assertions, conflicts and sources for one entity. **`as_of` reconstructs what ARGUS believed at that instant** — filtering on when ARGUS learned or asserted something, not on when it happened. |
| GET | `/api/provenance/subjects/{ref}/conflicts` | `as_of` | Predicates where current assertions disagree. Returns **every side, with no winner** — resolving a conflict is an analyst's job, and a system that quietly picks one hides the disagreement from the only person qualified to settle it. |
| GET | `/api/provenance/observations/{id}` | — | One observation: payload, content hash, source, and its three timestamps. |
| GET | `/api/provenance/assertions/{id}` | — | One assertion with its supporting *and* contradicting evidence, plus corroboration counted over independent source groups. |
| POST | `/api/provenance/assertions` | `{subject_ref, predicate, object_value, epistemic_kind, reliability, credibility, note?, supporting_observation_ids?, contradicting_observation_ids?, supersedes?}` | Record a judgement, attributed to you. Requires `assertion:write`. `epistemic_kind` accepts only `assessed` or `reported`: `observed` belongs to a system of record and `inferred` to an algorithm that names its method, so neither can be claimed by hand (**400**). |
| POST | `/api/provenance/assertions/{id}/retract` | `{reason}` | Withdraw a belief. Requires `assertion:retract`. The reason is mandatory, the assertion is not deleted, and the retraction cannot be reversed (**409** if already retracted). |

Reliability (`A`–`F`) and credibility (`1`–`6`) are the two axes of the Admiralty Code and are
returned as separate fields everywhere. Nothing in the API combines them into a single confidence
number — "0.62" cannot tell an analyst whether the basis is one excellent source or four poor ones.

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
| GET | `/api/dashboard/summary` | Aggregate counts (persons, orgs, transactions, flagged entities, active cases, open alerts, avg risk), risk-band distribution, 6 most recent incidents and cases. Risk bands are half-open `[low, high)` except the top band, which is inclusive of 100 — storyline-injected entities score exactly 100.0, and an exclusive upper bound previously dropped them from the distribution entirely (reported `Critical: 0` alongside 4 flagged entities). |

## Search — `app/api/routes/search.py`

| Method | Path | Params | Description |
|---|---|---|---|
| GET | `/api/search` | `q`, `limit` (default 20) | Fuzzy full-text search over Person/Organization/Location/Vehicle names (Neo4j `entity_name` fulltext index, `~` fuzzy match). |

## Map — `app/api/routes/map.py`

| Method | Path | Params | Description |
|---|---|---|---|
| GET | `/api/map/entities` | `type` (`Person`\|`Organization`, optional) | Every geo-located Person/Organization (`lat`/`lng` not null). |
| GET | `/api/map/shipments` | — | Shipment routes with resolved origin/destination/via coordinates, trade lane, anomaly kind, detour ratio, distance and manifest. `via` is set only on `circuitous` routes, so it is an OPTIONAL MATCH — a plain MATCH would drop every normal shipment. |
| GET | `/api/map/regions` | — | Per-region aggregates (entity/org/country counts, avg risk, elevated count, anomalous routes) plus map centre and zoom. Backs the map's world tier and the dashboard's Global posture panel. |
| GET | `/api/map/countries` | `region` (optional) | Per-country aggregates, optionally scoped to one region. Backs the map's regional tier. |
| GET | `/api/map/corridors` | — | Region-to-region trade corridors aggregated from actual shipments, with shipment count and anomaly share. Direction is collapsed — the question at world scale is how much moves between two regions, not which way. |

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
| 401 | No session cookie, or the session has expired or been revoked |
| 403 | Authenticated but the role lacks the permission the route requires; or a missing/invalid `X-CSRF-Token` on an unsafe method |
| 404 | Entity, case, alert, observation or assertion not found by ID |
| 400 | Invalid scenario `type`/`complexity`; unrecognised entity ID; an epistemic kind a person may not claim |
| 409 | Assertion already retracted |
| 422 | Request body fails validation (bad Admiralty rating, oversized field, missing reason) |
| 429 | Rate limit exceeded, or the job concurrency limit is saturated (`Retry-After` set) |
| 503 | A datastore is unreachable — Neo4j, Redis or PostgreSQL — or `/api/ai/ask` called while Ollama is down. Always with `Retry-After`, because the request was well-formed and should be retried rather than treated as a defect. |
| 500 | Unhandled exception — surfaces as FastAPI's default error response |
