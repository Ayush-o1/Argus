# Backend

Scope: the FastAPI application — folder structure, request lifecycle, services, background jobs, dependency injection, configuration. For the full endpoint list see [api.md](api.md); for Neo4j schema see [database.md](database.md); for the analytics/AI internals see [analytics.md](analytics.md) and [ai-layer.md](ai-layer.md).

Python 3.12, FastAPI, async Neo4j driver, async Redis client. Dependency manifest: `backend/pyproject.toml`.

## Folder structure

```
backend/app/
├── main.py                 # FastAPI app, lifespan, middleware order, routers, health
├── cli.py                   # out-of-band ops: create-user, verify-audit, backfill-provenance
├── config.py                # Settings (pydantic-settings, env-driven)
├── api/
│   ├── dependencies.py      # current_user, require_permission, get_db, get_pg
│   └── routes/               # one router module per resource
│       ├── admin.py           # user management + audit-log reads
│       ├── ai.py
│       ├── alerts.py
│       ├── analytics.py
│       ├── auth.py            # login, logout, session check
│       ├── cases.py
│       ├── dashboard.py
│       ├── entities.py
│       ├── graph.py
│       ├── map.py
│       ├── provenance.py      # sources, observations, assertions, conflicts
│       ├── resolution.py      # review queue, decision ledger, clusters, evaluations
│       ├── scenario.py
│       ├── search.py
│       └── timeline.py
├── database/
│   ├── neo4j.py              # process-wide AsyncDriver singleton
│   ├── postgres.py           # process-wide asyncpg pool
│   ├── redis.py              # process-wide Redis client singleton
│   ├── migrations/           # Neo4j migrations, forward-only, applied at startup
│   └── pg_migrations/        # PostgreSQL migrations, ditto
├── resolution/               # matching: normalise, compare, block, score, cluster, evaluate
│   │                         # pure — no I/O, so a merge is re-derivable from the record alone
├── ingestion/
│   ├── base.py               # Connector ABC + registry; secrets read by env-var name
│   ├── connectors.py         # filesystem drop folder, http_json poller
│   └── mapping.py            # declarative record mapping; timestamp normalisation
├── middleware/
│   ├── request_context.py    # request IDs, correlation
│   └── security.py           # rate limiting, security headers
├── security/
│   ├── passwords.py          # Argon2id hashing, strength rules
│   ├── roles.py              # Role / Permission enums, the authorization matrix
│   └── sessions.py           # session issue, resolve, revoke; CSRF tokens
├── observability/
│   └── logging.py            # structured JSON logging, actor context
├── models/
│   ├── aggregate.py          # Aggregate[T] — a value that cannot omit its denominator
│   ├── envelope.py           # Envelope[T] / Meta response wrapper
│   ├── graph.py              # GraphNode / GraphEdge / Subgraph / PathResult
│   └── provenance.py         # EpistemicKind, Reliability, Credibility, Assertion, Conflict
├── repositories/             # datastore access, one module per read-domain
│   ├── entity_labels.py      # human-ID prefix -> Neo4j label/id-field map
│   ├── graph_repo.py         # generic node/subgraph/search/path traversal
│   ├── entity_repo.py        # entity profile: connections, timeline, related cases/alerts
│   ├── dashboard_repo.py     # aggregate counts for the Dashboard
│   ├── case_repo.py          # Case CRUD + evidence linking
│   ├── alert_repo.py         # Incident-as-alert filtered view
│   ├── map_repo.py           # geospatial reads
│   ├── timeline_repo.py      # full-population temporal aggregation
│   ├── analytics_repo.py     # GDS projections + algorithm runs
│   ├── provenance_repo.py    # observations, assertions, conflicts, corroboration
│   └── user_repo.py          # users and sessions
└── services/                 # business logic that isn't pure Cypher
    ├── audit.py               # append-only, hash-chained audit log
    ├── jobs.py                # async-job + Redis-status primitive (analytics, scenario)
    ├── queue.py               # durable Postgres job queue + worker
    ├── scheduler.py           # queues connector runs when their interval elapses
    ├── ingest.py              # the pipeline: land, validate, resolve, observe, quarantine, replay
    ├── resolution.py          # runs, decisions, clusters, subject lookup — every DB call for matching
    ├── anomaly.py             # Isolation Forest + z-score detection
    ├── narrative.py           # deterministic template NLG
    ├── ollama.py              # optional local-LLM adapter
    ├── provenance.py          # source registry, graph backfill, attribute resolution
    └── scenario.py            # subprocess-driven scenario generation
```

**Repositories vs. services**: repositories are (almost) pure Cypher — they take a driver, run queries, shape rows into dicts. Services hold logic that doesn't belong in a query: background-job orchestration, ML model fitting, text composition, and subprocess management. Routes are thin — they resolve dependencies, call exactly one repository or service function, and wrap the result in an `Envelope`.

## Request lifecycle

1. **Startup** (`main.py`'s `lifespan`): PostgreSQL migrations run first (identity must be migrated before the app can authenticate anyone), then the Postgres pool, then `connect_neo4j()` / `connect_redis()`, then the Neo4j migrations, then registration of ARGUS's built-in provenance sources, then reaping of jobs orphaned by a previous process. A migration failure aborts startup deliberately.
2. **Middleware**: registered so that CORS is **outermost**. Starlette applies middleware in reverse registration order, and with CORS registered innermost an early 429 short-circuited before it ran — so the browser reported an opaque "blocked by CORS policy" instead of the rate limit that actually happened.
3. **Per-request DI**: routes depend on `require_permission(Permission.X)`, which resolves the session cookie to a user, enforces CSRF on unsafe methods, and checks the named permission. Permissions are enumerated in `app/security/roles.py` rather than inferred from role names, so adding a route forces an explicit decision about who may call it. `get_db` returns the singleton Neo4j driver; `get_pg` yields a pooled Postgres connection.
4. **Handler**: resolves params, calls a repository/service function, wraps the result in `Envelope(data=..., meta=...)`. Mutating handlers also write an audit event — inside the mutation's transaction where one exists, so the change and its record commit or roll back together.
5. **Shutdown**: in-flight jobs are cancelled and given a moment to record terminal state, then the pools are released.

`GET /api/health`, `/livez` and `/readyz` are unauthenticated. `/readyz` probes all three datastores and returns **503** when any is unreachable, so an orchestrator pulls the instance rather than routing traffic to one that cannot serve it.

## Configuration

`app/config.py`'s `Settings` (pydantic-settings, cached via `lru_cache`) reads from `../.env` relative to the backend process: `neo4j_*`, `redis_url`, `postgres_*` (host, port, database, superuser and application credentials), `ollama_base_url`, `session_*`, and `cors_origins` (comma-separated, exposed as `cors_origin_list`). See [deployment.md](deployment.md#environment-variables) for the full reference and defaults.

There is deliberately **no** `argus_api_token`. The single static bearer token was removed rather than rotated, and the setting was deleted with it: a setting left behind after the code stops reading it reads as a control that exists.

## Response envelope

Every endpoint returns `Envelope[T]` (`backend/app/models/envelope.py`):

```python
class Meta(BaseModel):
    total: int = 0
    page: int = 1
    page_size: int = 50

class Envelope(BaseModel, Generic[T]):
    data: T
    meta: Meta | None = None
    error: str | None = None
```

`meta` is populated only on paginated list endpoints (entities, cases, alerts, search). Errors surface as standard FastAPI `HTTPException`s (404, 400, 503), not via the `error` field — that field exists in the model but the current routes don't populate it; failures raise instead.

## Entity ID resolution

Every human-readable ID (`PRS-0000442`, `ACC-0000771`, ...) encodes its type as a 3-4 letter prefix. `app/repositories/entity_labels.py`'s `ENTITY_LABELS` dict maps each prefix to a `(label, id_field, name_field)` triple, and `resolve_label(human_id)` does the prefix split. This is what lets a single route like `GET /api/entities/{entity_id}` accept any entity type without a `type` query param — see `graph_repo.get_node_by_human_id`.

This map is duplicated (not imported) from the generator's implicit scheme in `neo4j_writer.py`'s `NODE_SPECS` — see [architecture.md](architecture.md#why-three-separate-deployables-instead-of-one) for why.

## Background jobs

`app/services/jobs.py` is the one place the "kick off → poll → fetch result" pattern is implemented, reused by analytics, anomaly detection, and scenario generation.

```python
async def create_job(redis, job_type) -> str          # SET job:<uuid> {status: running, stages: []}, TTL 1h
async def get_job(redis, job_id) -> dict | None        # GET job:<uuid>, json.loads
async def update_job_progress(redis, job_id, stages)   # append live stage list to a running job
async def run_job(redis, job_id, coro)                 # await coro, write terminal state (done|failed) back
async def start_job(redis, job_type, work) -> str      # create_job + asyncio.create_task(run_job(...))
async def start_job_with_progress(redis, job_type, work) -> str  # like start_job, but work(job_id) can call update_job_progress
```

Job records are plain Redis strings (JSON-encoded), keyed `job:<uuid>`, TTL 1 hour. There is no separate worker process — `asyncio.create_task` runs the job coroutine in the same event loop as the FastAPI process. See [architecture.md](architecture.md#why-in-process-asyncio-jobs-instead-of-a-task-queue-celeryarq) for why this is sufficient at this project's scale, and what would need to change to run this multi-tenant.

Every analytics route (`app/api/routes/analytics.py`) follows the identical shape:

```python
@router.post("/pagerank")
async def run_pagerank(driver=Depends(get_db), redis=Depends(get_redis)) -> Envelope[dict]:
    job_id = await jobs.start_job(redis, "pagerank", partial(analytics_repo.run_pagerank, driver))
    return Envelope(data={"job_id": job_id, "status": "running"})

@router.get("/results/{job_id}")
async def get_job_result(job_id: str, redis=Depends(get_redis)) -> Envelope[dict | None]:
    return Envelope(data=await jobs.get_job(redis, job_id))
```

Scenario generation uses `start_job_with_progress` instead, because it needs to stream intermediate stage messages from a subprocess — see [generator.md](generator.md#the-stage--result_json-protocol) and `app/services/scenario.py`.

## Adding a new endpoint

1. If it's a new read pattern, add a function to the relevant `repositories/*.py` module (or a new module if it's a genuinely new domain) — pure Cypher in, shaped dict/list out.
2. If it needs logic beyond querying (ML, text generation, a subprocess, a multi-step Cypher orchestration), add it to `services/`.
3. Add a route function in the matching `api/routes/*.py` module. Depend on `require_permission(Permission.X)` for the permission it needs, plus `get_db`/`get_redis`/`get_pg`. Return `Envelope[...]`. A new permission means adding it to `app/security/roles.py` and deciding, explicitly, which roles hold it — the enum is the decision point, so a route cannot quietly inherit access.
4. If it's long-running, wrap it with `jobs.start_job` / `start_job_with_progress` rather than awaiting it directly in the handler.
5. Register the router in `main.py` if it's a new module (`app.include_router(...)`).

## Linting

`ruff` (line length 120, `select = ["E", "F", "I", "UP", "B"]`), configured in `pyproject.toml`. `B008` (function calls in argument defaults) is deliberately ignored — `Depends(...)` in a default is the standard FastAPI DI idiom, not a bug.

## Testing

`backend/tests/` holds 593 tests. Run them with `pytest` from `backend/` (config lives in `pyproject.toml`'s `[tool.pytest.ini_options]`).

Most are pure-logic tests over the pieces that carry the intelligence: the matching, scoring and correlation measures, the isolation scans that fail the build if an application surface reads a generator-planted field, and the response models. The rest are integration tests that run against a **real** Neo4j and a **real** PostgreSQL, because the defects the production audit found all lived in code no test had executed, and a mocked driver reproduces that gap exactly — it cannot tell you that `collect(...)[0..5]` truncates a count, that `count(*) + 1` races, or that a lookup is a label scan.

Both stores are isolated rather than mocked, by different means:

- **Neo4j** — Community edition permits only one database, so every node a test creates carries a `_test_tag` and the `graph` fixture deletes exactly those afterwards. Running the suite against a populated development graph is therefore not destructive.
- **PostgreSQL** — redirected wholesale to a separate database (`argus_test` by default, `ARGUS_TEST_POSTGRES_DB` to change it), created and migrated by a session fixture. Tagging does not work here: `audit_events` is append-only by trigger, so rows a test writes cannot be removed afterwards by anyone. `conftest.py` refuses to start if the test database and the configured working database are the same name.

Because the test database is created from empty, a normal run also exercises the migrations from zero — which running them only against a long-lived working database never does.

Integration tests **skip** rather than fail when a database is unreachable, so `pytest` still works on a laptop with nothing running. CI treats any skip as a failure, since a green run that silently exercised nothing is worse than a red one.
