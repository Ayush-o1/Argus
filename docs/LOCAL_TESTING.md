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

### Using a PostgreSQL you already run

The compose stack is a convenience, not a requirement. To use an existing
server instead, point the Postgres variables at it and skip the `postgres`
service:

```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5432          # wherever your server listens
POSTGRES_DB=argus           # created by you; ARGUS never creates a database
POSTGRES_SUPERUSER=<your superuser>
POSTGRES_SUPERUSER_PASSWORD=<their password>
POSTGRES_APP_USER=argus_app
POSTGRES_APP_PASSWORD=<generate one>
```

Create the database first — `CREATE DATABASE argus;` — and let the migrations
do the rest. They create `argus_app`, grant it exactly what it needs, and set
its password from `POSTGRES_APP_PASSWORD` on every startup, so rotating that
value is a restart rather than a migration.

Two things are worth checking on a server you did not configure for ARGUS:

- **`pg_hba.conf` must not be `trust` for the connections ARGUS uses.** Under
  `trust`, PostgreSQL ignores passwords entirely: the least-privilege split
  still holds, because `argus_app`'s *privileges* are enforced regardless, but
  any local process can connect as the superuser and the audit log's
  tamper-resistance is only as good as who can reach the port. A Homebrew or
  distribution default install is frequently `trust` on loopback. Use
  `scram-sha-256` for `host` lines.
- **Do not point `POSTGRES_APP_USER` at the superuser.** The audit log survives
  compromise of the API precisely because the application's role cannot UPDATE
  or DELETE an audit row. A superuser DSN makes that property decorative.

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
- [ ] **Assess the world** — sign in as an investigator and press *Re-assess* on
      `/assessment`, or leave it: every risk surface will honestly report that
      nothing has been assessed yet
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
- [ ] `analyst` → can decide a resolution candidate, **cannot** reverse one,
      and **cannot** trigger an assessment run
- [ ] `supervisor` → can reverse a merge, quarantine a feed and run an assessment

---

## Dashboard

- [ ] Metrics load and are non-zero
- [ ] Counts match the database — `active_cases` counts `Open` + `UnderReview`
      (a `Draft` case is not active), and `open_alerts` counts alerts **ARGUS
      raised** from the alerting tables. It previously counted open High/Critical
      `Incident` nodes, which the generator writes one of per storyline, so the
      dashboard was reporting the answer key's size as the queue
- [ ] "Elevated entities" counts what **ARGUS** assessed, not what the generator
      flagged, and sits beside "Not assessable" — the figure that qualifies it.
      There is deliberately no mean risk score
- [ ] Every windowed figure states its window ("last 7 days") rather than
      presenting a slice as a total
- [ ] The header shows the **Synthetic** badge — the whole dataset is generated
      and the UI says so
- [ ] No console errors

## Alerts

Alerts are raised by rules over ARGUS's own findings, so **run the assessment
and the correlator first** — with neither, the queue is legitimately empty and
the page says so rather than showing a blank.

- [ ] **Run the rules** — *Alerts → Run rules* (investigator or supervisor).
      The run reports firings, how many were new, how many were repeats, how
      many are suppressed, and how many groups formed.
- [ ] **Every row names its rule.** No alert should be attributable to
      "the system". Open one: it carries the rule id and version, the evidence
      behind the summary, and the priority factors.
- [ ] **Run the rules again without changing anything.** `alerts_created`
      must be **0** and `alerts_repeated` equal to the firing count. The queue
      must not grow. On the alert, "seen N×" increments and the occurrence list
      gains a row.
- [ ] **Triage moves are attributed.** Move an alert Open → Acknowledged →
      Investigating → Resolved. Each step appears in *History* with the
      username, the role and the time. Reopen it: `closed_at` clears.
- [ ] **Illegal moves are refused with a useful message.** Try Open →
      Resolved: the error names what *is* reachable from Open, rather than
      saying "invalid status".
- [ ] **Dismissal requires a vocabulary reason.** Dismiss with no reason, and
      with an invented one — both refused, and the message lists the valid
      codes.
- [ ] **Groups are the correlated clusters, largest first.** A group of one is
      described as an alert ARGUS could not connect to anything, not as a
      group.
- [ ] **Suppression hides without silencing.** Suppress a rule, re-run, and
      check: the alerts are still raised and counted (the run reports
      `suppressed`), the banner states how many are hidden, and the *Suppressed*
      tab shows them, each naming the suppression that hid it.
- [ ] **Suppression cannot be indefinite or unscoped.** A suppression naming
      neither a rule nor a subject is refused; so is one expiring beyond 90
      days, and one whose note is under a sentence.
- [ ] **Priority publishes its factors** — corroboration, confidence,
      magnitude, recency — and states that asset criticality is **not**
      computed, because ARGUS has no asset register.
- [ ] **Roles differ.** An analyst can triage but not suppress and not run the
      rules; an investigator can do all three; an administrator gets 403 on
      every alert route including reads.

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
- [ ] Every graph result names the projection it came from: the graph's title,
      its fingerprint, every relationship type with its weight, and the caveats
      saying what that graph cannot answer
- [ ] Run PageRank on `money`, then on `entity` (`?projection=entity`). The
      rankings differ and the top entries change type — accounts on one,
      organisations on the other. That difference is the point: "influence"
      means something different depending on which graph was asked
- [ ] An unknown projection returns 422 naming the two that exist
- [ ] Restarting the backend mid-job does not leave a job "running" forever

## Search

- [ ] Search returns results with a total
- [ ] Result → entity profile

## Entity profile

- [ ] `/entities/PRS-0002001` loads
- [ ] **ARGUS assessment** is the first thing in the sidebar, with its band, its
      score, and the share of the model that could be evaluated — never the
      score alone
- [ ] Three states are visually distinct: **what fired**, **could not be
      evaluated**, and **examined, nothing found**. The middle one is the point:
      "no device is registered to this person" is not the same as "this person
      made no calls"
- [ ] Below it, **Reported by source** shows the generator's own number as a
      claim — *inferred*, rated F6, with a note saying it came from storyline
      membership. Look for an entity where the two disagree: PRS-0000590 is
      assessed elevated by ARGUS from a real funds cycle while the generator
      scored it 2/100
- [ ] An entity with no assessment says so plainly and is **not** drawn as low
      risk
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

## Assessment

- [ ] `/assessment` loads with band counts that sum to the assessed population
- [ ] Before any run has happened it says so plainly, rather than showing zeros
      that look like findings
- [ ] Each queue row states the actual finding with real numbers ("Funds moved
      through a 6-account ring and returned to the start within 18h, retaining
      74% of the opening amount"), not a bare score
- [ ] Every row shows its evidence coverage beside its score
- [ ] **What ARGUS looks for** lists every signal, its weight, the question it
      asks and why it counts as evidence
- [ ] **How well it performs** shows precision and recall against planted
      storylines, *and* names the two planted phenomena no signal can detect,
      with the reason. If that table ever hides them, the numbers above it are
      inflated
- [ ] Re-assess as an investigator → a run is queued; an analyst gets 403
- [ ] Stop Neo4j and trigger a run → the run is recorded as **failed** with the
      reason, the previous generation of assessments is untouched, and the page
      says the counts may be out of date rather than reporting "saw 0 transfers"

## Correlation

Correlation runs over ARGUS's own findings, so run an assessment first.

- [ ] `/correlation` loads with tier counts that sum to the recorded links
- [ ] Before any run has happened it says so plainly, and says that correlation
      needs an assessment first
- [ ] Each link states the reason with real quantities ("Money moves ORG-0000140
      ← PRS-0002510 in 1 hop, retaining 100% of its value... that first payment
      is 42% of everything ACC-0002387 sent"), not a bare similarity score
- [ ] Every link shows how many dimensions could be evaluated, beside its
      strength, and names the ones that could not
- [ ] **Groups** are modularity communities, not chains. No group should be
      hundreds of members; if one is, it is flagged `over-merged`, which is a
      report of a threshold problem rather than a finding
- [ ] Each group states its load-bearing links and the weakest of them, or says
      that every member is held by at least two independent routes
- [ ] **The model** lists every dimension, and marks each family as either able
      to establish a link or corroboration-only. Spatial and temporal must be
      corroboration-only — otherwise "two people in one city" becomes a finding
- [ ] **How well this works** shows three precision figures. If it ever shows
      one, the number is either flattering or falsely modest: an unlabelled link
      is not a wrong link, and the report has to say so
- [ ] The storyline table keeps the four planted phenomena correlation cannot
      reach, with the reason for each. Removing them would inflate every
      aggregate above
- [ ] An entity profile shows **ARGUS correlations** under the assessment, with
      the same reasons and the same blind spots
- [ ] A subject with no correlations says so, rather than filling the panel with
      the nearest few entities
- [ ] Re-correlate as an investigator → a run is queued; an analyst gets 403,
      an administrator gets 403 even on reads
- [ ] Stop Neo4j and trigger a run → the run is recorded as **failed** with the
      reason, and the previous generation of links is untouched

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
- [ ] **No surface computes anything from the generator's risk score.** The
      dashboard distribution, the browse filter, the map shading, the graph
      seeds and the lead queue all read ARGUS's own band
- [ ] Every score is displayed with its evidence coverage. A score without a
      denominator anywhere is a regression
- [ ] The band counts sum to the population, `insufficient_evidence` included —
      it is usually the largest bucket, and it is not a low-risk finding
- [ ] No surface presents `storyline_id` or `flagged` as a discovered finding
- [ ] **No correlation is drawn from a planted link.** `CONTROLS`,
      `SHARES_DEVICE`, `INVOLVES` and `LINKED_TO` join exactly the entities a
      storyline created together, and no dimension may read one. A dimension
      that did would post near-perfect precision and have discovered nothing
- [ ] Cycle detection finds rings by value preservation, not by
      `r.flagged = true`. The old filter returned only planted rings and could
      not have found an unplanted one
- [ ] A person is never correlated with an account they hold. That is one
      subject seen twice, and reporting it as a discovery is how a correlation
      count gets inflated by an order of magnitude

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
