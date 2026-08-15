# Deployment & Configuration

Scope: running ARGUS locally, what Docker Compose provides, every environment variable, and what a production deployment would need that this project deliberately doesn't build. For day-to-day run problems see [troubleshooting.md](troubleshooting.md).

ARGUS is **local-first by design** — there is no hosted deployment, and none is planned near-term (see [architecture.md](architecture.md#why-in-process-asyncio-jobs-instead-of-a-task-queue-celeryarq) for the related single-machine scope decision). Everything runs via Docker Compose (Neo4j + Redis, optionally the backend too) plus the Next.js dev/production server.

## Running locally

```bash
cp .env.example .env

# 1. Graph database (with GDS) + cache
docker compose up -d neo4j redis

# 2. Populate the graph (~20K nodes, ~90K relationships, ~15s)
cd generator
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export NEO4J_PASSWORD=argus_dev_password
python3 generate_world.py --seed 42

# 3. Backend
cd ../backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
# — or: docker compose up -d backend

# 4. Frontend
cd ../frontend
npm install
npm run dev
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API + Swagger docs | http://localhost:8000 / http://localhost:8000/docs |
| Neo4j Browser | http://localhost:7474 |

Keep `generator/.venv` in place after initial world generation — the Scenario Generator feature (`/scenario` page) invokes `generator/.venv/bin/python3` as a subprocess at request time; see [generator.md](generator.md#on-demand-scenario-generation).

## Docker Compose services

`docker-compose.yml` defines three services:

- **`neo4j`** — `neo4j:5-community` with the `graph-data-science` plugin enabled via `NEO4J_PLUGINS`, and GDS procedures explicitly allowlisted/unrestricted (`NEO4J_dbms_security_procedures_unrestricted`/`_allowlist: gds.*` — GDS's own procedures are otherwise sandboxed by Neo4j's default security policy). Heap/page-cache memory is capped (512MB initial / 1GB max heap, 512MB page cache) — sized for the default generator scale on a single laptop, not for a large production graph. Healthcheck polls the browser port.
- **`redis`** — `redis:7-alpine`, healthcheck via `redis-cli ping`.
- **`backend`** — builds from `backend/Dockerfile`, depends on both other services being `service_healthy` (not just started) before it starts, runs `uvicorn --reload` with the app directory bind-mounted for live reload during development. Reads its Neo4j/Redis URIs from the Docker service names (`bolt://neo4j:7687`, `redis://redis:6379/0`) rather than `localhost`, since it's on the same Compose network.

The `frontend` is intentionally **not** in `docker-compose.yml` — it's run via `npm run dev`/`npm run build && npm run start` directly, since Next.js's dev-server hot reload is the faster local workflow and there's no need to containerize it for a local-only deployment.

## Environment variables

All variables are documented with defaults in `.env.example` (repo root). Backend reads them via `app/config.py`'s `Settings` (from `../.env` relative to the backend process); frontend reads the `NEXT_PUBLIC_*` ones at build/runtime via `process.env`.

| Variable | Default | Used by | Purpose / impact |
|---|---|---|---|
| `NEO4J_URI` | `bolt://localhost:7687` | backend, generator | Bolt connection string. Inside Docker Compose, the backend overrides this to `bolt://neo4j:7687`. |
| `NEO4J_USER` | `neo4j` | backend, generator | Neo4j username. |
| `NEO4J_PASSWORD` | `argus_dev_password` | backend, generator, docker-compose (`NEO4J_AUTH`) | Neo4j password. Change this before exposing Neo4j's ports beyond localhost. |
| `REDIS_URL` | `redis://localhost:6379/0` | backend | Job-status store connection string. |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | backend (`app/services/ollama.py`) | Optional. If unreachable, the "Ask ARGUS" panel simply doesn't render — no other feature is affected. Inside Docker Compose, defaults to `http://host.docker.internal:11434` so a containerized backend can still reach an Ollama instance running on the host. See [ai-layer.md](ai-layer.md). |
| `POSTGRES_PORT` | `55432` | backend, docker-compose | Host port for ARGUS's PostgreSQL. Deliberately not 5432 — many machines already run their own PostgreSQL, and competing for the default port produces authentication errors that read as credential bugs. |
| `POSTGRES_SUPERUSER` / `POSTGRES_SUPERUSER_PASSWORD` | `argus_admin` / `argus_dev_password` | migrations only | Used to create the schema, the append-only audit triggers, and the least-privilege application role. The running app never uses these. |
| `POSTGRES_APP_USER` / `POSTGRES_APP_PASSWORD` | `argus_app` / `argus_dev_app_password` | backend | The role the application connects as. Holds `INSERT` and `SELECT` on `audit_events` and nothing else — see [Auth model](#auth-model). |
| `SESSION_COOKIE_SECURE` | `false` | backend | Set `true` wherever ARGUS is reachable over a network. `false` is for local http development only. |
| `SESSION_ABSOLUTE_HOURS` / `SESSION_IDLE_MINUTES` | `12` / `60` | backend | Absolute and idle session lifetimes. Both are enforced; the shorter wins. |
| `CORS_ORIGINS` | `http://localhost:3000` | backend | Comma-separated allowed origins for the FastAPI CORS middleware. |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | frontend (`lib/api.ts`) | Where the frontend sends every API request. |

Any `NEXT_PUBLIC_*` variable is baked into the frontend at build time and visible in the browser bundle. That is standard Next.js behaviour, and it is exactly why **no credential is passed that way**: the frontend receives only the API base URL.

## Auth model

Authentication is a **server-side session referenced by an httpOnly cookie**. There is no token
in the browser: JavaScript cannot read the session cookie, so an XSS flaw cannot exfiltrate it.

- `POST /api/auth/login` verifies the password (Argon2id) and, if the account has MFA enrolled, a
  TOTP code. On success it sets `argus_session` (httpOnly) and `argus_csrf` (readable by
  same-origin script).
- Every state-changing request must echo the CSRF cookie in an `X-CSRF-Token` header. This is
  required *because* the credential is a cookie: the browser attaches it to cross-site requests
  automatically, so a value only same-origin script can read must be presented alongside it.
- Sessions carry an absolute expiry and an idle expiry; the shorter wins. Tokens are stored only
  as SHA-256 hashes, so a database read yields no usable credential.
- Failed logins are counted per account and lock it temporarily. Login responses are deliberately
  identical for "no such user", "wrong password" and "locked" — distinguishing them would hand an
  attacker an account-enumeration oracle. The real reason is recorded in the audit log.

### Roles

| Role | Read intelligence | Triage / cases | Analytics | Scenario | Users | Audit log |
|---|---|---|---|---|---|---|
| `viewer` | ✓ | — | read only | — | — | — |
| `analyst` | ✓ | ✓ | ✓ | — | — | — |
| `investigator` | ✓ | ✓ (any case) | ✓ | — | — | — |
| `supervisor` | ✓ | ✓ (any case) | ✓ | ✓ | — | ✓ |
| `administrator` | **—** | — | — | — | ✓ | ✓ |
| `auditor` | ✓ | **—** | read only | — | — | ✓ |

Two separations are deliberate rather than incidental:

- **An administrator cannot read intelligence.** Compromising that account grants the ability to
  disrupt ARGUS, not to exfiltrate what it knows.
- **An auditor cannot write anything.** The account that can see what happened cannot also change
  it, so one compromised account cannot both act and erase the evidence.

The frontend hides surfaces a role lacks, but that is a usability affordance only — every
permission is enforced again on the server, because a hidden link is not a boundary.

### Audit log

Every mutation is recorded in PostgreSQL with actor, action, resource, before/after state,
request id and source address. Two properties make it trustworthy:

1. **Append-only, enforced by the database.** The application role is granted `INSERT` and
   `SELECT` on `audit_events` and nothing else, and triggers reject `UPDATE`, `DELETE` and
   `TRUNCATE` for *every* role including the superuser. Removing a record requires
   database-superuser access **and** explicitly disabling a trigger.
2. **Hash-chained.** Each row carries its predecessor's hash, so altering or removing one breaks
   the chain detectably. `GET /api/admin/audit/verify` (or `python -m app.cli verify-audit`)
   recomputes it.

There is deliberately **no "re-seal the chain" command**. A feature that recomputes the hashes
would let an attacker who tampered with records hide it, defeating the property entirely. A broken
chain is repaired by a human with superuser access, after forensic review.

### Creating the first account

Authentication guards every endpoint, so a fresh deployment has nobody who can log in:

```bash
cd backend
python -m app.cli create-user --username you --role administrator
```

The password is read from `ARGUS_NEW_USER_PASSWORD` or prompted for — never accepted as a
command-line flag, since argv is world-readable via `/proc` and `ps`.

## What would need to change for a real multi-tenant/hosted deployment

This is explicitly out of scope for the current project, but worth naming precisely since it's a common follow-up question:

- ~~**Auth**~~ — done: per-user sessions, roles, and an append-only audit log. An external identity provider (OIDC/SAML) would still be needed for single sign-on.
- **Background jobs** — replace `asyncio.create_task` + Redis-status with a real task queue (Celery, ARQ, or similar) that survives a process restart and can run on separate worker nodes — see [architecture.md](architecture.md#why-in-process-asyncio-jobs-instead-of-a-task-queue-celeryarq).
- **Neo4j sizing** — the current heap/page-cache limits in `docker-compose.yml` are tuned for the default ~20K-node synthetic world on a laptop; a larger or multi-tenant graph needs real capacity planning.
- **Scenario Generator subprocess model** — spawning a Python subprocess per scenario request is fine for one analyst; it would need queuing/isolation (containers-per-job, or a proper job runner) under concurrent multi-user load.
- **Reverse proxy / TLS** — none is configured; a hosted deployment needs a reverse proxy (nginx, Caddy, or a platform load balancer) terminating TLS in front of both the frontend and the backend.

## Regenerating or resetting the world

There is no in-app control for this (deliberately — it's destructive):

```bash
cd generator
python3 generate_world.py --seed 42          # refuses if the graph is already populated
python3 generate_world.py --seed 42 --wipe   # destructive: deletes everything first
```

See [generator.md](generator.md) for what this does and how to change scale.
