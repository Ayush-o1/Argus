# Database

Scope: the Neo4j schema — labels, relationships, properties, indexes, and the reasoning behind the graph design — plus the PostgreSQL schema that holds identity, audit and provenance. For how graph data is generated, see [generator.md](generator.md). For how it's queried, see [backend.md](backend.md) and [api.md](api.md).

Two datastores, with a clear division: **Neo4j** is authoritative for entities and the relationships between them; **PostgreSQL** holds records that must be immutable, which Neo4j Community cannot enforce (see [architecture.md](architecture.md)).

Neo4j Community Edition 5 + the Graph Data Science (GDS) plugin, self-hosted via `docker-compose.yml`.

## Migrations

Both schemas are managed by **numbered, forward-only migrations applied at startup**, not as a side effect of running the generator:

- `backend/app/database/migrations/` — Neo4j. Each migration is a list of statements plus an optional pre-flight `check`; applied state is recorded on a `:SchemaVersion` node.
- `backend/app/database/pg_migrations/` — PostgreSQL, plain `.sql` files applied inside a transaction each, tracked in `schema_migrations`.

A failure in either aborts startup deliberately: serving requests against a half-migrated schema risks wrong answers, and a half-applied privilege change is a security hole rather than an inconsistency.

This replaced schema creation inside the generator. The generator's default path **wipes and rebuilds the graph**, so requiring a generator run to acquire an index meant no deployed instance could change its schema without destroying its data.

## Node labels

| Label | Human ID field | Name/display field | Written by |
|---|---|---|---|
| `Person` | `person_id` (`PRS-0000442`) | `name` | `person_generator.py` |
| `Organization` | `org_id` (`ORG-0000123`) | `name` | `organization_generator.py` |
| `Account` | `account_id` (`ACC-0000771`) | — (`account_id` doubles as name) | `account_generator.py` |
| `Device` | `device_id` | — (`device_id` doubles as name) | `device_generator.py` |
| `Vehicle` | `vehicle_id` | `plate` | `vehicle_generator.py` |
| `Location` | `location_id` | `name` | `world_generator.py` |
| `Event` | `event_id` | — (`type` doubles as name) | `event_generator.py` |
| `Document` | `doc_id` | — (`doc_id` doubles as name) | `document_generator.py` |
| `Shipment` | `shipment_id` | — (`shipment_id` doubles as name) | `shipment_generator.py` |
| `Incident` | `incident_id` | — (`type` doubles as name) | `storyline_generator.py` |
| `Case` | `case_id` | `title` | `case_generator.py` |
| `Storyline` | `storyline_id` | — (`type` doubles as name) | `storyline_generator.py` |

Placed entities (`Person`, `Organization`, `Location`) additionally carry `country`, `country_code` and `region` alongside `city`/`state`, so the graph can be rolled up geographically without joining against a separate reference table — this is what `/api/map/regions` and `/api/map/countries` aggregate over. `Shipment` carries `origin_region`, `destination_region`, `lane`, `anomaly_kind`, `detour_ratio`, `distance_km` and a nullable `via_id`.

Every node also carries an opaque `id` property (a UUID4 string) — this is the node's true primary key, unique-constrained (see below), and what every relationship pattern matches on internally. The human-readable ID (`person_id`, `account_id`, ...) is what the API and UI expose to users; `backend/app/repositories/entity_labels.py` maps the ID's string prefix (`PRS`, `ACC`, ...) back to a label and field name so a route can resolve `/api/entities/PRS-0000442` without knowing the label ahead of time.

`Transaction` and `Communication` are **not node labels** — see [architecture.md#why-transactionscommunications-are-edge-properties-not-nodes](architecture.md#why-transactionscommunications-are-edge-properties-not-nodes). `Alert` is not a graph label at all: alerts live in PostgreSQL (`alerts`, `alert_occurrences`, `alert_groups`, `alert_transitions`, `alert_suppressions`), because they need transactions, constraints and an attributable history. They were a filtered view over `Incident` until Phase 7; see `backend/app/alerting/evidence.py` for why that had to change.

## Relationships

| Type | From → To | Notable properties | Purpose |
|---|---|---|---|
| `OWNS_ACCOUNT` | Person\|Organization → Account | — | Ownership |
| `OWNS_VEHICLE` | Person\|Organization → Vehicle | — | Ownership |
| `OWNS_DEVICE` | Person → Device | — | Ownership |
| `DIRECTS` | Person → Organization | `role`, `since` | Corporate directorship |
| `EMPLOYED_BY` | Person → Organization | `role`, `start_date` | Employment (independent of directorship) |
| `CONTROLS` | Person → Organization | `confidence` | Informal/illicit control — only created by storyline injection (shell company rings) |
| `SHARES_DEVICE` | Person → Person | `device_id`, `period` | Two people using the same physical device — only created by the Identity Overlap storyline |
| `TRANSACTED_WITH` | Account → Account | `tx_id`, `amount`, `currency`, `type`, `timestamp`, `flagged`, `storyline_id` | Money movement — the edge the entire Analytics Engine operates on |
| `COMMUNICATED_WITH` | Device → Device | `comm_id`, `type`, `timestamp`, `duration_seconds`, `flagged`, `storyline_id` | Contact — the edge the communication-cluster analysis operates on |
| `ATTENDED` | Person → Event | — | Event participation |
| `OCCURRED_AT` | Event → Location | — | Event location |
| `ISSUED_TO` | Document → Person | — | Document subject |
| `ISSUED_BY` | Document → Person\|Organization | — | Document issuer |
| `INVOLVES` | Incident → any entity | — | Resolved from `Incident.involved_entity_ids` at write time |
| `LINKED_TO` | Case → any entity | `reason`, `added_at` | Case evidence board — the only relationship type created/removed at runtime by the API (`case_repo.add_entity_to_case` / `remove_entity_from_case`), everything else is generator-written |

Every relationship except `LINKED_TO` is created once by the generator and never mutated by the running application. `TRANSACTED_WITH` and `COMMUNICATED_WITH` carry a `storyline_id` (nullable) that attributes injected anomalous activity back to the `Storyline`/`Incident` that planted it — this is ground truth for evaluating detection, not something the detector reads (see [analytics.md](analytics.md#relationship-to-ground-truth)).

## Constraints and indexes

Created by migration 001 (`backend/app/database/migrations/runner.py`). The generator also creates them idempotently on a full world build, so a freshly generated graph is usable before the backend has ever started:

```cypher
-- One per node label in NODE_SPECS
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Person) REQUIRE n.id IS UNIQUE
-- ... repeated for Organization, Location, Vehicle, Device, Account, Event,
--     Shipment, Document, Incident, Case, Storyline

-- And one per *human* ID, added by migration 001. These are the keys the API
-- actually looks entities up by; without them every lookup was a label scan
-- (NodeByLabelScan rather than NodeUniqueIndexSeek), and nothing prevented two
-- nodes sharing a human ID — which concurrent case creation could and did
-- produce, permanently breaking the affected case's detail page.
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Person) REQUIRE n.person_id IS UNIQUE
-- ... repeated for org_id, account_id, device_id, vehicle_id, doc_id,
--     shipment_id, event_id, location_id, case_id, incident_id, storyline_id

CREATE FULLTEXT INDEX entity_name IF NOT EXISTS
FOR (n:Person|Organization|Location|Vehicle) ON EACH [n.name]

CREATE INDEX person_risk  IF NOT EXISTS FOR (n:Person) ON (n.risk_score)
CREATE INDEX org_risk     IF NOT EXISTS FOR (n:Organization) ON (n.risk_score)
CREATE INDEX person_city  IF NOT EXISTS FOR (n:Person) ON (n.city)
CREATE INDEX event_time   IF NOT EXISTS FOR (n:Event) ON (n.timestamp)
CREATE INDEX incident_status IF NOT EXISTS FOR (n:Incident) ON (n.status, n.severity)
```

The uniqueness constraint on `id` is what every Cypher `MATCH` in the backend relies on being index-backed — `backend/app/repositories/graph_repo.py`'s module docstring calls this out explicitly: no full graph scans in user-facing read paths. `entity_name` backs global search (`/api/search`, `graph_repo.search_entities`, Lucene-style fuzzy match via `~`). `person_risk`/`org_risk`/`person_city` back entity-list filtering. `incident_status` backs the Alerts queue.

## Typical queries

Resolve a human ID to a node (every entity-detail route starts here):

```cypher
MATCH (n:Person {person_id: $human_id})
OPTIONAL MATCH (n)-[r]-()
RETURN n, labels(n)[0] AS label, count(r) AS degree
```

Bounded neighborhood expansion (Graph Explorer) — implemented as repeated 1-hop queries per BFS layer rather than one variable-length Cypher pattern, specifically to avoid exploding through high-degree hub nodes like shared Accounts or Devices:

```cypher
MATCH (n:Person {person_id: $human_id})-[r]-(m)
RETURN n, r, m, labels(m)[0] AS other_label, type(r) AS rel_type,
       startNode(r) = n AS outgoing
LIMIT $limit
```

Shortest path between two arbitrary entities (bounded to 8 hops so it can't hang):

```cypher
MATCH (a:Person {person_id: $from_id})
MATCH (b:Organization {org_id: $to_id})
MATCH path = shortestPath((a)-[*..8]-(b))
RETURN path
```

Circular money-movement detection (laundering-ring signature) — variable-length bounds must be Cypher literals, not parameters, so they're f-string-interpolated (safe here: both are backend-typed ints, never raw user input):

```cypher
MATCH path = (a:Account)-[rels:TRANSACTED_WITH*3..6]->(a)
WHERE any(r IN rels WHERE r.flagged = true)
WITH path, rels LIMIT $limit
RETURN [n IN nodes(path) | n.account_id] AS account_ids, length(path) AS length,
       reduce(total = 0.0, r IN rels | total + r.amount) AS total_amount
```

See [analytics.md](analytics.md) for the GDS graph-projection queries (PageRank, Betweenness, Louvain, Node2Vec) built on top of this schema.

## Expected graph shape (default generator scale)

| Entity | Count |
|---|---|
| Person | 4,000 |
| Organization | 400 |
| Location | 600 |
| Vehicle | 900 |
| Device | 1,500 |
| Account | 2,800 |
| Transaction (edges) | 40,000 |
| Event | 6,000 |
| Communication (edges) | 15,000 |
| Shipment | 1,200 |
| Document | 2,000 |
| Storyline / Incident | 15 each |

~20K nodes, ~90K relationships total. Fully configurable via `generator/config.py`'s `ScaleConfig` — see [generator.md](generator.md#scale-configuration).

## Design rationale summary

- **UUID `id` as the real primary key, human-readable ID as the display key** — lets every internal Cypher pattern and relationship match stay stable even though the human ID scheme (`PRS-0000442`) encodes a sequential counter that the Scenario Generator has to extend without collision (see [generator.md#id-offsets](generator.md#id-offsets)).
- **Edge properties over intermediate nodes for Transaction/Communication** — see [architecture.md](architecture.md#why-transactionscommunications-are-edge-properties-not-nodes).
- **Alerts in PostgreSQL, not the graph** — an alert is a work item with a current state, an assignee and an occurrence count, plus a complete history of every firing and every state change. Postgres gives that transactions, CHECK constraints and append-only triggers; Neo4j Community gives none of them. The graph stays authoritative for entities and relationships, and the alerting tables reference subjects by ref rather than by edge.
- **`Incident` is no longer an alert** — it remains in the graph as a record reported by a source. Conflating it with the alert queue meant the queue was the scenario generator's own storyline summaries, re-read and presented as findings.
- **Idempotent constraint/index creation** — since `write_world` wipes and rebuilds the graph by default (`wipe_existing=True`), constraints must survive a fresh `CREATE` pass without erroring on re-creation; `IF NOT EXISTS` makes this safe to run repeatedly, in both the generator and the migration runner.

## PostgreSQL schema

Three groups of tables, all in one database.

**Identity** — `users` (Argon2id hash, role, TOTP secret, lockout state) and `sessions` (token stored only as a SHA-256 hash, so a database read does not yield a usable credential, with separate absolute and idle expiry).

**Audit** — `audit_events`: append-only and hash-chained. Each row carries `prev_hash` and `entry_hash`, so removing or altering a row breaks the chain from that point and the break is detectable by recomputation (`python -m app.cli verify-audit`). Audit writes share the mutation's transaction, so an action cannot succeed while its record is lost.

**Provenance** — the observation/assertion split:

| Table | Holds |
|---|---|
| `sources` | Every source, including ARGUS's own generator. Admiralty reliability `A`–`F` with a required stated basis, an `is_synthetic` flag, and an `independence_group` so two feeds reprinting one wire service count as one voice. |
| `observations` | What a source said. Immutable. Keyed by `(source_id, content_hash)` so re-ingesting the same payload yields one row rather than inflating corroboration. Three separate timestamps — `occurred_at`, `collected_at`, `recorded_at` — of which only the last is `NOT NULL`, because only the last is knowable in every case. |
| `observation_subjects` | Which entities an observation is about. |
| `assertions` | What ARGUS or an analyst *believes*: subject, predicate, object, epistemic kind (`observed`/`reported`/`inferred`/`assessed`), and the two rating axes as separate `CHAR(1)` columns. Content is immutable; only supersession and retraction may be set, once, and never cleared. |
| `assertion_evidence` | The observations for **and against** an assertion. Counter-evidence is recorded rather than discarded — an assertion whose contradicting evidence was dropped looks better supported than it is. |

Reliability and credibility are stored as characters, not integers, on purpose: a numeric encoding invites arithmetic on an ordinal scale where A→B is not the same distance as E→F, and nothing establishes that it is.

**Ingestion** — the pipeline's working state and its evidence:

| Table | Holds |
|---|---|
| `job_queue` | Durable jobs. Claimed with `SELECT ... FOR UPDATE SKIP LOCKED` under a *lease* rather than a lock, so a worker that dies costs one visibility timeout instead of the job. Delivery is at-least-once, which is why handlers must be idempotent. |
| `connectors` | One row per configured feed: type, config, record mapping, poll interval, cursor, quarantine state. Adding a source is an INSERT. **Credentials are never stored here** — config may *name* an environment variable, never carry a value. |
| `ingest_batches` | One row per fetch attempt, with per-batch counts. Source health is computed from this table rather than kept in counters, so the numbers cannot drift from the events they describe. |
| `raw_records` | What arrived, exactly as it arrived. Immutable, unique on `(connector_id, content_hash)`. This is what makes replay possible: a pipeline that discards its input can only ever be fixed going forward. |
| `ingest_failures` | The dead-letter queue: stage, error, and the payload it refers to. Immutable except for its resolution. |
| `connector_field_stats` | Every field a source has ever sent. A source that quietly renames or drops one does not error — it just stops populating something, and every derived figure silently degrades. |

**Entity resolution** — the ledger, and the projections derived from it:

| Table | Purpose |
|---|---|
| `resolution_runs` | One row per sweep, with the model fingerprint it ran under and a blocking report: how many records no key could place, and which keys matched so many records they stopped discriminating. A silent loss of recall is the one failure in this pipeline that leaves no other trace. |
| `resolution_candidates` | A scored pair with **every** attribute comparison kept, including the ones that could not be made — storing only the agreements would produce a review screen that argues for the merge and never against it. `score` is nullable: a pair with nothing comparable has no score, and `0.0` would say "definitely different". `evidence_weight` is its denominator. One row per pair, with `left_ref < right_ref` enforced. |
| `resolution_decisions` | **The record.** Append-only, enforced by trigger for every role. There is no `active` column: the current decision for a pair is simply the highest `decision_id`, so reversing a merge is an INSERT and nothing is ever rewritten. Both entity records are untouched throughout, which is why a merge is reversible without a restore. |
| `resolution_clusters`, `resolution_cluster_members` | Connected components over active merges — a **derived cache**, safe to drop and rebuild from the ledger. A component containing a pair judged different is flagged `contested` with a stated reason; ARGUS does not choose which decision to discard. |
| `resolution_canonical_pins` | An analyst's choice of which record represents a cluster. Pinned by ref rather than by cluster, because cluster identity changes as members join while the judgement about the record does not. |
| `resolution_blocking_index` | Which coarse keys each record falls under. Exists for the single-record path: when a feed delivers a subject ARGUS does not hold, one indexed lookup per key answers "is this anyone we already have?" without scoring against the whole population. |
| `resolution_labels`, `resolution_evaluations` | Ground truth and the measurements taken against it, both append-only. A precision figure computed against a set that can be quietly edited is a claim, not a measurement. |

Nothing in the resolution schema can modify or delete an entity. There is no
`merged_into` column, no tombstone, no surviving-record pointer — the acceptance
criterion *"a merge never destroys either source record"* is a property of the
data model rather than of careful coding.

### How immutability is enforced

Two independent layers, because either alone is weaker than it looks:

1. **Grants.** The application role holds `INSERT` and `SELECT` on `audit_events`, `observations`, `observation_subjects` and `assertion_evidence`, and nothing else. It never holds `UPDATE` or `DELETE` on them.
2. **Triggers.** `BEFORE UPDATE/DELETE/TRUNCATE` triggers raise `insufficient_privilege` for **every** role, including the superuser. `TRUNCATE` needs its own statement-level guard because it bypasses row-level triggers entirely.

`assertions` is the one narrower case: a belief must be able to *end*. `UPDATE` is permitted for exactly four lifecycle columns, only in the direction unset → set, enforced by an explicit column-by-column trigger. It is written as an explicit list rather than a blanket comparison so that a column added later fails closed.

Removing a row during development required connecting as superuser *and* explicitly disabling a trigger — two deliberate acts, which is the point.
