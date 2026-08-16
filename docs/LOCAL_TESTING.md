# Running and testing ARGUS locally

A practical checklist for driving the application by hand. Everything here was
run against a live stack before it was written down.

Verified on macOS with Docker Desktop, Python 3.12/3.14 and Node 22.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Docker + Docker Compose | Runs Neo4j, Redis and PostgreSQL |
| Python ≥ 3.12 | Backend and generator each have their own virtualenv |
| Node 22 | Frontend |
| ~4 GB free RAM | Neo4j's heap is capped at 2 GB by default |

## Environment

```bash
cp .env.example .env
```

The defaults work out of the box for local development, and every variable is
documented in [deployment.md](deployment.md#environment-variables). The two that
most often need attention:

| Variable | Default | Why you might change it |
|---|---|---|
| `POSTGRES_PORT` | `55432` | Non-standard on purpose, so it cannot collide with a PostgreSQL you already run |
| `ARGUS_INGEST_ROOT` | unset | Required only to use the filesystem connector; every path is confined beneath it |

**The `.env` defaults are development credentials and are safe to be public** —
they exist in `.env.example` in the repository. They are not production
credentials and cannot become them: `docker-compose.yml` reads every one from
the environment, so a real deployment supplies its own and never inherits these.

---

## Startup

- [ ] **Start the databases** — `make infra-up`
      Starts Neo4j, Redis *and* PostgreSQL, and waits for all three to report
      healthy. PostgreSQL is not optional: it holds identity, the audit chain,
      provenance, ingestion and entity resolution, so without it nothing can
      authenticate.
- [ ] **Verify they are healthy** — `docker compose ps` shows three `healthy`
- [ ] **Seed the world** — `make seed`
      Generates ~19.5K nodes and ~90K relationships (~15s), then runs
      `backfill-provenance` so every generated value is attributed to the
      synthetic source that produced it. Without the backfill the UI is not
      wrong, but it correctly reports every value as *unattributed*.
- [ ] **Migrations** — nothing to do. Both databases migrate at backend startup;
      a failure aborts startup deliberately rather than serving a half-migrated
      schema.
- [ ] **Start the backend** — `make backend` → http://localhost:8000
- [ ] **Create an account** — there are no defaults:
      ```bash
      cd backend
      .venv/bin/python -m app.cli create-user --username you --role analyst
      ```
      Use **analyst** to actually look at intelligence. An `administrator`
      deliberately cannot read any of it.
- [ ] **Start the frontend** — `make frontend` → http://localhost:3000

### Verify the stack is actually up

- [ ] `curl localhost:8000/api/health` → `{"status":"ok","neo4j":true,"redis":true,"postgres":true}`
- [ ] `curl -o /dev/null -w '%{http_code}' localhost:8000/readyz` → `200`
      (returns `503` when a dependency is down, so a load balancer drains it)
- [ ] http://localhost:8000/docs loads the OpenAPI browser
- [ ] `make verify` → `N entries verified` (the audit hash chain)

---

## Authentication

- [ ] Sign in with your analyst account → lands on the Dashboard
- [ ] Sign out → returns to the sign-in gate
- [ ] Open http://localhost:3000/dashboard while signed out → sign-in form, not a blank page
- [ ] Wrong password → "Invalid username or password", and **the same message for
      an unknown username** — it must not reveal which accounts exist
- [ ] `curl localhost:8000/api/entities` with no cookie → `401`

### Roles are the interesting part

Create one of each and check the separation holds — it is the control that stops
a single compromised account being catastrophic:

- [ ] `administrator` → can open Settings/users, **cannot** open Dashboard,
      Alerts, Graph or Resolution (403). Managing the system is not permission to
      read what it knows.
- [ ] `auditor` → can read everything **and** the audit log, can change nothing
- [ ] `viewer` → reads intelligence, cannot triage, decide or merge
- [ ] `analyst` → can decide a resolution candidate, **cannot** reverse one
- [ ] `supervisor` → can reverse a merge and quarantine a feed

---

## Dashboard

- [ ] Metrics load and are non-zero
- [ ] Counts match the database — `active_cases` counts `Open` + `UnderReview`
      (a `Draft` case is not active), `open_alerts` counts open High/Critical
      incidents
- [ ] Every windowed figure states its window ("last 7 days") rather than
      presenting a slice as a total
- [ ] The header shows the **Synthetic** badge — the whole dataset is generated
      and the UI says so
- [ ] No console errors

## Alerts

- [ ] List loads with a total
- [ ] Filter by status and by priority
- [ ] Open an alert → detail renders
- [ ] Triage actions work as an analyst and are refused for a viewer
- [ ] Related alerts are shown, and are not simply "everything with the same
      storyline id"

## Cases

- [ ] List loads
- [ ] Create a case → appears in the list
- [ ] Open it → detail, linked entities, history
- [ ] Update status; close it
- [ ] The status vocabulary matches what the dashboard counts

## Map

- [ ] Map renders (give it ~5s; it keeps loading tiles, so "network idle" never
      arrives — that is not a hang)
- [ ] Regions carry entity counts and anomalous-route counts
- [ ] Click a region to drill in
- [ ] Toggle Entities / Routes / World
- [ ] The finding is stated in words, not left for you to infer from dot size

## Graph

- [ ] Graph renders with a node/edge count shown (e.g. "159 nodes · 196 edges")
- [ ] Relationships render and are typed
- [ ] Search for an entity and re-seed the view
- [ ] Click a node → inspection panel
- [ ] **A merged pair does not appear as a connection.** `SAME_AS` is a statement
      about records, not a relationship between entities, so it is excluded from
      connection counts, node degree and shortest path.

## Timeline

- [ ] Timeline loads, spanning ~180 days
- [ ] **Refresh twice — the buckets must be byte-identical.** Only `computed_at`
      may differ. Anything else means sampling is back (audit B-03).
- [ ] The day series is contiguous, including days with zero activity (B-18) —
      omitting empty days inflates the mean and hides real bursts
- [ ] Totals state `basis: complete`, and the lane totals sum to the overall total
- [ ] Lane filtering recomputes from per-lane counts rather than apportioning

## Analytics

- [ ] Page loads
- [ ] Run a job → it completes and results render
- [ ] Every graph result names the projection it came from
- [ ] Restarting the backend mid-job does not leave a job "running" forever

## Search

- [ ] Search returns results with a total
- [ ] Result → entity profile

## Entity profile

- [ ] `/entities/PRS-0002001` loads
- [ ] Risk is visible on arrival, with its provenance
- [ ] **The risk score is labelled as generator-assigned**, rated F6, with a note
      saying it came from storyline membership rather than evidence. This is the
      single most important thing on the page: it is the difference between a
      number and a conclusion.
- [ ] Provenance tab lists observations and assertions
- [ ] Conflicting values are shown as conflicts, not silently resolved

## Sources (ingestion)

- [ ] `/sources` loads
- [ ] With no connectors configured, it says so plainly and explains that
      everything in the graph came from the generator
- [ ] Add a connector, drop a `.jsonl` file under `ARGUS_INGEST_ROOT`, run it
- [ ] A malformed record lands in the dead-letter queue with a stage and reason
- [ ] A record whose subject does not exist dead-letters at the `resolve` stage —
      **not** silently accepted
- [ ] Re-reading the same file creates no duplicate observation

## Resolution

- [ ] `/resolution` loads
- [ ] Band counts are shown with denominators ("of 1,556 scored")
- [ ] Open a candidate → every attribute compared side by side, including the
      ones marked **Not comparable**
- [ ] The score is never shown without the share of evidence behind it
- [ ] Decide a pair (rationale required) → it leaves the queue
- [ ] Reverse the decision as a supervisor → both decisions remain in the ledger
- [ ] A contested cluster, if any, leads the page and is not auto-resolved

## Settings

- [ ] Page loads
- [ ] As an administrator, user management is reachable

## Navigation

- [ ] Every sidebar item routes correctly
- [ ] Items your role cannot use are hidden rather than shown and 403-ing
- [ ] Breadcrumbs and back-navigation behave

---

## Error handling

- [ ] Empty state — a page with no data explains what would fill it
- [ ] `404` — `/api/entities/PRS-0000000` returns `{"detail":"Entity not found"}`
- [ ] `422` — `/api/entities?page_size=9999` is rejected, not silently clamped
- [ ] `403` — an analyst calling `/api/admin/audit`
- [ ] **CSRF** — a `POST` without the `X-CSRF-Token` header is refused
- [ ] **Database outage** — `docker stop argus-postgres`, then reload a page.
      Every route returns `503` with a stated reason and `Retry-After`, never a
      bare `500`. `docker start argus-postgres` and it recovers **without
      restarting the backend**.
- [ ] **Graph outage** — `docker stop argus-neo4j` during ingestion. The batch
      fails as one retryable unit; it must **not** dead-letter records as
      "unknown subject", because "the database is down" and "this person does not
      exist" are different facts.

---

## Verifying the data is not misleading

The audit's central finding was that several surfaces presented sampled or
generated values with the authority of analytic conclusions. These checks exist
to make sure that has not come back:

- [ ] Timeline is deterministic across refreshes (no sampling)
- [ ] Timeline days are contiguous (no inflated means)
- [ ] Every aggregate is shown with its denominator
- [ ] The generator is registered as a source with `is_synthetic: true`, rated
      `F`, with a stated basis:
      ```bash
      curl -b cookies.txt localhost:8000/api/provenance/sources
      ```
- [ ] Generated risk scores are `inferred` assertions rated `F6` with method
      `generator.risk_scorer@v1`, not bare numbers on the node
- [ ] No surface presents `storyline_id` or `flagged` as a discovered finding

---

## Stopping and resetting

```bash
make stop     # stops backend, frontend and databases; keeps all data
make reset    # destroys the volumes: graph, accounts, audit chain, provenance
```

After a `reset`, start again from `make infra-up` and `make seed`.

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `readyz` returns 503 | One dependency is down. The body names which. `docker compose ps` |
| Backend exits at startup with a migration error | Deliberate — it refuses to serve a half-migrated schema. Read the logged error; `make reset` if the database is from an older schema you do not need |
| Every page shows the sign-in form | No account exists yet. `create-user` |
| Signed in but every page 403s | You are probably an `administrator`, who cannot read intelligence by design. Sign in as an analyst |
| Entity values all show "unattributed" | `backfill-provenance` has not run — `make seed` |
| `/scenario` fails to run | It invokes `generator/.venv` as a subprocess; keep that virtualenv in place |
| Port 55432 in use | Another PostgreSQL. Change `POSTGRES_PORT` in `.env` |
| Neo4j unhealthy on first start | It can take ~30s to open the store. `make infra-logs` |
| Integration tests skip | The databases are not up. `make infra-up` — CI treats a skip as a failure for exactly this reason |
| `make help` prints escape codes | Fixed; if you see it, your `make` is not using bash — the Makefile sets `SHELL := /bin/bash` |
