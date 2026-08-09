# Backend

Scope: the FastAPI application — folder structure, request lifecycle, services, background jobs, dependency injection, configuration. For the full endpoint list see [api.md](api.md); for Neo4j schema see [database.md](database.md); for the analytics/AI internals see [analytics.md](analytics.md) and [ai-layer.md](ai-layer.md).

Python 3.12, FastAPI, async Neo4j driver, async Redis client. Dependency manifest: `backend/pyproject.toml`.

## Folder structure

```
backend/app/
├── main.py                 # FastAPI app, lifespan, router registration, /api/health
├── config.py                # Settings (pydantic-settings, env-driven)
├── api/
│   ├── dependencies.py      # require_api_token, get_db
│   └── routes/               # one router module per resource
│       ├── ai.py
│       ├── alerts.py
│       ├── analytics.py
│       ├── cases.py
│       ├── dashboard.py
│       ├── entities.py
│       ├── graph.py
│       ├── map.py
│       ├── scenario.py
│       ├── search.py
│       └── timeline.py
├── database/
│   ├── neo4j.py              # process-wide AsyncDriver singleton
│   └── redis.py              # process-wide Redis client singleton
├── models/
│   ├── envelope.py           # Envelope[T] / Meta response wrapper
│   └── graph.py              # GraphNode / GraphEdge / Subgraph / PathResult
├── repositories/             # Cypher access, one module per read-domain
│   ├── entity_labels.py      # human-ID prefix -> Neo4j label/id-field map
│   ├── graph_repo.py         # generic node/subgraph/search/path traversal
│   ├── entity_repo.py        # entity profile: connections, timeline, related cases/alerts
│   ├── dashboard_repo.py     # aggregate counts for the Dashboard
│   ├── case_repo.py          # Case CRUD + evidence linking
│   ├── alert_repo.py         # Incident-as-alert filtered view
│   ├── map_repo.py           # geospatial reads
│   ├── timeline_repo.py      # global temporal activity sample
│   └── analytics_repo.py     # GDS projections + algorithm runs
└── services/                 # business logic that isn't pure Cypher
    ├── jobs.py                # async-job + Redis-status primitive
    ├── anomaly.py             # Isolation Forest + z-score detection
    ├── narrative.py           # deterministic template NLG
    ├── ollama.py              # optional local-LLM adapter
    └── scenario.py            # subprocess-driven scenario generation
```

**Repositories vs. services**: repositories are (almost) pure Cypher — they take a driver, run queries, shape rows into dicts. Services hold logic that doesn't belong in a query: background-job orchestration, ML model fitting, text composition, and subprocess management. Routes are thin — they resolve dependencies, call exactly one repository or service function, and wrap the result in an `Envelope`.

## Request lifecycle

1. **Startup** (`main.py`'s `lifespan`): `connect_neo4j()` creates one process-wide `AsyncDriver` (connection pool, max 50), `connect_redis()` creates one process-wide `Redis` client. Both call `verify_connectivity()`/`ping()` — the app fails to start if either datastore is unreachable.
2. **Per-request DI**: every route depends on `require_api_token` (bearer-token check against `settings.argus_api_token`) and `get_db` (returns the singleton driver via `Depends`). Routes needing Redis depend on `get_redis` the same way.
3. **Handler**: resolves params, calls a repository/service function, wraps the result in `Envelope(data=..., meta=...)`.
4. **Shutdown**: `close_neo4j()` / `close_redis()` release the pooled connections.

`GET /api/health` is the one unauthenticated route — it actively probes both datastores (`verify_connectivity()`, `ping()`) and reports `{"status": "ok"|"degraded", "neo4j": bool, "redis": bool}`.

## Configuration

`app/config.py`'s `Settings` (pydantic-settings, cached via `lru_cache`) reads from `../.env` relative to the backend process, with these fields: `neo4j_uri`, `neo4j_user`, `neo4j_password`, `redis_url`, `ollama_base_url`, `argus_api_token`, `cors_origins` (comma-separated, exposed as `cors_origin_list`). See [deployment.md](deployment.md#environment-variables) for the full variable reference and defaults.

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
3. Add a route function in the matching `api/routes/*.py` module. Depend on `get_db`/`get_redis`/`require_api_token` as needed. Return `Envelope[...]`.
4. If it's long-running, wrap it with `jobs.start_job` / `start_job_with_progress` rather than awaiting it directly in the handler.
5. Register the router in `main.py` if it's a new module (`app.include_router(...)`).

## Linting

`ruff` (line length 120, `select = ["E", "F", "I", "UP", "B"]`), configured in `pyproject.toml`. `B008` (function calls in argument defaults) is deliberately ignored — `Depends(...)` in a default is the standard FastAPI DI idiom, not a bug.

## Testing

`backend/tests/` holds unit tests for the pure-logic pieces that don't require a live Neo4j/Redis connection: human-ID label resolution (`entity_labels.py`), the deterministic narrative templates (`narrative.py`), the anomaly-detection sliding-window/z-score math (`anomaly.py`), and the `Envelope`/`Meta` response models. Run with `pytest` from `backend/` (config lives in `pyproject.toml`'s `[tool.pytest.ini_options]`). Repository functions that require a live database are exercised by manual/`curl` verification and the frontend's integration paths rather than mocked unit tests — mocking the Neo4j driver would test the mock, not the Cypher.
