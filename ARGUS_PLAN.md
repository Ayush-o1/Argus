# ARGUS — Full Product Architecture & Research Proposal

> **Status**: Historical design proposal. All phases described below have been built — see [`docs/`](docs/) for current, maintained technical documentation. Phase 16's checklists (near the end of this file) are kept up to date with actual build status. This document is retained for its original architecture rationale and phase-by-phase reasoning, not as a live spec.
> **Scope**: 100% Synthetic Data — Educational Engineering Portfolio Project
> **Tagline**: *"See everything. Understand the connections."*

---

## TABLE OF CONTENTS

1. [Phase 1 — Product Vision](#phase-1--product-vision)
2. [Phase 2 — Competitive Research](#phase-2--competitive-research)
3. [Phase 3 — Feature Research](#phase-3--feature-research)
4. [Phase 4 — The Synthetic World (VERIDIA)](#phase-4--the-synthetic-world-veridia)
5. [Phase 5 — Information Architecture](#phase-5--information-architecture)
6. [Phase 6 — Page-by-Page UX Design](#phase-6--page-by-page-ux-design)
7. [Phase 7 — Data Model & Ontology](#phase-7--data-model--ontology)
8. [Phase 8 — Synthetic Data Generation Engine](#phase-8--synthetic-data-generation-engine)
9. [Phase 9 — Graph Analytics Engine](#phase-9--graph-analytics-engine)
10. [Phase 10 — AI Features](#phase-10--ai-features)
11. [Phase 11 — Technology Stack](#phase-11--technology-stack)
12. [Phase 12 — Design System](#phase-12--design-system)
13. [Phase 13 — System Architecture](#phase-13--system-architecture)
14. [Phase 14 — Folder Structure](#phase-14--folder-structure)
15. [Phase 15 — Performance Strategy](#phase-15--performance-strategy)
16. [Phase 16 — Development Roadmap](#phase-16--development-roadmap)
17. [Phase 17 — Risks & Mitigations](#phase-17--risks--mitigations)
18. [Phase 18 — Future Scope](#phase-18--future-scope)
19. [Phase 19 — Final Recommendation](#phase-19--final-recommendation)

---

## PHASE 1 — PRODUCT VISION

### What Is ARGUS?

**ARGUS** is a synthetic intelligence analysis simulator. It is an interactive, full-stack platform designed to demonstrate how modern analytical systems model connected data — entities, relationships, events, and patterns — at scale.

ARGUS operates entirely on a procedurally generated fictional world. No real people, no real companies, no real data of any kind.

The system answers one fundamental engineering question:

> *"What does it look like when an analyst can see an entire world as a connected graph — and reason through it?"*

---

### The Core Problem ARGUS Solves (in the fictional world)

ARGUS exists inside a fictional jurisdiction: **the India**. The fictional problem it solves:

India's **Office of Strategic Intelligence (OSI)** manages thousands of entities — people, companies, vehicles, financial accounts, communications networks, events, and locations — all interacting in ways that produce patterns. Some patterns are routine. Some are anomalies. Some suggest organized collusion, resource laundering, or supply-chain manipulation.

Traditional relational databases show rows. **ARGUS shows the graph.** It reveals the invisible scaffolding connecting entities that would otherwise appear unrelated.

---

### Who Uses ARGUS (Fictional Persona)

| Persona | Role | Primary Workflow |
|---|---|---|
| **Analyst** | Reviews flagged anomalies, traces paths | Graph Explorer, Timeline, Entity Profiles |
| **Case Manager** | Manages active investigations | Case Workspace, Alerts, Reports |
| **Data Scientist** | Runs algorithms, validates scores | Analytics, Scenario Generator |
| **Administrator** | Manages system config | Settings, Developer, Data Status |

---

### Why ARGUS Feels Different

Most portfolio projects show CRUD apps or dashboards with static charts. ARGUS demonstrates:

- **Graph thinking** — relationships as first-class data
- **Entity resolution** — merging duplicate synthetic records intelligently
- **Temporal reasoning** — events across time, not just at a point in time
- **Risk propagation** — how a flagged entity contaminates connected nodes
- **Investigation workflow** — hypothesis → exploration → evidence → report
- **Local-first intelligence** — graph algorithms and ML doing the reasoning, not LLM theater

This is not a demo. It's a simulation of a real analytical system.

---

## PHASE 2 — COMPETITIVE RESEARCH

### What We Studied

We analyzed the following categories of software at an **architectural and workflow level** (not visual design):

| Category | Systems Studied |
|---|---|
| Intelligence Platforms | Palantir Gotham, Palantir Foundry, i2 Analyst's Notebook |
| Graph Analytics | Neo4j Bloom, Linkurious, TigerGraph, Memgraph |
| Fraud Investigation | Lucinity, FICO, Featurespace, DataWalk |
| Geospatial | Esri ArcGIS, Mapbox Studio, Google Earth Pro |
| Investigation Case Management | IBM i2, Nuix, Relativity |
| Knowledge Graphs | Stardog, Ontotext, Franz AllegroGraph |
| Command Centers | Splunk, Elastic SIEM, Palo Alto Cortex XDR |

---

### Key Insight: Why These Platforms Work

The platforms that analysts love share one architectural truth:

> **The entity is the atom, not the event or the record.**

Traditional systems ask: "Show me all transactions on this date."
Intelligence platforms ask: "Show me everything connected to this person — across time, across systems."

The shift is from **row-centric** to **entity-centric**. This changes everything:
- Navigation centers on entities, not tables
- Search returns entities with contextual connections, not lists of rows
- Filters operate on graph properties, not column values
- Visualizations show neighborhoods, not aggregates

---

### What ARGUS Takes From Each

| Source | What We Adopt | What We Deliberately Avoid |
|---|---|---|
| Palantir Gotham | Entity-centric model, investigation pivoting, pathfinding workflow | Their visual language, color palette, sidebar structure |
| i2 Analyst's Notebook | Link chart UX, temporal layout, relationship metadata | Their legacy desktop feel |
| Linkurious | Graph canvas UX, progressive node expansion | Their flat card design |
| Lucinity | Human-in-the-loop confirmation workflow, risk scoring UI | Their compliance-first heavy interface |
| Neo4j Bloom | Node labels, color coding, graph legend | Their developer-tool appearance |
| Linear | Typography, micro-animation, keyboard-first UX | Nothing — we adopt this fully |
| Apple HIG | Clarity, deference, depth principles, semantic color tokens | Overly soft pastels |
| Vercel Dashboard | Dark surface palette, card elevation, monospace stats | Their purely developer-focused hierarchy |

---

### What Makes ARGUS Different From All of Them

ARGUS is not a real product. It is an **engineered simulation** with a single, clear purpose: demonstrate excellence.

That means:
- Every page has a reason to exist
- Every feature demonstrates a real engineering decision
- The synthetic world is internally consistent and explorable
- The codebase is clean, layered, and readable

---

## PHASE 3 — FEATURE RESEARCH

### The Investigation Lifecycle (Workflow)

Every feature in ARGUS maps to a stage in this investigation lifecycle:

```
ALERT DETECTED
      │
      ▼
ENTITY IDENTIFIED ──────► ENTITY PROFILE VIEW
      │
      ▼
CONNECTIONS EXPLORED ────► GRAPH EXPLORER
      │
      ▼
TIMELINE ANALYZED ───────► TIMELINE VIEW
      │
      ▼
GEOGRAPHY EXAMINED ──────► MAP VIEW
      │
      ▼
PATTERNS DETECTED ───────► ANALYTICS ENGINE
      │
      ▼
CASE OPENED ─────────────► CASE WORKSPACE
      │
      ▼
REPORT GENERATED ────────► AI REPORT + EXPORT
```

Every page in ARGUS corresponds to a specific stage. No page exists without a clear workflow reason.

---

### Core Feature Matrix

| Feature | Why It Exists | Complexity |
|---|---|---|
| Graph Explorer | Core analytical surface — visualize entity networks | ★★★★★ |
| Entity Profiles | Deep dive into a single entity with all connections | ★★★★☆ |
| Timeline View | Temporal pattern analysis across events | ★★★★☆ |
| Map View | Geospatial co-location and movement analysis | ★★★★☆ |
| Case Workspace | Collaborative investigation management | ★★★★☆ |
| Analytics Dashboard | Risk scores, community detection, centrality | ★★★★☆ |
| Search | Global entity + event search with facets | ★★★☆☆ |
| Alerts | System-detected anomalies requiring review | ★★★☆☆ |
| Scenario Generator | Create synthetic cases on demand | ★★★☆☆ |
| Local Intelligence Layer | Anomaly detection, template narratives, optional local assistant | ★★★☆☆ |
| Settings | Theme, data config, system status | ★★☆☆☆ |
| Help / Docs | In-app documentation | ★☆☆☆☆ |

---

## PHASE 4 — THE SYNTHETIC WORLD

> **[v2 REVISION]** V1 of this plan invented a wholly fictional country ("Republic of Veridia"). That conflicted with the project's actual goal: a world that *feels relatable* to the person building and showing it. V2 grounds ARGUS in **real Indian geography** (real cities, states, coordinates) while keeping **every entity — every person, company, phone number, account, and transaction — 100% procedurally generated and fictional.** No real individual, real company, or real record is ever represented. This is the same pattern real-world training/demo datasets use (real geography, synthetic subjects) and it is what makes the world feel grounded without touching anyone's real identity.

### ARGUS World: Overview

ARGUS is framed as the internal analysis platform of the **Office of Strategic Intelligence (OSI)** — a fictional, invented analytical unit (not a real agency, and not modeled on any specific real agency's identity or branding) that operates, for the purposes of this simulation, across India. The world is deterministic and seeded — the same seed number always produces the same synthetic population, organizations, and event history.

| Attribute | Value |
|---|---|
| Setting | India (real geography — cities, states, coordinates) |
| Fictional Unit | Office of Strategic Intelligence (OSI) — entirely invented, generic in name and mandate |
| Cities Modeled | Bengaluru, Mumbai, Delhi, Hyderabad, Pune, Ahmedabad, Chennai, Jaipur, Lucknow, Patna |
| States Modeled | Karnataka, Maharashtra, Delhi (NCT), Telangana, Gujarat, Tamil Nadu, Rajasthan, Uttar Pradesh, Bihar |
| Currency | Indian Rupee (₹ / INR) — real currency unit, entirely synthetic amounts |
| Synthetic Telecom Operators | Saffron Mobility, Aether Telecom, NordLink Wireless |
| Synthetic Banks | Surya FinTech Bank, Narmada Cooperative Bank, + 4 other invented banks |
| Synthetic Energy Grid | Bharat Energy Systems (BES) |
| Synthetic Logistics/Transport | Shakti Logistics Pvt Ltd, Astra Freight Lines, regional port/rail authorities (invented) |
| Synthetic Healthcare Networks | Zenith Healthcare India + 2 other invented networks |

**Naming pool** for generated persons and organizations follows the examples in the project brief (e.g. Priya Sharma, Arjun Singh, Rohan Patel, Ananya Iyer; Shakti Logistics, Surya FinTech, Astra Manufacturing) — expanded programmatically by the Faker-based generator (Phase 8) into thousands of unique combinations, never reusing a real person's or real company's actual identity.

---

### The Entities We Generate

> **[v2 REVISION]** V1 defaulted to 50,000 persons / 500,000 transactions. Since we're building **local-first** (per the deployment decision), the default world is sized to load and query instantly on a laptop while still being rich enough to demonstrate real graph depth — dense enough that community detection, cycles, and shortest-path all produce genuinely interesting results. The generator remains fully configurable up to (and beyond) the original scale for anyone who wants to stress-test it.

#### PRIMARY ENTITIES (Nodes) — Default Demo Scale

| Type | Count (Default) | Count (Stress-test max) | Key Properties |
|---|---|---|---|
| **Person** | 4,000 | 500,000 | name, dob, gender, occupation, city, state, risk_score, status |
| **Organization** | 400 | 50,000 | name, type, industry, registered_city, risk_score |
| **Location** | 600 | — | name, type, city, coordinates (real city, synthetic point), region |
| **Vehicle** | 900 | — | plate, type, make, model, registered_to, color |
| **Device** | 1,500 | — | device_id, type, IMEI (synthetic), MAC (synthetic) |
| **Account** | 2,800 | — | account_id, bank, type, balance_class, status |
| **Transaction** | 40,000 | 5,000,000 | tx_id, amount (INR), timestamp, from_account, to_account, type |
| **Event** | 6,000 | — | event_id, type, timestamp, location, participants |
| **Communication** | 15,000 | 2,000,000 | comm_id, type, from_device, to_device, timestamp, duration |
| **Shipment** | 1,200 | — | shipment_id, origin, destination, carrier, manifest, status |
| **Document** | 2,000 | — | doc_id, type, issuer, subject, issued_date |
| **Incident** | 250 | — | incident_id, type, severity, timestamp, involved_entities |
| **Case** | 40 | — | case_id, status, assigned_analyst, linked_entities, opened_at |

At default scale this produces roughly **75K nodes and 250K+ relationships** — large enough for PageRank, Louvain, and cycle detection to be genuinely interesting, small enough to generate in seconds and query with no perceptible latency on a single machine.

---

### The Synthetic Incidents (Storylines)

The generator creates several types of synthetic "storylines" — clusters of entities that are deliberately entangled:

| Storyline Type | Description |
|---|---|
| **Shell Company Ring** | 3–8 organizations linked through shared directors and circular transactions |
| **Money Routing Network** | A chain of accounts moving synthetic funds through multiple banks |
| **Communication Cluster** | A group of devices and persons with suspiciously dense communication patterns |
| **Supply Chain Divergence** | Shipments whose stated route doesn't match GPS waypoints |
| **Document Forgery Ring** | Synthetic documents with mismatched issuer/subject relationships |
| **Identity Overlap** | Synthetic persons who share devices, addresses, or accounts |
| **Anomalous Transaction Burst** | An account with a sudden deviation from its historical pattern |

Each storyline is tagged with a `severity` (Low, Medium, High, Critical) and a `discovery_difficulty` score — some are obvious, some are buried.

---

### Geography

```
India — Cities Modeled (real coordinates, synthetic activity)
───────────────────────────────────────────────────────────────
  Delhi ●            Lucknow ●         Patna ●
        (North)             (North)          (East)

  Jaipur ●
        (West)

  Ahmedabad ●        Mumbai ●          Pune ●
        (West)             (West)            (West)

  Hyderabad ●        Bengaluru ●       Chennai ● (Port City)
        (South)            (South)           (South)
```

Every city sits at its real latitude/longitude. Every *person, organization, vehicle, and event* placed within it is entirely synthetic — real geography, fictional subjects. Locations within a city (offices, warehouses, ports) are synthetic points jittered around the city's real center, not real addresses.

---

## PHASE 5 — INFORMATION ARCHITECTURE

### Navigation Philosophy

ARGUS follows a **dual-axis navigation model**:

- **Primary Axis (Sidebar)**: Workflow stages — where am I in the investigation?
- **Secondary Axis (Topbar)**: Context — what am I currently looking at?

The sidebar is always visible but collapsible. The topbar shows breadcrumbs and active investigation context.

---

### The 13 Pages of ARGUS

After careful elimination of unnecessary pages, ARGUS contains exactly **13 pages** — no more, no fewer. Each exists for a specific workflow reason.

```
ARGUS Navigation Tree
─────────────────────
/                         → Redirects to /dashboard
/dashboard                → Command center overview
/graph                    → Graph explorer (full-screen canvas)
/search                   → Global entity search
/map                      → Geospatial view
/timeline                 → Temporal event analysis
/entities/:id             → Single entity profile
/cases                    → Case list
/cases/:id                → Single case workspace
/analytics                → Algorithm results, risk heatmaps
/alerts                   → System-detected anomalies
/scenario                 → Synthetic scenario generator
/settings                 → System configuration
```

**Eliminated pages (with reasons):**

| Eliminated | Reason |
|---|---|
| `/reports` (standalone) | Reports are generated inside `/cases/:id`. Standalone page creates redundancy. |
| `/admin` | Not needed — this is a single-user educational system. |
| `/simulation` (separate) | Simulation is a feature of `/scenario`, not a standalone page. |
| `/help` (standalone) | Replaced by in-app contextual tooltips and a slide-over help panel. |
| `/developer` | Debug panel accessible via keyboard shortcut, not a dedicated route. |

---

### Sidebar Structure

```
╔══════════════════════════════╗
║  ▲ ARGUS                     ║  ← Logo + System Name
╠══════════════════════════════╣
║  ● Dashboard          /dashboard
║  ○ Graph Explorer     /graph
║  ○ Search             /search
║  ○ Map                /map
║  ○ Timeline           /timeline
╠══════════════════════════════╣  ← Divider: Investigation
║  ○ Cases              /cases
║  ○ Alerts     [12]    /alerts  ← Badge for unreviewed count
║  ○ Analytics          /analytics
╠══════════════════════════════╣  ← Divider: Tools
║  ○ Scenario Generator /scenario
╠══════════════════════════════╣
║  ○ Settings           /settings
╚══════════════════════════════╝
```

---

### Topbar Structure

```
╔═════════════════════════════════════════════════════════════════╗
║  [← Back]  Dashboard  /  Case-007  /  Entity: Karan Malhotra        ║
║                                              [🔍 Search]  [?]  ║
╚═════════════════════════════════════════════════════════════════╝
```

---

## PHASE 6 — PAGE-BY-PAGE UX DESIGN

---

### PAGE 1: `/dashboard` — Command Center

**Purpose**: The mission control surface. An analyst opens ARGUS here every morning.

**Design Philosophy**: Five seconds to understand system state.

**Layout**: Three-column grid, 12-column base

```
╔══════════════════════════════════════════════════════════════════╗
║  [STAT] Active Cases   [STAT] Open Alerts   [STAT] Risk Score   ║
║  [STAT] New Entities   [STAT] Flagged Txns  [STAT] Graph Nodes  ║
╠══════════════════════════════╦═══════════════════════════════════╣
║  RECENT ACTIVITY FEED        ║  ALERT PRIORITY QUEUE             ║
║  • Entity flagged (2m ago)   ║  ▲ CRITICAL: Shell ring detected  ║
║  • Case-012 updated          ║  ▲ HIGH: Burst transaction        ║
║  • New incident logged       ║  ▲ MED: Overlapping devices       ║
╠══════════════════════════════╬═══════════════════════════════════╣
║  ENTITY RISK DISTRIBUTION    ║  INVESTIGATION TIMELINE (7 days) ║
║  [Donut chart by type]       ║  [Sparkline per case]             ║
╠══════════════════════════════╩═══════════════════════════════════╣
║  WORLD MAP SNAPSHOT — Recent geospatial activity               ║
║  [Mini deck.gl map — dots, clusters, heatmap option]           ║
╚══════════════════════════════════════════════════════════════════╝
```

**Components**:
- `StatCard` — animated counter on mount
- `ActivityFeed` — virtual scroll, real-time-feeling updates
- `AlertQueue` — priority-sorted, color-coded severity
- `RiskDonut` — Recharts pie chart with custom legend
- `WorldMapSnapshot` — deck.gl ScatterplotLayer + HeatmapLayer
- `InvestigationSparkline` — mini VisX area charts

**Interactions**:
- Clicking a stat card navigates to the relevant page with pre-filters applied
- Clicking an alert opens a slide-over panel with entity preview
- The map snapshot is interactive — clicking a cluster opens a filtered map view
- Activity feed items are clickable links into the entity or case

**Animations**:
- Stat numbers count up on load (spring animation, 600ms)
- Alert items slide in from the right with staggered delay
- Map dots pulse on the first render

---

### PAGE 2: `/graph` — Graph Explorer

**Purpose**: The primary analytical surface. The canvas where investigations live.

**Design Philosophy**: The graph IS the interface. Everything else is secondary.

**Layout**: Full-screen canvas with collapsible control panels

```
╔════════════════════════════════════════════════════════════╗
║ [Search/Filter Bar]  [Algorithms ▼]  [Layout ▼]  [Export] ║
╠════╦═══════════════════════════════════════════════════════╣
║    ║                                                       ║
║ C  ║                  GRAPH CANVAS                        ║
║ O  ║              (Cytoscape.js WebGL)                    ║
║ N  ║                                                       ║
║ T  ║    ● ── relationship ──► ●                           ║
║ R  ║         ╲                                            ║
║ O  ║          ●──►●                                       ║
║ L  ║                                                       ║
║ S  ╠═══════════════════════════════════════════════════════╣
║    ║  DETAIL PANEL (right slide-over when node selected)  ║
╚════╩═══════════════════════════════════════════════════════╝
```

**Control Panel (left collapsible)**:
- Entity type toggles (Person, Organization, Vehicle, Device...)
- Relationship type filter checkboxes
- Risk score range slider
- Date range filter
- Depth slider (1-hop, 2-hop, 3-hop expansion)

**Canvas Controls**:
- Zoom in/out (scroll or buttons)
- Fit-to-screen button
- Mini-map (bottom-right)
- Node count indicator
- Layout switcher: Force-directed, Hierarchical, Radial, Grid

**Node Selection → Right Panel**:
```
╔═══════════════════════════╗
║ ● Karan Malhotra              ║
║ Person | Risk: HIGH       ║
║ ──────────────────────    ║
║ 📋 Properties             ║
║ 🔗 12 Connections         ║
║ 📅 Last Activity: 3d ago  ║
║ ──────────────────────    ║
║ [View Full Profile]       ║
║ [Expand Neighbors]        ║
║ [Add to Case]             ║
║ [Run Algorithm]           ║
╚═══════════════════════════╝
```

**Algorithm Panel (top dropdown)**:
- Shortest Path (select two nodes)
- Community Detection (Louvain — color codes clusters)
- Centrality (node size = betweenness)
- Risk Propagation (flood-fill from flagged node)
- Cycle Detection (highlights circular paths)

**Interactions**:
- Double-click node → expand its neighbors (1-hop)
- Right-click → context menu (Expand, Pin, Hide, Add to Case)
- Drag nodes to reposition manually
- Ctrl+Click → multi-select
- "Lasso" draw tool for group selection
- Edge click → shows relationship metadata

**Animations**:
- Nodes appear with spring pop-in when added to canvas
- Edges draw themselves (animated stroke) on connection
- Community detection: nodes gently migrate to cluster centers (physics)
- Risk propagation: colored pulse wave emanates from source node

**Performance Strategy**:
- Initial render: max 500 nodes
- Expansion: load neighbors lazily via API
- WebGL renderer for >200 nodes
- Web Worker for layout calculation (no UI jank)

---

### PAGE 3: `/search` — Global Search

**Purpose**: Entry point when the analyst knows what they're looking for.

**Design Philosophy**: Instant, faceted, powerful — not a table with a filter box.

**Layout**: Two-panel (filters left, results right)

```
╔══════════════════════════════════════════════════════╗
║  🔍  Search entities, events, cases...               ║
╠═════════════╦════════════════════════════════════════╣
║  FILTERS    ║  RESULTS  (showing 1–20 of 4,328)      ║
║  ─────────  ║  ──────────────────────────────────    ║
║  Type:      ║  [Entity Card] Karan Malhotra · Person     ║
║  ○ Person   ║  Risk: HIGH · New Delhi · 12 links     ║
║  ○ Org      ║                                        ║
║  ○ Vehicle  ║  [Entity Card] Malhotra Overseas Trading · Org  ║
║  ○ Device   ║  Risk: CRITICAL · Shell Company        ║
║  ─────────  ║                                        ║
║  Risk:      ║  [Event Card] Money Transfer · Event   ║
║  LOW → HIGH ║  2024-11-03 · ₹45,000               ║
║  ─────────  ║                                        ║
║  City:      ║  [MORE RESULTS...]                     ║
║  Multi-sel  ║                                        ║
╚═════════════╩════════════════════════════════════════╝
```

**Features**:
- Full-text search across all entity types
- Keyboard-first: `⌘K` global shortcut
- Instant search (debounced 200ms)
- Faceted filtering (type, city, risk, date range, status)
- Result cards with entity-type icon, risk badge, key properties
- "Open in Graph" button on each result → launches graph with that entity as seed
- "Add to Case" action on each result

**Interactions**:
- Type-ahead suggestions appear in a dropdown (entities + cases)
- Filter changes are reflected in URL params (shareable/bookmarkable results)
- Result cards have hover-reveal action buttons
- Pressing Enter on a result opens the entity profile

---

### PAGE 4: `/map` — Geospatial View

**Purpose**: Understand the geographic dimension of entity activity.

**Design Philosophy**: The map IS the workspace. Controls live on top, not beside.

**Layout**: Full-screen MapLibre GL + deck.gl layers + floating control bar

```
╔═══════════════════════════════════════════════════════════════╗
║  [Layers ▼]  [Time Range ←──────→]  [Heatmap | Points | Arc] ║
║═══════════════════════════════════════════════════════════════║
║                                                               ║
║     [Custom dark MapLibre basemap — India, real geography]    ║
║                                                               ║
║   ● New Delhi  (cluster: 1,240)                              ║
║         ↕ arc connection                                      ║
║   ● Chennai     (cluster: 380)                                ║
║                                                               ║
╠═══════════════════════════════════════════════════════════════╣
║  [Timeline scrubber — bottom of map]                          ║
╚═══════════════════════════════════════════════════════════════╝
```

**Layers**:
- **Person Locations** — dots sized by activity density
- **Organization Headquarters** — building icon markers
- **Shipment Routes** — animated arc lines (deck.gl LineLayer)
- **Incident Locations** — severity-colored markers
- **Communication Density** — hexagonal heatmap

**Interactions**:
- Click marker/cluster → slide-over with entity list
- Layer toggles
- Time scrubber → filter all visible data by time window
- Hover arc → see shipment or communication metadata
- "Find Nearby" — click location → show all entities within radius
- Export visible data as a case attachment

---

### PAGE 5: `/timeline` — Temporal Analysis

**Purpose**: See patterns across time — event bursts, gaps, correlations.

**Design Philosophy**: Time is a dimension, not a filter.

**Layout**: Vertical swim-lane timeline

```
╔══════════════════════════════════════════════════════════════╗
║  [Entity Selector]  [Date Range]  [Event Types]  [Zoom ←──→] ║
╠══════════════════════════════════════════════════════════════╣
║  ENTITY: Karan Malhotra                                          ║
║  ────────────────────────────────────────────────────────    ║
║  │ NOV 01 │ NOV 05 │ NOV 10 │ NOV 15 │ NOV 20 │ NOV 25 │   ║
║  │   ●       ●●        ●         ●●●●●      ●     │         ║
║  │ TRANSACTIONS                                              ║
║  │   ●●                    ●              ●●               │ ║
║  │ COMMUNICATIONS                                           │ ║
║  │               ●●●●                              ●       │ ║
║  │ EVENTS                                                   │ ║
╠══════════════════════════════════════════════════════════════╣
║  CORRELATED ENTITIES  (entities with activity at same time) ║
║  [Malhotra Overseas Trading]  [Aether Telecom Device-44]                   ║
╚══════════════════════════════════════════════════════════════╝
```

**Features**:
- Swim lanes per event category
- Temporal zooming (year → month → week → day → hour)
- Event burst detection (highlights clusters of activity)
- Correlation panel: "Who else was active at this time?"
- Add event markers to case as evidence
- Compare two entities side-by-side

**Interactions**:
- Click event dot → slide-over with full event details
- Drag to select a time range → filter entire view
- "Burst" indicator when event density exceeds baseline × 3
- Hover lane header → toggle that category

---

### PAGE 6: `/entities/:id` — Entity Profile

**Purpose**: The most information-dense page. Complete picture of one entity.

**Design Philosophy**: 360° view without overwhelming — progressive disclosure.

**Layout**: Header + tabbed content + persistent sidebar connections

```
╔══════════════════════════════════════════════════════════════╗
║  ● PERSON  │  Karan Malhotra  │  Risk: ██████ HIGH              ║
║  New Delhi · Male · 38 · Merchant                          ║
║  [View in Graph]  [View on Map]  [Add to Case]  [Flag]      ║
╠══════════════╦═══════════════════════════════════════════════╣
║  CONNECTIONS ║  [Properties] [Activity] [Graph] [Documents]  ║
║  ─────────── ║                                               ║
║  Persons (4) ║  PROPERTIES                                   ║
║  Orgs (2)    ║  Name: Karan Malhotra                             ║
║  Accounts(3) ║  DOB: 12 Mar 1986                             ║
║  Devices (2) ║  Nationality: Indian                        ║
║  Events (12) ║  Occupation: Import Merchant                  ║
║  Vehicles(1) ║  Status: Active                               ║
║              ║  Risk Score: 72 / 100                         ║
║              ║  Communities: [Shell-Ring-04]                  ║
║              ║  Entity ID: PRS-0000442                        ║
╚══════════════╩═══════════════════════════════════════════════╝
```

**Tabs**:
1. **Properties** — all structured attributes
2. **Activity** — mini timeline of all events for this entity
3. **Graph** — embedded graph (subgraph of this entity's neighborhood)
4. **Documents** — linked synthetic documents
5. **Summary** — template-generated narrative about this entity, built from the same facts as the Risk Score Widget

**Risk Score Widget**:
```
Risk Score: 72 / 100
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Contributing Factors:
  + Connected to 2 flagged organizations       (+18)
  + Transaction velocity above baseline (×4)   (+14)
  + Communication cluster with 4 flagged nodes (+12)
  + No verified address document               (+8)
  - Government employment record (discount)    (−10)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Confidence: HIGH
```

---

### PAGE 7: `/cases` — Case List

**Purpose**: Manage ongoing investigations.

**Layout**: Sortable, filterable table + creation modal

```
╔═══════════════════════════════════════════════════════════╗
║  Cases  [+ New Case]  [Filter ▼]  [Sort ▼]               ║
╠═══════════════════════════════════════════════════════════╣
║  ID        Status    Priority  Entities  Updated          ║
║  CASE-001  OPEN      CRITICAL    12       2h ago          ║
║  CASE-002  REVIEW    HIGH         7       1d ago          ║
║  CASE-007  CLOSED    MED          3       5d ago          ║
╚═══════════════════════════════════════════════════════════╝
```

---

### PAGE 8: `/cases/:id` — Case Workspace

**Purpose**: The war room for a specific investigation.

**Design Philosophy**: Everything about this case, in one place.

**Layout**: Two-panel workspace

```
╔═══════════════════════════════════════════════════════════════╗
║  CASE-007: "Operation Amber"   [Status: OPEN]  [Close Case]   ║
╠══════════════╦════════════════════════════════════════════════╣
║  EVIDENCE    ║  INVESTIGATION NOTES                           ║
║  ─────────── ║  [Rich text editor — markdown]                 ║
║  Entities(7) ║  ─────────────────────────────────────────     ║
║  Events (3)  ║  AI SUMMARY (expandable)                       ║
║  Documents(2)║  "This case involves a suspected shell         ║
║  Screenshots ║   company ring centered on Malhotra Overseas Trading..."    ║
║  ─────────── ║  ─────────────────────────────────────────     ║
║  [+ Add]     ║  AUDIT LOG                                     ║
║              ║  • Entity added: Karan Malhotra (2h ago)           ║
╚══════════════╩════════════════════════════════════════════════╝
```

**Features**:
- Entity pin board (drag and arrange evidence cards)
- Markdown notes with auto-save
- Template-generated case summary (on demand)
- Linked timeline (events filtered to case entities)
- Linked subgraph (graph filtered to case entities)
- Export to PDF report
- Status workflow: Draft → Open → Under Review → Closed

---

### PAGE 9: `/analytics` — Analytics Engine

**Purpose**: Run graph algorithms, view computed metrics, explore risk heatmaps.

**Design Philosophy**: Power user surface — the analyst who thinks in algorithms.

**Layout**: Sidebar algorithm list + main result panel

```
╔═══════════════════════════════════════════════════════════════╗
║  ANALYTICS ENGINE                                             ║
╠════════════════╦══════════════════════════════════════════════╣
║  ALGORITHMS    ║  RESULT: Community Detection (Louvain)       ║
║  ──────────── ║  Run: 3 min ago  │  Entities: 4,200          ║
║  ▶ PageRank    ║  Communities Found: 47                        ║
║  ▶ Betweenness ║                                               ║
║  ▶ Louvain     ║  [Bar chart: community size distribution]    ║
║  ▶ Risk Prop.  ║  [Table: top 10 communities by risk]         ║
║  ▶ Shortest    ║  [Graph: community subgraph preview]         ║
║  ▶ Cycle Det.  ║                                               ║
║  ──────────── ║  [View in Graph Explorer]                     ║
║  Run Again     ║  [Export Results]                            ║
╚════════════════╩══════════════════════════════════════════════╝
```

**Algorithm Results Views**:
- **PageRank / Betweenness**: Ranked entity table + bar chart
- **Louvain**: Community size chart + risk distribution per community
- **Risk Propagation**: Visual flood fill from seed node
- **Shortest Path**: Step-by-step path visualization
- **Cycle Detection**: Highlighted cycle sub-graph

---

### PAGE 10: `/alerts` — Alert Queue

**Purpose**: System-detected anomalies that need human review.

**Design Philosophy**: Human-in-the-loop. The machine flags; the analyst decides.

**Layout**: Priority-sorted queue + detail panel

```
╔═══════════════════════════════════════════════════════════════╗
║  ALERTS  (12 unreviewed)  [Filter ▼]  [Bulk Review]          ║
╠═══════════════════════════════════════════════════════════════╣
║  ▲ CRITICAL │ Transaction burst │ Entity: Karan Malhotra │ 1h ago ║
║  ▲ HIGH     │ New shell pattern │ 4 linked orgs      │ 3h ago ║
║  ▲ MED      │ Device shared     │ PRS-002, PRS-044   │ 5h ago ║
╠═══════════════════════════════════════════════════════════════╣
║  DETAIL: Transaction Burst Alert                              ║
║  Entity: Karan Malhotra (PRS-0000442)                            ║
║  Trigger: 47 transactions in 6 hours (baseline: 2.3/day)     ║
║  Amount: ₹1.2M total                                       ║
║  [Open in Graph]  [Create Case]  [Dismiss]  [Flag for Review] ║
╚═══════════════════════════════════════════════════════════════╝
```

**Alert Types**:
- Transaction velocity anomaly
- Communication burst
- New entity connection to flagged node
- Geographic impossibility (same person, two distant locations, same hour)
- Document inconsistency
- Community risk threshold crossed

---

### PAGE 11: `/scenario` — Scenario Generator

**Purpose**: The demonstration feature. Create synthetic investigation scenarios on demand.

**Design Philosophy**: Make the invisible visible — show how the world is built.

**Layout**: Wizard-style config + generation progress + result preview

```
╔════════════════════════════════════════════════════════╗
║  SCENARIO GENERATOR                                    ║
╠════════════════════════════════════════════════════════╣
║  Storyline Type:  [Shell Company Ring ▼]               ║
║  Complexity:      [●●●○○] Medium                       ║
║  Entities:        [~20 entities]                       ║
║  Time Span:       [90 days]                            ║
║  Seed:            [42]  [Randomize]                    ║
║                                                        ║
║  [Generate Scenario]                                   ║
╠════════════════════════════════════════════════════════╣
║  GENERATING...                                         ║
║  ✓ Organizations created (6)                           ║
║  ✓ Persons assigned (12)                               ║
║  ✓ Transactions generated (340)                        ║
║  ✓ Documents forged (4)                                ║
║  ↻ Building graph relationships...                     ║
╠════════════════════════════════════════════════════════╣
║  RESULT                                                ║
║  [Mini graph preview]  [Open in Graph]  [Open in Map]  ║
║  Difficulty: HIGH  │  Key Entity: Malhotra Overseas Trading     ║
╚════════════════════════════════════════════════════════╝
```

**Scenario Types**:
- Shell Company Ring
- Money Routing Network
- Communication Cluster
- Identity Overlap
- Supply Chain Fraud
- Document Forgery Ring

---

### PAGE 12: `/settings` — System Configuration

**Purpose**: Control system parameters, data status, theming.

**Layout**: Tabbed settings panel

**Tabs**:
- **Data** — seed, entity counts, regeneration button
- **Appearance** — theme mode (already dark, but intensity slider), accent color
- **Performance** — max graph nodes, map cluster threshold
- **About** — version, ethics notice, synthetic data disclaimer

---

### PAGE 13: `/analytics` Risk Heatmap (Sub-view)

> Note: This is a sub-view within Analytics, not a separate page.

A grid showing risk scores across entity types and cities, rendered as a color-matrix heatmap. Clicking a cell filters the graph/map to those entities.

---

## PHASE 7 — DATA MODEL & ONTOLOGY

### Design Principle

ARGUS uses an **entity-centric graph ontology**. Everything is a node. Every connection is a labeled, directed edge with metadata.

---

### Node Types (Full Schema)

#### `(:Person)`
```
id: UUID
name: String
alias: [String]
dob: Date
gender: String
nationality: String
occupation: String
city: String
coordinates: {lat: Float, lng: Float}  -- synthetic
status: Enum[Active, Deceased, Unknown]
risk_score: Float (0–100)
risk_factors: [String]
community_ids: [String]
created_at: DateTime
last_activity: DateTime
flags: [String]
```

#### `(:Organization)`
```
id: UUID
name: String
type: Enum[Corporation, NGO, Shell, Government, Criminal]
industry: String
registered_city: String
coordinates: {lat, lng}
registration_date: Date
risk_score: Float
directors: [Person.id]   -- also stored as edges
status: Enum[Active, Dissolved, Flagged]
```

#### `(:Location)`
```
id: UUID
name: String
type: Enum[Building, District, Port, Airport, Warehouse, SafeHouse]
city: String
coordinates: {lat, lng}
capacity: Int
risk_score: Float
```

#### `(:Vehicle)`
```
id: UUID
plate: String
type: Enum[Car, Truck, Boat, Aircraft]
make: String
model: String
color: String
registered_to: Person.id | Organization.id
risk_score: Float
```

#### `(:Device)`
```
id: UUID
device_id: String
type: Enum[Phone, Laptop, SIM, Router]
imei: String (synthetic)
mac: String (synthetic)
owner: Person.id
carrier: String
risk_score: Float
```

#### `(:Account)`
```
id: UUID
account_id: String
bank: String
type: Enum[Checking, Savings, Corporate, Shell, Crypto]
balance_class: Enum[Low, Medium, High, Extreme]
status: Enum[Active, Frozen, Closed]
owner: Person.id | Organization.id
opened_date: Date
risk_score: Float
```

#### `(:Transaction)`

> **[v3 IMPLEMENTATION REFINEMENT]** Built as a `TRANSACTED_WITH` relationship between two `Account` nodes carrying every property below, not as a separate intermediate node. At this project's scale that's ~40K fewer nodes for identical query power — every property survives on the edge, and this is exactly the shape cycle detection, PageRank, and betweenness (Phase 9) need: they traverse Account→Account directly. The schema below is unchanged; only its physical representation moved from node to edge.

```
id: UUID
tx_id: String
from_account: Account.id
to_account: Account.id
amount: Float
currency: String (INR)
type: Enum[Wire, Cash, Crypto, Escrow]
timestamp: DateTime
description: String
flagged: Boolean
risk_score: Float
```

#### `(:Event)`
```
id: UUID
event_id: String
type: Enum[Meeting, Transaction, Communication, Travel, Incident, DocumentSigned]
timestamp: DateTime
location: Location.id
participants: [Entity.id]
metadata: JSON
risk_score: Float
```

#### `(:Communication)`

> **[v3 IMPLEMENTATION REFINEMENT]** Same reasoning as `(:Transaction)` above — built as a `COMMUNICATED_WITH` relationship between two `Device` nodes, not a separate node.

```
id: UUID
from_device: Device.id
to_device: Device.id
type: Enum[Call, SMS, Encrypted, Email]
timestamp: DateTime
duration_seconds: Int
flagged: Boolean
```

#### `(:Shipment)`
```
id: UUID
shipment_id: String
origin: Location.id
destination: Location.id
carrier: Organization.id
manifest: JSON
departure: DateTime
arrival: DateTime
status: Enum[InTransit, Delivered, Seized, Unknown]
risk_score: Float
```

#### `(:Document)`
```
id: UUID
doc_id: String
type: Enum[Passport, ContractFinancial, Registration, License, Invoice]
issuer: Organization.id | Person.id
subject: Person.id | Organization.id
issued_date: Date
expiry_date: Date
flagged: Boolean
inconsistency_type: String
```

#### `(:Incident)`
```
id: UUID
incident_id: String
type: Enum[Fraud, Trafficking, FinancialCrime, CommunicationAnomaly, DocumentForgery]
severity: Enum[Low, Medium, High, Critical]
timestamp: DateTime
location: Location.id
involved_entities: [Entity.id]
description: String
status: Enum[Open, UnderInvestigation, Closed]
```

#### `(:Case)`
```
id: UUID
case_id: String
title: String
status: Enum[Draft, Open, UnderReview, Closed]
priority: Enum[Low, Medium, High, Critical]
assigned_analyst: String
opened_at: DateTime
closed_at: DateTime
linked_entities: [Entity.id]
linked_events: [Event.id]
notes: String (markdown)
ai_summary: String
```

---

### Edge Types (Relationships)

| Edge Label | From | To | Key Properties |
|---|---|---|---|
| `KNOWS` | Person | Person | confidence, first_seen |
| `EMPLOYED_BY` | Person | Organization | role, start_date, end_date |
| `DIRECTS` | Person | Organization | role, since |
| `OWNS_ACCOUNT` | Person | Account | since |
| `OWNS_ACCOUNT` | Organization | Account | since |
| `OWNS_VEHICLE` | Person | Vehicle | since |
| `OWNS_DEVICE` | Person | Device | since |
| `COMMUNICATED_WITH` | Device | Device | via edge: Communication |
| `TRANSACTED_WITH` | Account | Account | via edge: Transaction |
| `ATTENDED` | Person | Event | role |
| `LOCATED_AT` | Person | Location | timestamp, confidence |
| `LOCATED_AT` | Organization | Location | primary: Boolean |
| `SHIPS_TO` | Organization | Organization | via edge: Shipment |
| `ISSUED_TO` | Document | Person | — |
| `ISSUED_BY` | Document | Organization | — |
| `LINKED_TO` | Case | Entity | reason, added_at |
| `PART_OF` | Person | Incident | role |
| `CONTROLS` | Person | Organization | confidence (for shell rings) |
| `SHARES_DEVICE` | Person | Person | device_id, period |
| `CO_LOCATED` | Person | Person | location, timestamp |

All edges include:
```
id: UUID
created_at: DateTime
confidence: Float (0.0 – 1.0)
source: String ("generator", "algorithm", "analyst")
metadata: JSON
```

---

## PHASE 8 — SYNTHETIC DATA GENERATION ENGINE

### Architecture

The data generator is a **standalone Python script** (`generate_world.py`) that:
1. Accepts a `--seed` integer argument (default: `42`)
2. Runs the full generation pipeline
3. Outputs to Neo4j via the Python driver
4. Is deterministic: same seed = same world, always

---

### Generation Pipeline (Ordered)

```
STAGE 1: World Foundation
  → Create cities (6) with coordinates
  → Create districts within cities
  → Create locations (8,000) distributed by city population weight

STAGE 2: Organizations
  → Generate 5,000 organizations across industries
  → Assign 10% as shell companies (randomly seeded)
  → Place shell companies in Offshoring District (Chennai)
  → Assign directors (persons not yet created — store as pending links)

STAGE 3: Persons
  → Generate 50,000 synthetic persons
  → Assign each to a city (weighted distribution)
  → Assign occupation, risk factors (initially clean)
  → Link directors to organizations (resolve pending links)
  → Assign devices (1–3 per person), accounts (1–4 per person)

STAGE 4: Transactions
  → For each account, generate baseline transaction history
  → Distribution: mostly small, daily-ish amounts
  → 2% of accounts: inject anomalous burst patterns
  → 0.5% of accounts: inject circular routing patterns

STAGE 5: Communications
  → Build communication graphs (social network model)
  → Most persons: 5–15 regular contacts
  → Inject dense clusters for storyline groups

STAGE 6: Events
  → Generate meetings, travel events, signed documents
  → Tie events to persons, locations, and timestamps

STAGE 7: Shipments
  → Generate 15,000 shipments via synthetic carriers
  → 3% have route anomalies

STAGE 8: Storyline Injection
  → For each storyline type, select seed entities
  → Modify their properties and relationships to create detectable patterns
  → Ensure each storyline has 1 "obvious" entry point and 2 "buried" paths

STAGE 9: Risk Score Computation
  → Run risk scoring algorithm on all entities
  → Score = weighted sum of: flagged connections, anomalous transactions,
    community membership, communication density, document inconsistencies
  → Propagate risk: neighbors of flagged nodes gain partial score

STAGE 10: Incident + Alert Generation
  → For each anomalous pattern, generate an Incident record
  → For high-severity incidents, generate an Alert
  → Alerts are tagged with entity IDs for the alert queue

STAGE 11: Index + Write to Neo4j
  → Batch write all nodes
  → Batch write all edges
  → Create Neo4j fulltext index on name fields
  → Create range indexes on risk_score, timestamp
  → Create composite indexes for common query patterns
```

---

### Seeding & Reproducibility

```python
from faker import Faker
import random

MASTER_SEED = 42

faker = Faker()
faker.seed_instance(MASTER_SEED)
random.seed(MASTER_SEED)
```

All distributions, random choices, and procedural decisions derive from the master seed. Changing the seed produces a completely different but internally consistent world.

---

### Scale Parameters (Configurable)

| Parameter | Default | Min | Max |
|---|---|---|---|
| `PERSON_COUNT` | 50,000 | 1,000 | 500,000 |
| `ORG_COUNT` | 5,000 | 500 | 50,000 |
| `TRANSACTION_COUNT` | 500,000 | 10,000 | 5,000,000 |
| `COMMUNICATION_COUNT` | 200,000 | 5,000 | 2,000,000 |
| `STORYLINE_COUNT` | 15 | 5 | 100 |

---

## PHASE 9 — GRAPH ANALYTICS ENGINE

### Implementation Strategy

All analytics run as **background jobs** triggered via the FastAPI backend. Results are cached and returned to the frontend. The heavy computation uses **Neo4j Graph Data Science (GDS)** library.

---

### Algorithm Catalogue

#### 1. PageRank (Influence Score)

**What**: Identifies the most globally influential entities — those whose importance is amplified by being connected to other important entities.

**Neo4j GDS Call**:
```cypher
CALL gds.pageRank.stream('entityGraph', {
  maxIterations: 20,
  dampingFactor: 0.85
})
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).name AS name, score
ORDER BY score DESC LIMIT 50
```

**Frontend**: Ranked table with score bar + "Open in Graph" per entity.

---

#### 2. Betweenness Centrality (Bridge Detection)

**What**: Finds entities that act as bridges between otherwise disconnected groups. Critical for understanding who controls information flow.

**Use**: Identifies key connectors in shell company rings. If you remove the highest-betweenness node, parts of the network become disconnected.

**Frontend**: Node size = betweenness score in graph canvas.

---

#### 3. Community Detection — Louvain

**What**: Partitions the graph into densely connected communities. Each community gets a color. Communities with high average risk score are flagged.

**Neo4j GDS Call**:
```cypher
CALL gds.louvain.stream('entityGraph')
YIELD nodeId, communityId
```

**Frontend**: 
- Nodes colored by community
- Community table: ID, size, avg risk, top entity
- "Explore Community" button → opens graph filtered to that community

---

#### 4. Weakly/Strongly Connected Components

**What**: Identifies isolated sub-networks. In an intelligence graph, isolated groups are often purposeful — designed to limit exposure.

**Use**: Finding self-contained clusters that don't touch the main graph. Classic indicator of compartmentalization.

---

#### 5. Shortest Path (Investigation Pivoting)

**What**: Given two entities, find the shortest chain of relationships connecting them.

**Workflow**: Analyst suspects Entity A is connected to flagged Entity B but cannot see how. Shortest path reveals the connecting chain.

**Frontend**: Step-by-step path rendered in graph canvas with path highlighted in accent color.

---

#### 6. Risk Propagation (Label Propagation variant)

**What**: A custom algorithm. Starting from one or more flagged ("seed") nodes, risk propagates along edges to neighbors, attenuating by a factor per hop.

```
Risk(neighbor) += Risk(seed) × (1 / hop_distance) × edge_confidence
```

**Use**: If we know a company is flagged, all persons connected to it (directors, account holders, associates) receive elevated risk scores proportional to their connection strength.

**Frontend**: Animation — a colored wave emanates from the seed node, coloring neighbors progressively.

---

#### 7. Cycle Detection

**What**: Finds circular paths in the transaction graph. Money going A → B → C → D → A is a classic laundering pattern.

**Implementation**: Custom Cypher traversal to detect cycles of length 3–7 in the Account/Transaction subgraph.

**Frontend**: Highlights the cycle as a colored ring in the graph.

---

#### 8. Degree Centrality + Density Map

**What**: Simple but powerful. Which nodes have the most edges? High degree in an unusual entity type (e.g., a private individual with 60+ organizational connections) is a red flag.

**Frontend**: Sorted list + histogram of degree distribution with anomaly threshold line.

---

#### 9. Node2Vec Similarity (Entity Resolution / "Find Similar")

> **[v3 ADDITION]** Added as part of the local-first intelligence pivot (see Phase 10) — a concrete example of "intelligence from graph algorithms, not API calls."

**What**: Neo4j GDS's built-in `gds.node2vec` produces a vector embedding for every node from its position in the graph (who it connects to, how densely). Cosine similarity between embeddings surfaces entities that occupy a *structurally similar role* in the network even if they share no direct edge — e.g. two people who each direct a shell company, transact with the same bank, and share a device with an associate, without ever appearing in the same query together.

**Neo4j GDS Call**:
```cypher
CALL gds.node2vec.stream('entityGraph', { embeddingDimension: 64 })
YIELD nodeId, embedding
```
Cosine similarity over the returned vectors (via `gds.similarity.cosine` or computed application-side) ranks the closest entities to a given seed.

**Use**: Entity Profile → "Similar Entities" panel. Powers a lightweight, fully local analogue of entity-resolution / "who else looks like this" — the kind of feature portfolio reviewers otherwise expect to see backed by an external ML API.

---

## PHASE 10 — LOCAL INTELLIGENCE LAYER

> **[v3 REVISION — supersedes v1/v2 "AI Features"]** v1/v2 of this plan made every intelligence feature a thin wrapper around the Gemini API — a required, internet-dependent, per-call-cost external service. The project owner made an explicit architectural call: **ARGUS must be fully functional offline, and its intelligence must come from graph algorithms, statistics, and local ML — not hosted LLM calls.** This phase is rewritten from scratch around that principle. Nothing below requires an API key, an internet connection, or a running cost. An LLM appears exactly once, at the very end, as a named-optional module that the rest of the system does not depend on.

### Philosophy

> "ARGUS should feel intelligent because of what it computes, not because it phoned an API."

Every feature in this layer:
1. Runs entirely on the local machine, using only the synthetic data ARGUS itself generated
2. Is explainable — its output is a direct, traceable function of specific graph facts or model features, never an opaque "the model said so"
3. Works with zero configuration and zero internet access
4. States its confidence, and is honest about being a heuristic, not a guarantee

---

### Where the "intelligence" actually comes from

| Capability | Technique | Why this, not an LLM |
|---|---|---|
| Influence ranking | PageRank (Neo4j GDS) | Phase 9 — already algorithmic, already local |
| Bridge / connector detection | Betweenness centrality (Neo4j GDS) | Phase 9 |
| Cluster / ring discovery | Louvain community detection (Neo4j GDS) | Phase 9 |
| "Find similar entities" | Node2Vec graph embeddings + cosine similarity (Neo4j GDS) | Phase 9 — a graph-native alternative to an embedding API |
| Laundering-pattern detection | Custom cycle detection over the transaction graph | Phase 9 |
| Risk scoring | Weighted rule-based scoring + custom label-propagation | Deterministic, auditable — an analyst can see exactly why a score is what it is |
| **Anomaly detection (transaction bursts, communication spikes)** | **Isolation Forest** (scikit-learn) over per-account/per-device behavioral features, with a z-score baseline as the explainable fallback | This is the textbook right tool: unsupervised, trained fresh on ARGUS's own synthetic data every run, ships as a ~10MB pure-Python dependency, and its output ("this account's transaction velocity is a 4.2σ outlier vs. its own 90-day baseline") is more concretely explainable than an LLM's prose guess |
| Entity / case narrative text | **Deterministic template-based NLG** — the same structured facts used for the Risk Score Widget (Phase 6), assembled into analyst-brief-style prose by a rule-based sentence composer | No hallucination risk, zero latency, zero dependency, and — because the "story" is built from the literal graph facts — it is by construction always accurate |
| Conversational Q&A ("Ask ARGUS") | **Optional** local LLM via Ollama (see below) | The one place a genuinely open-ended natural-language interface adds real value over a fixed template — explicitly opt-in |

The Analytics Engine (Phase 9) was never the problem — it was already 100% local. This phase's job is to replace the *narrative and Q&A* layer, which v1/v2 wrongly assumed needed a hosted LLM.

---

### Local Feature 1: Statistical / ML Anomaly Detection

**Where**: Runs as part of the generation pipeline (Phase 8, Stage 10) and is re-runnable on demand from `/analytics`.

**How it works — and why it's not just re-reading the generator's own injected labels**: Phase 8's storyline injector plants ground-truth anomalies (transaction bursts, circular routing, dense communication clusters) into an otherwise plausible baseline world. Detection is a **separate, independent pass** that does not consult those injection labels — it engineers behavioral features per entity (transaction count/amount in rolling windows, inter-transaction time variance, communication fan-out, degree relative to entity-type baseline) and scores outliers two ways:
- **Isolation Forest** (`sklearn.ensemble.IsolationForest`) trained fresh on the current world's own feature matrix — unsupervised, no labels used, no external training data.
- **Z-score baseline** as a simpler, fully explainable cross-check (`(value − mean) / stddev` against the entity's own historical window or its peer group).

An entity is flagged when both methods agree it's an outlier, which becomes the trigger for Incident/Alert generation (Phase 8, Stage 10) — a real (if small-scale) precision/recall story an interviewer can ask about, versus "the alerts are just the entities we marked as bad at generation time."

**Frontend**: Alert detail panel shows the actual feature values and the baseline they're compared against — e.g. *"47 transactions in 6 hours; this account's 90-day baseline is 2.3/day (μ) with σ=1.1 → z=19.8"* — not a paraphrased LLM sentence.

---

### Local Feature 2: Template-Based Narrative Generation

**Where**: Entity Profile → "Summary" tab; Case Workspace → "Summary" section; Alert detail panel.

**Input**: The same structured data the Risk Score Widget already computes — properties, connections, risk factors with their point contributions, community membership, anomaly detector output.

**Output**: A rule-based sentence composer turns that structured data into analyst-brief prose, e.g.:
> "Karan Malhotra is a 38-year-old import merchant based in New Delhi with a risk score of 72/100. He is associated with two organizations flagged as shell companies: Malhotra Overseas Trading and Shakti Logistics Pvt Ltd. The anomaly detector flagged a transaction burst on 12 Nov — 47 transactions totaling ₹1.2M in a 6-hour window, a 19.8σ deviation from his own baseline. He belongs to Community-12, the second-highest-risk community in the current graph. His device has been shared with 3 other individuals, two of whom are also in Community-12."

Every clause in that sentence maps 1:1 to a queried fact — there is nothing here an LLM adds except phrasing, which a well-written template composer handles deterministically and instantly.

**Implementation**: A small library of sentence templates keyed by fact type (risk factor, anomaly, community membership, shared-device overlap, ...), composed in priority order, with light variation (synonym rotation, clause reordering) so the same facts don't always read identically. Pure Python, no dependency beyond the standard library.

---

### Local Feature 3: Report Generator

**Where**: Case Workspace → "Export" → "Generate Report"

Same principle as Feature 2, extended to document length: Executive Summary, Key Entities, Evidence Timeline, Risk Assessment, and Recommended Actions sections are each assembled from the case's actual linked entities/events/risk data via templates, then rendered to Markdown/PDF. Deterministic, reproducible, no API call.

---

### Optional Module: ARGUS Assistant (Local LLM, Off by Default)

> This is the **one** place in ARGUS where an LLM is allowed to exist — and it is entirely optional. ARGUS Core (every feature above, every page in the product) works completely without it.

**Design**:
```
ARGUS Core
    ↓
Works 100% offline. No LLM anywhere in the request path.

ARGUS Assistant (optional, off by default)
    ↓
If — and only if — Ollama is detected running locally (a lightweight
runtime for small open models, e.g. llama3.2:3b or phi3, that runs
comfortably on a laptop CPU/GPU with no cloud dependency and no API
key), a "⌘J Ask ARGUS" panel becomes available for open-ended natural-
language questions ("which community has the most flagged
transactions?"). If Ollama isn't running, the panel simply doesn't
appear — every other feature is completely unaffected.
```

**Why Ollama specifically, and why optional**: Ollama runs entirely on the user's machine, requires no account, no API key, and no internet access once the model is pulled — it is the one "LLM" option that doesn't violate the offline-first requirement. But even so, it's a genuinely heavy dependency (a multi-GB model download) that most people evaluating this project won't want to install just to see it work — hence strictly optional, detected at runtime, never required.

**Implementation sketch**: The backend exposes `/api/ai/ask` (already scaffolded in Phase 0) as a thin adapter: it checks for a reachable Ollama instance at startup; if present, natural-language questions are answered by having the local model translate them into a bounded Cypher query template (never arbitrary generated Cypher against production data — the same safety principle v1/v2 intended, just running locally instead of against a hosted API) and then phrase the result. If absent, the endpoint returns a clear "Assistant not available — Ollama not detected" rather than failing silently.

---

## PHASE 11 — TECHNOLOGY STACK

### Decision Framework

Every technology was evaluated against 4 criteria:
1. **Best-in-class for its job** (not just popular)
2. **Excellent developer ergonomics** (so the codebase stays clean)
3. **Appropriate scale** (no over-engineering, no under-engineering)
4. **Portfolio signal** (choosing Neo4j over SQLite communicates engineering depth)

---

### Frontend

| Decision | Technology | Why |
|---|---|---|
| **Framework** | **Next.js 16** (App Router) | Best React framework. Server Components reduce client bundle. App Router enables clean layouts per page group. (Repo already scaffolded on 16; supersedes v1's "15".) |
| **Language** | **TypeScript** | Non-negotiable for a system of this complexity. Type safety across API contracts is critical. |
| **Styling** | **Vanilla CSS + CSS Custom Properties** | Full control. No runtime overhead. Design tokens via CSS variables. Zero Tailwind lock-in. |
| **Graph Visualization** | **Cytoscape.js** | Best balance of built-in algorithms + rendering performance + interaction API for this use case. Supports WebGL via extension. |
| **Map** | **MapLibre GL JS + deck.gl** *(v2 change from Mapbox GL)* | MapLibre is the open-source fork of Mapbox GL — same API, same WebGL rendering, **no API token, no billing, no vendor account**. Since v2 grounds ARGUS in real India geography, a real basemap now makes narrative sense (v1 had a fictional country on top of a real map, which was a mismatch). deck.gl still handles all data layers (GPU-accelerated, handles 100K+ points). |
| **Charts** | **Recharts** (standard charts) + **VisX** (custom timeline) | Recharts for dashboards. VisX for the timeline page where custom interaction is required. |
| **Server State** | **TanStack Query v5** | Best-in-class async state management. Caching, background refetch, mutation lifecycle — all handled. |
| **Client State** | **Zustand** | Minimal, unobtrusive, performant. For UI state: sidebar collapsed, active canvas selection, theme. |
| **Animation** | **Framer Motion** | Spring physics. Page transitions. Micro-animations on cards, alerts, stat counters. |
| **Icons** | **Lucide React** | Clean, consistent, SVG-based. Matches the minimal premium aesthetic. |
| **Typography** | **Inter** (body) + **JetBrains Mono** (data/IDs) | Inter for readability at high density. JetBrains Mono for entity IDs, scores, code. |

---

### Backend

| Decision | Technology | Why |
|---|---|---|
| **API Framework** | **FastAPI** | Async Python, automatic OpenAPI docs, Pydantic validation, native async support for Neo4j driver. Best-in-class DX for Python APIs. |
| **Graph Database** | **Neo4j Community Edition, self-hosted via Docker** *(v2 clarification)* | Native graph database, expressive Cypher. **v1 proposed Neo4j AuraDB Free for hosting — this is a bug: AuraDB Free does not support installing the GDS plugin, and the entire Analytics Engine (Phase 9) depends on GDS.** Self-hosting Community Edition + the GDS plugin via Docker is free, fully-featured, and is what the local-first `docker-compose` stack runs. |
| **Graph Algorithms** | **Neo4j GDS (Graph Data Science)**, plugin on self-hosted Neo4j | Pre-built, parallelized, production-grade. PageRank, Louvain, Betweenness, Node2Vec, Shortest Path — all built in. Only usable because we self-host (see above). |
| **Anomaly Detection** | **scikit-learn (Isolation Forest)** + statistical z-score baselines *(v3 addition)* | See Phase 10. Trained fresh on ARGUS's own synthetic data every run — no external dataset, no API, ~10MB pure-Python dependency. This is where "intelligence" actually lives, not in an LLM call. |
| **Narrative / Report Generation** | **Deterministic template-based NLG** (pure Python, stdlib only) *(v3 change from Gemini)* | v1/v2 sent every entity/case summary through the Gemini API. v3 replaces this with a rule-based sentence composer over the same structured facts already computed for the Risk Score Widget — no hallucination risk, no latency, no dependency, no cost, and it's always accurate by construction since it's built from literal graph facts. See Phase 10 for the full rationale. |
| **AI Assistant (optional)** | **Ollama**, running a small local model (e.g. `llama3.2:3b`) *(v3 change from required Gemini)* | The **only** LLM anywhere in ARGUS, and it's off by default and fully optional — see Phase 10. Chosen over any hosted API specifically because it runs on the user's machine with no account, no key, and no internet access, which is the one way an LLM feature can exist without breaking the offline-first requirement. Every other feature in the product works with zero knowledge of whether Ollama is even installed. |
| **Background Jobs** | **In-process asyncio tasks + Redis-backed job status** *(v2 change from ARQ)* | v1 proposed a dedicated ARQ worker process. At the reduced default scale (Phase 4), every algorithm and scenario-generation job completes in low single-digit seconds — a separate always-running worker process is operational overhead without payoff. `asyncio.create_task` inside the FastAPI process + a job-id/status record in Redis preserves the exact same UX (kick off job → poll status → get result) with one fewer service to run and deploy. If a genuinely long job ever appears, ARQ remains a drop-in upgrade — the job-status contract is identical. |
| **Cache** | **Redis** | Algorithm result caching, AI response caching, search result caching, and job status (see above). |
| **Search** | **Neo4j Fulltext Index** | Built-in full-text search within Neo4j. No need for Elasticsearch at this scale. |
| **Auth** | **JWT (static demo token)** | Single-user educational system. No real auth required. Simple token for API protection. |
| **Data Generation** | **Faker (Python)** + custom generation engine | Python Faker with seeded reproducibility. Custom pipeline scripts. |

---

### Infrastructure & DevOps

> **[v2 REVISION]** v1 assumed a live hosted deployment (Vercel + Railway/Render + AuraDB) from day one. The project owner chose **local-first**: build ARGUS to run perfectly via a single `docker-compose up`, document it thoroughly (README, architecture diagram, recorded demo), and treat live hosting as a separate future decision rather than a Phase-0 dependency. This removes all ongoing hosting cost during development and removes the AuraDB/GDS conflict entirely, since Neo4j+GDS is self-hosted in the same compose stack either way.

| Decision | Technology | Why |
|---|---|---|
| **Repo Structure** | **Monorepo (single repo, clear separation)** | Keeps frontend and backend together. Simpler for a portfolio project. No Turborepo complexity needed. |
| **Local Runtime** | **Docker + docker-compose** (Neo4j+GDS, Redis, FastAPI, Next.js) | The entire stack — including the graph database and its algorithms library — runs identically on any machine with one command. This *is* the primary way ARGUS is experienced for now. |
| **Future Frontend Hosting** | **Vercel** (when/if deployed) | Optimal for Next.js. Zero-config. Not wired up yet — deferred by design. |
| **Future Backend/DB Hosting** | **Self-hosted Neo4j+GDS container on Railway/Fly.io** (when/if deployed) | AuraDB is explicitly ruled out (see GDS note above) for any tier that needs the Analytics Engine. Deferred by design. |
| **CI/CD** | **GitHub Actions** | Lint, type-check, build on every push. No deploy step until hosting is decided. |

---

### Why NOT These Technologies

| Rejected | Rejected Technology | Reason |
|---|---|---|
| Graph viz | D3.js force | Too low-level; layout physics in main thread kills performance |
| Graph viz | Sigma.js | Excellent rendering but no built-in algorithms; Cytoscape.js does both |
| Map | Mapbox GL JS | Requires an API token and bills past a free quota; MapLibre GL JS is the API-compatible open-source fork with none of that — strictly better for this project |
| Database | Neo4j AuraDB (any tier below AuraDS) | Does not support the GDS plugin — incompatible with the entire Analytics Engine |
| Database | PostgreSQL + graph extension | Apache AGE/pgvector don't match Neo4j's algorithm maturity |
| Database | TigerGraph | Overkill for educational scale; GSQL adds complexity |
| Backend | Express/Node | Python is better for data science integrations and Neo4j client |
| Background | ARQ / Celery (dedicated worker process) | At this project's scale, jobs complete in seconds; a separate always-on worker is overhead without payoff. In-process asyncio tasks preserve the same job/poll UX with less infra. Revisit if job durations grow. |
| State | Redux | Massive boilerplate; TanStack Query + Zustand does the job with 1/10th the code |
| Auth | Full OAuth | Single-user demo system; adds unnecessary complexity |
| **AI** | **Any hosted LLM as a required dependency** (Gemini, OpenAI, Claude, Grok, Perplexity, or equivalent) *(v3 rejection)* | Explicit project requirement: ARGUS must work fully offline, with zero API keys and zero per-request cost, and its intelligence must demonstrably come from graph algorithms and ML rather than "an LLM guessed it." A required hosted-LLM dependency would also mean the product silently stops working the moment an API key expires or a quota is hit — unacceptable for something meant to sit untouched in a portfolio and still work the day someone clones it. See Phase 10. |

---

## PHASE 12 — DESIGN SYSTEM

### Core Philosophy

> **Premium. Minimal. Mission Control.**
> 
> Every pixel serves a purpose. The interface disappears; the data speaks.

---

### Color System

```css
/* === SURFACE HIERARCHY ===
   Eight levels of elevation. Never pure black. Never pure white. */

--surface-base:        #0B0C0F;   /* Page background */
--surface-raised:      #111318;   /* Cards, panels */
--surface-overlay:     #161A22;   /* Modals, popovers */
--surface-inset:       #0E1016;   /* Input backgrounds */
--surface-hover:       #1C2130;   /* Interactive hover */
--surface-selected:    #1E2536;   /* Selected/active state */
--surface-border:      #252B3B;   /* Dividers, card borders */
--surface-border-faint:#1A1F2E;   /* Very subtle separation */

/* === TEXT HIERARCHY === */
--text-primary:        #F0F2F7;   /* Main content text */
--text-secondary:      #8892A4;   /* Labels, metadata */
--text-tertiary:       #5A6478;   /* Placeholders, hints */
--text-inverse:        #0B0C0F;   /* Text on accent backgrounds */
--text-code:           #A8C4FF;   /* Entity IDs, scores */

/* === ACCENT (Single vibrant accent) === */
--accent-primary:      #3D7BFF;   /* Primary actions, links, selection */
--accent-primary-hover:#5590FF;   
--accent-glow:         rgba(61, 123, 255, 0.15);

/* === RISK / SEVERITY === */
--risk-critical:       #FF3B47;   /* CRITICAL — urgent red */
--risk-high:           #FF7D1A;   /* HIGH — warning orange */
--risk-medium:         #FFB800;   /* MED — caution amber */
--risk-low:            #1AE87B;   /* LOW — safe green */
--risk-unknown:        #8892A4;   /* Unknown — neutral */

/* === ENTITY TYPES (Graph node colors) === */
--entity-person:       #3D7BFF;   /* Blue */
--entity-organization: #A855F7;   /* Purple */
--entity-location:     #1AE87B;   /* Green */
--entity-vehicle:      #FFB800;   /* Amber */
--entity-device:       #06B6D4;   /* Cyan */
--entity-account:      #F97316;   /* Orange */
--entity-event:        #EC4899;   /* Pink */
--entity-document:     #84CC16;   /* Lime */
--entity-shipment:     #F43F5E;   /* Rose */
```

---

### Typography

```css
/* === FONTS ===
   Inter for UI text. JetBrains Mono for data. */

--font-sans:  'Inter', system-ui, sans-serif;
--font-mono:  'JetBrains Mono', 'Fira Code', monospace;

/* === SCALE === */
--text-xs:    11px;   /* Badges, labels */
--text-sm:    13px;   /* Secondary info, metadata */
--text-base:  15px;   /* Primary body text */
--text-md:    17px;   /* Card titles, section headers */
--text-lg:    20px;   /* Page headings */
--text-xl:    24px;   /* Section titles */
--text-2xl:   30px;   /* Dashboard stats */
--text-3xl:   36px;   /* Hero numbers */

/* === WEIGHT === */
--font-regular: 400;
--font-medium:  500;
--font-semibold: 600;
--font-bold:    700;
```

---

### Spacing System

```css
/* Base unit: 4px */
--space-1:   4px;
--space-2:   8px;
--space-3:   12px;
--space-4:   16px;
--space-5:   20px;
--space-6:   24px;
--space-8:   32px;
--space-10:  40px;
--space-12:  48px;
--space-16:  64px;
--space-20:  80px;
```

---

### Component Tokens

```css
/* === SIDEBAR === */
--sidebar-width:        240px;
--sidebar-collapsed:    64px;
--sidebar-transition:   280ms cubic-bezier(0.4, 0, 0.2, 1);

/* === CARDS === */
--card-radius:          10px;
--card-padding:         20px;
--card-border:          1px solid var(--surface-border);
--card-shadow:          0 1px 3px rgba(0,0,0,0.3);
--card-shadow-hover:    0 4px 16px rgba(0,0,0,0.4);

/* === TRANSITIONS === */
--transition-fast:      150ms ease;
--transition-base:      220ms ease;
--transition-slow:      350ms ease;
--transition-spring:    400ms cubic-bezier(0.34, 1.56, 0.64, 1);
```

---

### Grid System

```css
/* 12-column grid, 24px gutters, max-width 1440px */
--grid-cols: 12;
--grid-gutter: 24px;
--grid-max: 1440px;

/* Content widths */
--content-sm:  480px;   /* Forms, modals */
--content-md:  720px;   /* Detail panels */
--content-lg:  960px;   /* Tables */
--content-xl:  1200px;  /* Full pages */
```

---

### States

Every interactive element has 5 defined states:

| State | Visual Treatment |
|---|---|
| **Default** | Base color, 1px border |
| **Hover** | Background lightens, border brightens, subtle elevation |
| **Active/Pressed** | Scale 0.98, immediate color |
| **Selected** | Accent border-left, accent tint background |
| **Disabled** | 40% opacity, cursor: not-allowed |

---

### Empty States

Every page that can have no data has a designed empty state:

```
      ◦ ○ ◦
   No cases yet.

   Open the Graph Explorer or run a 
   Scenario to begin an investigation.

   [+ New Case]  [Go to Graph]
```

Minimalist, centered, actionable. Never just "No data."

---

### Loading States

| Component | Loading Behavior |
|---|---|
| Page | Skeleton shimmer on cards/lists |
| Graph Canvas | Spinner + "Loading graph..." overlay |
| Stat Cards | Pulsing placeholder rectangles |
| Entity Profile | Staggered skeleton rows |
| Summary tab | Skeleton rows — generation is near-instant, but the placeholder keeps the layout stable |

---

## PHASE 13 — SYSTEM ARCHITECTURE

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLIENT BROWSER                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Next.js App (React)                                     │   │
│  │  ├── App Router (/dashboard, /graph, /map, ...)          │   │
│  │  ├── TanStack Query (server state + caching)             │   │
│  │  ├── Zustand (UI state)                                  │   │
│  │  ├── Cytoscape.js (graph canvas)                         │   │
│  │  ├── MapLibre + deck.gl (map)                            │   │
│  │  └── Framer Motion (animations)                          │   │
│  └─────────────────────────────────────────────────────────┘   │
└────────────────────────────────┬────────────────────────────────┘
                                 │ HTTPS / REST
┌────────────────────────────────▼────────────────────────────────┐
│                         FASTAPI BACKEND                         │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Routers                                                  │  │
│  │  ├── /api/entities     (CRUD + search)                    │  │
│  │  ├── /api/graph        (subgraph queries)                 │  │
│  │  ├── /api/analytics    (algorithm endpoints)              │  │
│  │  ├── /api/cases        (case management)                  │  │
│  │  ├── /api/alerts       (alert queue)                      │  │
│  │  ├── /api/ai           (local intelligence: narratives, ask)│ │
│  │  ├── /api/map          (geospatial endpoints)             │  │
│  │  ├── /api/timeline     (temporal queries)                 │  │
│  │  └── /api/scenario     (generator trigger)                │  │
│  ├──────────────────────────────────────────────────────────┤  │
│  │  Services                                                 │  │
│  │  ├── GraphService      (Cypher query builder)             │  │
│  │  ├── AnalyticsService  (GDS algorithm runner)             │  │
│  │  ├── IntelligenceService (anomaly detection, NLG templates)│ │
│  │  ├── AlertService      (anomaly detection + queue)        │  │
│  │  └── GeneratorService  (scenario trigger)                 │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────┬──────────────────────┬────────────────────┬──────────────┘
       │ Bolt Protocol        │ Redis Client        │ HTTP
       │                      │                     │
┌──────▼──────┐   ┌───────────▼──────┐   ┌─────────▼────────┐
│    NEO4J    │   │      REDIS       │   │  OLLAMA (local)  │
│  Graph DB   │   │  Cache + job     │   │  optional, off   │
│  + GDS      │   │  status          │   │  by default      │
└─────────────┘   └──────────────────┘   └──────────────────┘
(scikit-learn Isolation Forest + template NLG run in-process in the
backend itself — no external service box needed for either.)
```

---

### API Design Principles

1. **REST, not GraphQL** — REST is sufficient; GraphQL adds complexity without benefit here since we query Neo4j directly with Cypher
2. **Consistent response envelope**: `{ data, meta, error }`
3. **Pagination**: cursor-based for large result sets
4. **Compression**: gzip for graph payloads (node/edge lists can be large)
5. **Rate limiting**: on the optional `/api/ai/ask` endpoint, since it's the only path that may call out to a local Ollama instance

---

### Key API Endpoints

```
GET  /api/entities?type=Person&risk_min=60&city=New Delhi&page=1
GET  /api/entities/:id
GET  /api/entities/:id/graph?depth=2
GET  /api/entities/:id/timeline
GET  /api/entities/:id/ai-summary

GET  /api/graph/subgraph?entity_ids=[]&depth=2
GET  /api/graph/shortest-path?from=:id&to=:id
GET  /api/graph/neighbors?id=:id&depth=:n

POST /api/analytics/pagerank
POST /api/analytics/betweenness
POST /api/analytics/louvain
POST /api/analytics/risk-propagation?seed_ids=[]
POST /api/analytics/cycle-detection
GET  /api/analytics/results/:job_id

GET  /api/cases
POST /api/cases
GET  /api/cases/:id
PUT  /api/cases/:id
POST /api/cases/:id/entities
DELETE /api/cases/:id/entities/:entity_id

GET  /api/alerts?status=unreviewed&priority=HIGH
PUT  /api/alerts/:id/review

POST /api/ai/entity-summary/:id
POST /api/ai/case-summary/:id
POST /api/ai/ask (body: { question, context })

GET  /api/map/entities?bbox=...&type=...
GET  /api/map/shipments?bbox=...

POST /api/scenario/generate (body: { type, complexity, seed })
GET  /api/scenario/status/:job_id

GET  /api/search?q=...&types=[]&risk_min=0&city=...
```

---

## PHASE 14 — FOLDER STRUCTURE

```
argus/
├── README.md
├── .env.example
├── docker-compose.yml
├── docker-compose.prod.yml
│
├── frontend/                        # Next.js App
│   ├── package.json
│   ├── tsconfig.json
│   ├── next.config.ts
│   ├── public/
│   │   ├── fonts/
│   │   └── icons/
│   │
│   └── src/
│       ├── app/                     # Next.js App Router
│       │   ├── layout.tsx           # Root layout (sidebar + topbar)
│       │   ├── page.tsx             # Redirect → /dashboard
│       │   ├── dashboard/
│       │   │   └── page.tsx
│       │   ├── graph/
│       │   │   └── page.tsx
│       │   ├── search/
│       │   │   └── page.tsx
│       │   ├── map/
│       │   │   └── page.tsx
│       │   ├── timeline/
│       │   │   └── page.tsx
│       │   ├── entities/
│       │   │   └── [id]/page.tsx
│       │   ├── cases/
│       │   │   ├── page.tsx
│       │   │   └── [id]/page.tsx
│       │   ├── analytics/
│       │   │   └── page.tsx
│       │   ├── alerts/
│       │   │   └── page.tsx
│       │   ├── scenario/
│       │   │   └── page.tsx
│       │   └── settings/
│       │       └── page.tsx
│       │
│       ├── components/
│       │   ├── layout/
│       │   │   ├── Sidebar.tsx
│       │   │   ├── Topbar.tsx
│       │   │   └── PageShell.tsx
│       │   │
│       │   ├── graph/
│       │   │   ├── GraphCanvas.tsx       # Cytoscape wrapper
│       │   │   ├── GraphControls.tsx
│       │   │   ├── NodeDetailPanel.tsx
│       │   │   ├── AlgorithmPanel.tsx
│       │   │   └── GraphLegend.tsx
│       │   │
│       │   ├── map/
│       │   │   ├── ArgusMap.tsx          # MapLibre + deck.gl wrapper
│       │   │   ├── MapLayers.tsx
│       │   │   └── MapControls.tsx
│       │   │
│       │   ├── timeline/
│       │   │   ├── TimelineCanvas.tsx    # VisX custom timeline
│       │   │   ├── TimelineLane.tsx
│       │   │   └── EventDot.tsx
│       │   │
│       │   ├── entity/
│       │   │   ├── EntityCard.tsx
│       │   │   ├── EntityProfile.tsx
│       │   │   ├── RiskScoreWidget.tsx
│       │   │   └── EntityTypeIcon.tsx
│       │   │
│       │   ├── cases/
│       │   │   ├── CaseCard.tsx
│       │   │   ├── CaseWorkspace.tsx
│       │   │   └── EvidenceBoard.tsx
│       │   │
│       │   ├── analytics/
│       │   │   ├── AlgorithmResult.tsx
│       │   │   ├── CommunityTable.tsx
│       │   │   └── RiskHeatmap.tsx
│       │   │
│       │   ├── alerts/
│       │   │   ├── AlertCard.tsx
│       │   │   └── AlertDetailPanel.tsx
│       │   │
│       │   ├── dashboard/
│       │   │   ├── StatCard.tsx
│       │   │   ├── ActivityFeed.tsx
│       │   │   ├── AlertQueue.tsx
│       │   │   └── WorldMapSnapshot.tsx
│       │   │
│       │   ├── ai/
│       │   │   ├── AISummaryPanel.tsx
│       │   │   ├── AskArgusPanel.tsx    # ⌘J panel
│       │   │   └── AIReportExport.tsx
│       │   │
│       │   └── ui/                      # Design system atoms
│       │       ├── Button.tsx
│       │       ├── Badge.tsx
│       │       ├── Card.tsx
│       │       ├── Input.tsx
│       │       ├── Select.tsx
│       │       ├── Modal.tsx
│       │       ├── SlideOver.tsx
│       │       ├── Tooltip.tsx
│       │       ├── Skeleton.tsx
│       │       ├── EmptyState.tsx
│       │       ├── Spinner.tsx
│       │       └── RiskBadge.tsx
│       │
│       ├── hooks/
│       │   ├── useEntities.ts
│       │   ├── useGraph.ts
│       │   ├── useCases.ts
│       │   ├── useAlerts.ts
│       │   ├── useAnalytics.ts
│       │   ├── useSearch.ts
│       │   └── useAI.ts
│       │
│       ├── stores/
│       │   ├── uiStore.ts            # Zustand: sidebar, modals, theme
│       │   ├── graphStore.ts         # Zustand: canvas selection, layout
│       │   └── investigationStore.ts # Zustand: active case context
│       │
│       ├── lib/
│       │   ├── api.ts                # Fetch wrapper, base URL config
│       │   ├── queryClient.ts        # TanStack Query client
│       │   ├── formatters.ts         # Risk score, dates, entity types
│       │   └── constants.ts
│       │
│       └── styles/
│           ├── globals.css           # CSS variables + reset
│           ├── typography.css
│           ├── components.css        # Global component styles
│           └── animations.css
│
├── backend/                         # FastAPI Application
│   ├── pyproject.toml
│   ├── Dockerfile
│   │
│   └── app/
│       ├── main.py                  # FastAPI app init, CORS, routers
│       ├── config.py                # Settings (env vars, Pydantic)
│       │
│       ├── api/
│       │   ├── routes/
│       │   │   ├── entities.py
│       │   │   ├── graph.py
│       │   │   ├── analytics.py
│       │   │   ├── cases.py
│       │   │   ├── alerts.py
│       │   │   ├── ai.py
│       │   │   ├── map.py
│       │   │   ├── timeline.py
│       │   │   ├── search.py
│       │   │   └── scenario.py
│       │   └── dependencies.py      # Auth, rate limiting, DB
│       │
│       ├── services/
│       │   ├── graph_service.py     # Cypher query builder
│       │   ├── analytics_service.py # GDS algorithm runner
│       │   ├── ai_service.py        # Template NLG + optional Ollama adapter
│       │   ├── alert_service.py     # Anomaly detection
│       │   └── scenario_service.py  # Generator trigger
│       │
│       ├── repositories/
│       │   ├── entity_repo.py       # Neo4j entity CRUD
│       │   ├── graph_repo.py        # Graph traversal queries
│       │   ├── case_repo.py
│       │   └── alert_repo.py
│       │
│       ├── models/
│       │   ├── entities.py          # Pydantic models: Person, Org...
│       │   ├── graph.py             # GraphNode, GraphEdge, Subgraph
│       │   ├── analytics.py         # AlgorithmResult, Community
│       │   ├── cases.py
│       │   └── alerts.py
│       │
│       ├── workers/
│       │   └── tasks.py             # asyncio background job runners (Phase 9 result, replaces v1's ARQ worker)
│       │
│       └── database/
│           ├── neo4j.py             # Driver init, connection pool
│           └── redis.py             # Redis client init
│
└── generator/                       # Synthetic Data Generator
    ├── requirements.txt
    ├── generate_world.py            # Main entry point
    ├── config.py                    # Seed, scale parameters
    │
    └── generators/
        ├── world_generator.py       # Cities, districts, locations
        ├── person_generator.py
        ├── organization_generator.py
        ├── account_generator.py
        ├── transaction_generator.py
        ├── communication_generator.py
        ├── event_generator.py
        ├── shipment_generator.py
        ├── document_generator.py
        ├── storyline_generator.py   # Injects synthetic incidents
        ├── risk_scorer.py           # Initial risk computation
        └── neo4j_writer.py          # Batch write to Neo4j
```

---

## PHASE 15 — PERFORMANCE STRATEGY

### Frontend Performance

| Area | Strategy |
|---|---|
| **Graph Rendering** | Cytoscape.js WebGL renderer for >200 nodes. Layout calculation in Web Worker. Progressive node loading (initial: 500, expand on demand). |
| **Map** | deck.gl GPU rendering. MapLibre tile caching. Cluster aggregation server-side before sending to client. |
| **Large Lists** | TanStack Virtual for lists of 1000+ entities. Only render visible rows. |
| **Code Splitting** | Next.js dynamic imports for Cytoscape, MapLibre, deck.gl (heavy libraries). Never in initial bundle. |
| **Image/Asset** | No images in the app (icons only). Lucide SVGs are inline. No weight from images. |
| **State** | TanStack Query prevents redundant API calls. Stale-while-revalidate on entity data. |

---

### Backend Performance

| Area | Strategy |
|---|---|
| **Queries** | All Neo4j queries use index-based lookups. No full graph scans in user-facing endpoints. |
| **Algorithm Jobs** | Async in-process jobs (asyncio task + Redis job status). Frontend polls status endpoint every 2s. Algorithm results cached in Redis for 1 hour. |
| **Pagination** | All list endpoints return max 50 results. Cursor-based pagination for graph traversals. |
| **Connection Pool** | Neo4j driver uses connection pooling (50 max connections). |
| **AI Calls** | Template-generated narratives are cheap enough to compute on demand; results are still cached in Redis keyed by entity ID + data hash to keep entity-profile loads instant. Optional Ollama responses are cached the same way. |

---

### Neo4j Index Strategy

```cypher
-- Full-text search
CREATE FULLTEXT INDEX entity_name FOR (n:Person|Organization|Location|Vehicle)
ON EACH [n.name, n.alias]

-- Range queries
CREATE INDEX entity_risk FOR (n:Person) ON (n.risk_score)
CREATE INDEX entity_city FOR (n:Person) ON (n.city)
CREATE INDEX event_time FOR (n:Event) ON (n.timestamp)
CREATE INDEX tx_time FOR (n:Transaction) ON (n.timestamp)
CREATE INDEX alert_status FOR (n:Alert) ON (n.status, n.priority)
```

---

## PHASE 16 — DEVELOPMENT ROADMAP

### Phase Principle

> "Ship a working, impressive demo fast. Then deepen."

**Each phase produces a demo-able product.** No phase ends with broken code.

---

### Phase 0: Foundation (Week 1)

- [x] Initialize monorepo structure
- [x] Docker compose: Neo4j + Redis + FastAPI + Next.js
- [x] CSS design system (all tokens, typography, base components)
- [x] Sidebar + Topbar layout components
- [x] FastAPI app skeleton with all routers registered (empty responses)
- [x] TanStack Query + Zustand setup
- [x] Environment configuration

**Demo**: App loads. Sidebar navigates between empty pages. ✅ Done.

---

### Phase 1: Data World (Week 2)

- [x] Python Faker generator: persons, organizations, locations
- [x] Neo4j writer: batch node creation
- [x] Relationship generator: KNOWS, EMPLOYED_BY, OWNS_*
- [x] Transaction generator: baseline patterns
- [x] Storyline injector: all 7 storyline types (exceeds the original "first storyline" scope)
- [x] Risk scorer: initial computation
- [x] Verify: Neo4j Browser shows a rich, connected graph

**Demo**: Neo4j Browser shows ~20K nodes, ~90K relationships at default scale (local-first scale, revised down from the original 50K/200K target — see Phase 4 scale note).

---

### Phase 2: Core API (Week 3)

- [x] Entity CRUD endpoints with Pydantic models
- [x] Search endpoint (Neo4j fulltext)
- [x] Graph subgraph endpoint
- [x] Case CRUD
- [x] Alert endpoints

**Demo**: API returns real data. `/docs` shows all endpoints working. ✅ Done.

---

### Phase 3: Dashboard + Search (Week 3–4)

- [x] Dashboard page: stat cards, activity feed, alert queue
- [x] Search page: faceted search, entity cards
- [x] Entity profile page: properties, connections list

**Demo**: Dashboard shows live system stats. Search finds entities. Profile page complete. ✅ Done.

---

### Phase 4: Graph Explorer (Week 4–5)

- [x] Cytoscape.js canvas integration
- [x] Node rendering with entity type colors
- [x] Edge rendering with relationship labels
- [x] Node expansion (double-click to load neighbors)
- [x] Control panel: type filter, depth slider
- [x] Node selection → detail panel (right side)
- [x] Layout switcher
- [x] Shortest path finder (select two nodes → highlight the path) — added in Phase 10 polish
- [x] Mini-map — a hand-drawn `<canvas>` overview (not a second Cytoscape instance or plugin), bottom-right, coloring dots by risk tier and drawing the current viewport as a draggable rectangle; click/drag pans the real graph

**Demo**: Graph Explorer with real data. Expand nodes, find paths between them, see the network.

---

### Phase 5: Map + Timeline (Week 5–6)

- [x] MapLibre GL integration with custom dark style
- [x] deck.gl ScatterplotLayer for entity locations
- [x] deck.gl ArcLayer for shipment routes
- [x] Timeline page with VisX custom rendering
- [x] Timeline swim lanes per event type
- [x] Temporal zooming — drag across the daily-volume histogram to select a span; narrows the active range (chart, scatter, and notable-moments panel all re-filter), with a "Zoomed to X–Y · reset" badge; a plain click still selects a single day, distinguished from a drag by pointer movement, not by target element

**Demo**: See entities on the map. See their activity on the timeline. ✅ Done.

---

### Phase 6: Analytics Engine (Week 6–7)

- [x] Neo4j GDS setup and verification
- [x] PageRank endpoint + result display
- [x] Betweenness Centrality + graph visualization
- [x] Louvain Community Detection + color coding
- [x] Risk Propagation algorithm (custom hop-decayed spread, not a GDS primitive — see Phase 9 write-up)
- [x] Async job status pattern (asyncio task + Redis) for long-running algorithms
- [x] Shortest Path (select two nodes in graph → run) — wired into Graph Explorer in Phase 10
- [x] Cycle Detection (verified live against a real 6-hop laundering ring in the synthetic data)
- [x] Node2Vec similarity ("Find Similar Entities") — v3 addition beyond the original scope

**Demo**: Analytics page runs algorithms. Results appear in graph. ✅ Done.

---

### Phase 7: Cases + Alerts (Week 7)

- [x] Full case workflow (create, open, close)
- [x] Case workspace: notes editor, entity evidence board
- [x] Evidence system: add/remove entities to/from a case
- [x] Alert queue with severity + status filters
- [x] Alert review actions: Investigate, Close, Reopen

**Demo**: Full investigation workflow from alert → case → workspace. ✅ Done.

---

### Phase 8: Local Intelligence Layer (Week 8)

- [x] Isolation Forest + z-score anomaly detection over generated behavioral features — verified live: independently rediscovered a real injected transaction burst without reading its ground-truth flag
- [x] Template-based NLG composer (entity narrative, case summary)
- [x] Report generator (Markdown/PDF export) — added as two more formats on the investigation export custody chain built in the evidence/calibration phase (json, html, now markdown and pdf), rather than a second, disconnected export path: same hash-on-creation, same per-access logging, same retention schedule. PDF is drawn directly with reportlab (no system Cairo/Pango dependency); Markdown escapes the handful of characters the format gives meaning to, so a finding statement containing `*` or `#` can't inject structure. Verified live against a real investigation with findings and evidence.
- [x] Optional: Ollama detection + "Ask ARGUS" panel (⌘J), gracefully absent if not installed

**Demo**: Anomaly detector flags entities, template narratives explain them, case summaries generate on demand — all offline.

---

### Phase 9: Scenario Generator (Week 8–9)

- [x] Scenario Generator UI
- [x] Backend: generate scenario as an async background job (subprocess running the real generation engine, not a simulated one)
- [x] All 6 storyline types implemented
- [x] Live progress updates via polling
- [x] Preview and launch into Graph / Case

**Demo**: One click generates a real Shell Company Ring (or any of 5 other storyline types) and writes it into the live graph. ✅ Done.

---

### Phase 10: Polish (Week 9–10)

- [x] Animations: Framer Motion where it earns its keep (stat counters, incident feed, page transitions) — not sprinkled everywhere for its own sake
- [x] Empty states for all pages
- [x] Loading skeletons
- [x] Error boundaries and error states (root-level Next.js `error.tsx`)
- [x] Keyboard shortcuts (⌘K search, ⌘J Ask ARGUS, ⌘B graph)
- [x] Responsive layout (spot-checked at 900px breakpoints across Dashboard/Analytics/Cases/Alerts)
- [x] README with features/stack/run instructions
- [x] Ethics + synthetic data disclaimer (README + Settings → About)
- [x] Final performance audit — formal Lighthouse pass against a production build with a seeded graph, authenticated; found and fixed a real layout-shift defect on the Dashboard, and investigated (with direct evidence, not assumption) why Graph/Map LCP figures don't hold up — see [docs/performance.md](docs/performance.md)

**Demo**: The finished product. Enterprise-grade feel. Smooth everywhere.

---

## PHASE 17 — RISKS & MITIGATIONS

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Graph canvas performance with 5K+ nodes** | High | High | Cap initial render at 500 nodes. Lazy expansion. Web Worker layout. WebGL renderer. |
| **Neo4j GDS algorithm timeout** | Medium | Medium | All GDS runs as async background jobs (asyncio task + Redis status). Frontend polls. No HTTP timeout risk. |
| **Isolation Forest false positives/negatives on small synthetic scale** | Medium | Low | Cross-checked against an explainable z-score baseline; both must agree to raise an alert. Acceptable — the point is a realistic detection story, not perfect precision. |
| **Optional Ollama dependency confusing users who don't have it installed** | Low | Low | Detected at runtime; the Assistant panel simply doesn't render if Ollama isn't reachable. Every other feature is unaffected. |
| **Generator runs for too long** | High | Low | Make generator configurable. Default to 10K persons for development. 50K for demo. |
| **Map coordinate ambiguity** | Low | Low | All coordinates are clearly synthetic (bounded box, no real-world overlap). |
| **Self-hosted Neo4j resource limits** | Low | Medium | Default generator scale (~75K nodes) runs comfortably in the Docker container's default memory allocation. Generator remains configurable for stress-testing. |
| **Complex Cypher query optimization** | Medium | Medium | All queries tested in Neo4j Browser first. Index verification step before release. |
| **Template narratives feeling repetitive/robotic** | Medium | Low | Sentence-variation library (synonym rotation, clause reordering) keyed by fact type keeps phrasing from feeling copy-pasted across entities. |

---

## PHASE 18 — FUTURE SCOPE

These are excluded from V1 but represent genuine engineering growth paths:

| Feature | Why Deferred |
|---|---|
| **Real-time event streaming** | Requires Kafka or WebSocket event bus. Adds operational complexity. V2 candidate. |
| **Multi-analyst collaboration** | Requires presence system, conflict resolution. V2 candidate. |
| **Natural language → Cypher compiler** | The optional Ollama-backed Ask ARGUS (Phase 10) uses bounded query templates, not open Cypher generation; a fully general NL-to-Cypher compiler is a genuine V2 research project. |
| **Graph Neural Network risk model** | Replacing heuristic risk scoring with a trained GNN. Requires ML pipeline infrastructure. |
| **Mobile layout** | Investigation tools are inherently desktop-first. Mobile optimization is a V3 concern. |
| **Export to Neo4j format** | Allow downloading the full synthetic world as a Neo4j dump for offline analysis. |
| **Custom ontology editor** | Let analysts define new entity types and relationship labels in the UI. |
| **Time-series anomaly detection** | Statistical models (ARIMA, Isolation Forest) for transaction pattern detection instead of heuristic rules. |
| **Integration with Open Source data** | e.g., Wikipedia-sourced fictional companies, or procedurally generated news events. |

---

## PHASE 19 — FINAL RECOMMENDATION

### What ARGUS Is

ARGUS is a **synthetic intelligence analysis simulator** — a full-stack engineering portfolio project that demonstrates mastery of:

- **Graph database design and querying** (Neo4j, Cypher, GDS)
- **Large-scale synthetic data generation** (50K entities, 1M+ relationships)
- **Advanced graph visualization** (Cytoscape.js, WebGL rendering)
- **Geospatial analytics** (MapLibre + deck.gl, real India geography)
- **Temporal analysis** (custom VisX timeline)
- **Local-first intelligence** (Neo4j GDS algorithms, Isolation Forest anomaly detection, deterministic template NLG, optional local LLM via Ollama)
- **Enterprise-grade UX** (dark design system, micro-animations, progressive disclosure)
- **Async backend architecture** (FastAPI, asyncio background jobs, Redis, Neo4j GDS)
- **Investigation workflow modeling** (entity-centric, hypothesis-driven)

### Why It Will Impress

Most engineers build CRUD apps with tables and charts. ARGUS builds a world — and then lets you reason through it.

A recruiter or hiring manager viewing ARGUS will see:

1. ✅ Intentional architecture — nothing is accidental
2. ✅ Graph thinking — understanding of non-relational data modeling
3. ✅ Performance engineering — WebGL, Web Workers, lazy loading
4. ✅ Design maturity — not a template, a crafted system
5. ✅ AI integration — practical, grounded, not theatrical
6. ✅ Ethical clarity — explicit about synthetic nature; no surveillance theater

### The Stack, One More Time

| Layer | Technology |
|---|---|
| Frontend | Next.js 15, TypeScript, Vanilla CSS |
| Graph Viz | Cytoscape.js (WebGL) |
| Map | MapLibre GL JS + deck.gl |
| Charts | Recharts + VisX |
| State | TanStack Query + Zustand + Framer Motion |
| Backend | FastAPI (Python) |
| Database | Neo4j + GDS |
| Cache/Queue | Redis (cache + async job status) |
| AI / Intelligence | Neo4j GDS + scikit-learn + template NLG (all local); Ollama optional |
| Data Gen | Python Faker + custom engine |
| Deploy | Local-first via Docker Compose; hosting deferred (see Phase 11) |

### Development Order

```
Week 1  → Foundation + Design System
Week 2  → Synthetic World (Generator)
Week 3  → Core API
Week 3–4 → Dashboard + Search + Entity Profile
Week 4–5 → Graph Explorer (the crown jewel)
Week 5–6 → Map + Timeline
Week 6–7 → Analytics Engine
Week 7   → Cases + Alerts
Week 8   → AI Features
Week 8–9 → Scenario Generator
Week 9–10 → Polish + Documentation
```

**Estimated total time**: 10 weeks at a moderate engineering pace.

---

> [!IMPORTANT]
> This document represents the original product vision, architecture, and implementation plan for ARGUS, as proposed before Phase 0 began.
> **All phases have since been implemented.** For current, accurate technical documentation, see [`docs/`](docs/) and the top-level [`README.md`](README.md). This file remains for its design rationale.

---

> [!NOTE]
> ARGUS is set in India using real geography (cities, states, coordinates), but every person, organization, phone number, account, transaction, and document in it is procedurally generated and entirely fictional. No real individual or real company is represented. ARGUS contains no real personal data, no scraping, no OSINT, and no surveillance functionality — it is an educational engineering demonstration of graph analytics, investigation workflow design, and connected data visualization.
