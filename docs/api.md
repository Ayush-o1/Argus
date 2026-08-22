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
| GET | `/api/entities/{entity_id}/alerts` | `limit` (default 20) | Source-reported incidents naming this entity. These are `Incident` nodes, which in this world the generator writes — they are not ARGUS's alerts. For those, use `/api/alerts?subject_ref=…`. |
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
| GET | `/api/dashboard/summary` | Aggregate counts (persons, orgs, transactions, elevated entities, active cases, open alerts and high-priority open alerts — both from the alerting tables, not from `Incident`), assessment-band distribution, 6 most recent incidents and cases. Risk bands are half-open `[low, high)` except the top band, which is inclusive of 100 — storyline-injected entities score exactly 100.0, and an exclusive upper bound previously dropped them from the distribution entirely (reported `Critical: 0` alongside 4 flagged entities). |

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

An alert is raised by a named, versioned **rule** evaluated over ARGUS's own
assessments and correlations, and persisted in PostgreSQL. It is not a view over
`Incident`: those nodes are written by the scenario generator, one per
storyline, so the previous endpoint re-read the answer key and presented it as a
queue. Nothing generated an alert, nothing deduplicated, and "review" was an
unvalidated status write that left no record of who made it.

Identity is `(rule_id, rule_version, sorted scope)`, so a re-run over an
unchanged world increments an occurrence count rather than inserting a row.
Alerts are mutable (they are work items); occurrences and transitions are
append-only by trigger.

| Method | Path | Params / Body | Description |
|---|---|---|---|
| GET | `/api/alerts` | `state`, `suppressed`, `include_suppressed`, `group_key`, `subject_ref`, `page`, `page_size` | Paginated queue. Excludes suppressed and closed alerts by default. |
| GET | `/api/alerts/model` | — | The rule set: each rule's meaning, what would make it wrong, what it reads, the state machine, the dismissal vocabulary, and the rules fingerprint. |
| GET | `/api/alerts/summary` | — | Queue counts by state, group total, latest run. |
| GET | `/api/alerts/groups` | `limit` | One row per story. A group is a correlated cluster ARGUS published, largest first. |
| GET | `/api/alerts/suppressions` | `active_only` | Active or all suppressions, each naming who set it and why. |
| GET | `/api/alerts/evaluation` | — | Latest precision/recall against ground truth the rules never saw. |
| GET | `/api/alerts/runs` | `limit` | Rule-engine runs, with firing and dedup counts. |
| GET | `/api/alerts/{alert_key}` | — | One alert with its full occurrence and transition history. |
| POST | `/api/alerts/{alert_key}/transition` | `{to_state, reason_code?, note?}` | Move through the lifecycle. `409` for an illegal move, naming what *is* reachable; `409` for a dismissal without a vocabulary reason; `409` if another analyst moved it first. Requires `alert:triage`. |
| POST | `/api/alerts/{alert_key}/assign` | `{assignee}` | Assign or unassign. Requires `alert:triage`. |
| POST | `/api/alerts/suppressions` | `{rule_id?, subject_ref?, reason_code, note, expires_at}` | Hide matching alerts from the default queue. `422` for a wildcard, an expiry beyond 90 days, or a note under a sentence. Requires `alert:suppress`. |
| DELETE | `/api/alerts/suppressions/{id}` | — | Revoke. Requires `alert:suppress`. |
| POST | `/api/alerts/run` | — | Queue a rule-engine run. Requires `alert:run`. |

**Suppression hides; it never silences.** A suppressed alert is still raised,
counted, grouped, and named with the suppression that hid it — it is excluded
from the default filter and is one query parameter away.

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

## Ingestion — `app/api/routes/ingest.py`

Requires `ingest:read`, held by every intelligence-reading role **and** by
administrators. Whether a source has gone quiet changes how its silence should be
read, so pipeline health travels with the intelligence it feeds.

| Method | Path | Params | Description |
|---|---|---|---|
| GET | `/api/ingest/health` | — | Per-connector freshness, 24h volume, rejection rate and dead-letter depth, plus queue depth and which sources are overdue against their own declared interval. Computed from `ingest_batches` rather than from counters, so the figures cannot drift from the events they describe. |
| GET | `/api/ingest/connectors` | — | Configured connectors. `config` is redacted of anything credential-shaped before it leaves the process. |
| GET | `/api/ingest/connectors/{id}/batches` | `limit` | Recent fetch attempts with per-batch counts. |
| GET | `/api/ingest/connectors/{id}/fields` | — | Every field this source has ever sent, first and last seen. A field that stops arriving is a schema change nothing else reports. |
| PUT | `/api/ingest/connectors` | `{connector_id, source_id, connector_type, display_name, config, mapping, poll_interval_seconds?, enabled?}` | Register or update a connector. Requires `ingest:manage`. **400** if the type is unregistered, the mapping is invalid, or `config` contains anything credential-shaped — name an environment variable instead (`token_env`). |
| POST | `/api/ingest/connectors/{id}/run` | — | Queue an immediate run; returns a job id, not a result. Requires `ingest:manage`. |
| POST | `/api/ingest/connectors/{id}/quarantine` | `{reason}` | Stop a connector, with a stated reason. Requires `ingest:manage`. |
| POST | `/api/ingest/connectors/{id}/release` | — | Return a quarantined connector to service. Requires `ingest:manage`. |
| GET | `/api/ingest/failures` | `connector_id`, `include_resolved`, `limit` | The dead-letter queue — **metadata only**, deliberately excluding the rejected payload. Stages are `fetch`, `validate`, `normalize`, `resolve` and `persist`; `resolve` means the record is well-formed but its subject matches no entity ARGUS holds. |
| GET | `/api/ingest/failures/{id}/payload` | — | The rejected record itself. Requires `ingest:read` **and** `entity:read`, so an administrator — who operates the pipeline but cannot read intelligence — is refused here while still seeing that the failure exists and why. |
| POST | `/api/ingest/failures/{id}/replay` | — | Re-run a dead-lettered record after fixing its cause. Requires `ingest:manage` and `entity:read`. |
| POST | `/api/ingest/failures/{id}/resolve` | `{resolution}` | Close an entry without replaying it. The entry is never deleted; only its resolution is recorded. |

Also `POST /api/provenance/sources` registers a source with its Admiralty rating,
a **required** stated basis for that rating, and an optional `staleness_hours`.
Re-registering an existing source is a **409**: a reliability rating re-weights
every assertion resting on it, so changing one is not a side effect of a repeated
call.

## Entity Resolution — `app/api/routes/resolution.py`

Requires `resolution:read`, held by every intelligence-reading role. An
administrator is **refused**: a candidate pair puts two records' attributes side
by side, which is intelligence, not pipeline operation.

`resolution:decide` records a decision; `resolution:manage` reverses one, pins a
cluster's representative record, or triggers a sweep. Reversal sits above
analyst for the same reason retraction does — undoing a colleague's decision is
a judgement about their work.

| Method | Path | Params | Description |
|---|---|---|---|
| GET | `/api/resolution/queue` | `band`, `entity_type`, `include_decided`, `limit`, `offset` | The review queue. Returns counts for **every** band and status, not just the one displayed: "12 pending" reads as "12 duplicates exist" without the denominators. |
| GET | `/api/resolution/model` | — | Every attribute the matcher compares, with its weight, comparator, and whether it is disqualifying or a strong identifier — plus the thresholds and the model fingerprint. Published rather than buried: a weighting nobody can inspect is not reviewable. |
| GET | `/api/resolution/candidates/{id}` | — | One scored pair with every attribute comparison, including the ones that **could not be compared**, and the pair's full decision history. |
| POST | `/api/resolution/candidates/{id}/decide` | `{verdict, rationale}` | Record `same` or `different`. `rationale` is required. **409** if the pair is already decided — reverse it instead, so the change is recorded as a reversal. Requires `resolution:decide`. |
| POST | `/api/resolution/decisions` | `{left_ref, right_ref, verdict, rationale}` | Decide a pair the matcher never proposed. The escape hatch for blocking's one silent failure: a pair no key brings together is never scored and appears nowhere. The pair is scored on the way through, so the record still carries what the model thought — including where it disagreed with the person. Requires `resolution:decide`. |
| GET | `/api/resolution/decisions` | `verdict`, `limit` | The append-only ledger, most recent first. |
| GET | `/api/resolution/decisions/pair` | `left`, `right` | Full merge lineage for a pair. A list, not a current state: "merged, un-merged, merged again by someone else" is a different situation from "merged". |
| POST | `/api/resolution/decisions/{id}/reverse` | `{rationale}` | Undo a decision by recording its opposite. Nothing is deleted. **409** if it is no longer the current decision for that pair. Requires `resolution:manage`. |
| GET | `/api/resolution/clusters` | `contested_only`, `entity_type`, `limit` | Clusters with their members, representative record, and how that record was chosen. A **contested** cluster contains a pair judged different — ARGUS states the contradiction and refuses to resolve it. |
| GET | `/api/resolution/entity/{ref}` | — | Everything resolution knows about one record: its cluster, its projected `SAME_AS` links, open candidates and decision history. Consumed by the entity profile. |
| POST | `/api/resolution/clusters/pin` | `{ref, reason}` | Choose which record represents a cluster, overriding the stated rule. Requires `resolution:manage`. |
| GET | `/api/resolution/runs` | `limit` | Sweep history, including the blocking report — how many records no key could place, and which keys stopped discriminating. |
| POST | `/api/resolution/runs` | `{entity_types?, apply_auto?}` | Queue a sweep; returns a job id. `apply_auto: false` scores without merging, which is the mode to use after changing weights. Requires `resolution:manage`. |
| GET | `/api/resolution/evaluations` | `limit` | Published precision and recall per model fingerprint, for both labelled datasets, each with a note stating what it does and does not measure. |
| POST | `/api/resolution/evaluations` | `entity_type`, `sample` | Re-measure and publish. Requires `resolution:manage`. |
| POST | `/api/resolution/rebuild-projection` | — | Re-derive every `SAME_AS` edge from the ledger. A repair tool and a proof at once: if the graph and PostgreSQL disagree, PostgreSQL wins. Requires `resolution:manage`. |

`SAME_AS` is deliberately excluded from every type-agnostic graph traversal —
connection counts, node degree, one-hop neighbours, shortest path and risk
propagation. It is a statement about *records*, not a relationship between
entities, and routing a path through one would manufacture a connection the
graph never contained.

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
