# Database

Scope: the Neo4j schema — labels, relationships, properties, indexes, and the reasoning behind the graph design. For how this data is generated, see [generator.md](generator.md). For how it's queried, see [backend.md](backend.md) and [api.md](api.md).

Neo4j Community Edition 5 + the Graph Data Science (GDS) plugin, self-hosted via `docker-compose.yml`. No separate schema-migration tool — the schema is created idempotently by `generator/generators/neo4j_writer.py` (`_create_constraints`, `_create_search_and_range_indexes`) every time the generator runs.

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

Every node also carries an opaque `id` property (a UUID4 string) — this is the node's true primary key, unique-constrained (see below), and what every relationship pattern matches on internally. The human-readable ID (`person_id`, `account_id`, ...) is what the API and UI expose to users; `backend/app/repositories/entity_labels.py` maps the ID's string prefix (`PRS`, `ACC`, ...) back to a label and field name so a route can resolve `/api/entities/PRS-0000442` without knowing the label ahead of time.

`Transaction` and `Communication` are **not node labels** — see [architecture.md#why-transactionscommunications-are-edge-properties-not-nodes](architecture.md#why-transactionscommunications-are-edge-properties-not-nodes). `Alert` is also not a separate label — alerts are a filtered view over `Incident` (severity `High`/`Critical`); see `backend/app/repositories/alert_repo.py`.

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

Created in `neo4j_writer.py`, idempotently (`IF NOT EXISTS`), every time `write_world` runs:

```cypher
-- One per node label in NODE_SPECS
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Person) REQUIRE n.id IS UNIQUE
-- ... repeated for Organization, Location, Vehicle, Device, Account, Event,
--     Shipment, Document, Incident, Case, Storyline

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
- **Alerts as a filtered Incident view, not a separate label** — the machine (generator's rule-based scorer, or the storyline injector) creates `Incident`; the analyst reviews and updates `Incident.status` through the same node. There is no separate write path to keep in sync.
- **Idempotent constraint/index creation on every generator run** — since `write_world` wipes and rebuilds the graph by default (`wipe_existing=True`), constraints must survive a fresh `CREATE` pass without erroring on re-creation; `IF NOT EXISTS` makes this safe to run repeatedly.
