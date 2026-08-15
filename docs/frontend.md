# Frontend

Scope: the Next.js application — routes, data fetching, state management, and the three canvas-heavy modules (Graph Explorer, Map, Timeline) that carry the most implementation complexity. For the API contract every hook talks to, see [api.md](api.md).

Next.js 16 (App Router), TypeScript, React 19. Vanilla CSS Modules — no Tailwind, no component library. Dependency manifest: `frontend/package.json`.

> **Next.js 16 note**: `frontend/AGENTS.md` flags that this Next.js major version has breaking changes from what most training data assumes — check `node_modules/next/dist/docs/` before relying on remembered App Router conventions.

## Folder structure

```
frontend/src/
├── app/
│   ├── layout.tsx            # root layout: fonts, <Providers> only
│   ├── page.tsx               # public landing page (no app shell)
│   ├── providers.tsx           # TanStack Query + ToastProvider
│   ├── error.tsx                # root error boundary
│   └── (app)/                    # route group — every authenticated app screen
│       ├── layout.tsx             # wraps the group in <AppShell>
│       └── dashboard/, graph/, map/, timeline/, search/,
│           entities/[id]/, cases/, cases/[id]/, alerts/,
│           analytics/, scenario/, settings/
├── components/
│   ├── marketing/             # landing page only: Hero, CapabilityGrid, SpotlightSection,
│   │                            WorkflowSection, TechCredibility, FinalCTA, *Motif
│   ├── layout/                 # AppShell, Sidebar, Topbar, PageShell, CommandPalette
│   ├── graph/                   # GraphCanvas, GraphControls, NodeDetailPanel, RelationshipPanel
│   ├── map/                     # ArgusMap, MapControls, SelectedEntityPopup, ShipmentDetailPopup
│   ├── timeline/                 # TimelineChart
│   ├── dashboard/                 # MetricStrip, PriorityQueue, RiskDonut, CaseList, IncidentFeed
│   ├── entity/                     # EntityCard, EntitySearchBox, EntityTypeIcon, RiskScoreWidget
│   ├── assistant/                   # AskArgusPanel
│   └── ui/                           # Badge, Button, Card, Checkbox, EmptyState, Input/Select/
│                                       Textarea, Modal, RangeSlider, RiskBadge, SegmentedControl,
│                                       SelectControl, Skeleton, Spinner, Table, Tabs, Toast
├── hooks/                    # one file per resource, TanStack Query wrappers over lib/api.ts
├── lib/                      # api.ts, types.ts, constants.ts, entityDisplay.ts, formatters.ts,
│                               queryClient.ts, cn.ts, theme.ts
├── types/                    # ambient module declarations (cytoscape-fcose)
└── stores/                   # uiStore.ts (Zustand)
```

### Route groups

`app/page.tsx` is the public landing page and must **not** render the app shell (sidebar/topbar), while every product screen must. The `(app)` route group solves this without affecting URLs: `app/(app)/layout.tsx` applies `<AppShell>` to everything inside it, and the root layout carries only fonts and providers. `/dashboard` still resolves from `app/(app)/dashboard/` — parenthesised segments are organisational, not part of the path.

## Routes

| Path | Renders | Primary hook(s) |
|---|---|---|
| `/` | Public landing page — no app shell | `useDashboardSummary` (live hero stats) |
| `/dashboard` | Command center: metric strip, priority queue, incident feed, risk ladder, active cases | `useDashboardSummary`, `useEntities` |
| `/graph` | Cytoscape.js canvas — the Graph Explorer | `useGraphOverview`, `useSubgraph` |
| `/search` | Full-text search + browse, with type/risk facets | `useSearch`, `useBrowseEntities` |
| `/map` | Global geospatial workspace (MapLibre + deck.gl), three scale tiers | `useMapEntities`, `useMapShipments`, `useMapRegions`, `useMapCountries`, `useMapCorridors` |
| `/timeline` | Volume histogram + burst detection + swimlane chart + ranked moments | `useGlobalTimeline` |
| `/entities/[id]` | Entity hub — risk and contributing factors always visible in the sidebar; Properties/Activity/Cases & Alerts/Summary tabs | `useEntity`, `useEntityTimeline`, `useEntityCases`, `useEntityAlerts`, `useEntitySummary` |
| `/cases`, `/cases/[id]` | Case list + workspace (evidence board, notes, summary) | `useCases`, `useCase`, `useCaseSummary` |
| `/alerts` | Alert review queue | `useAlerts`, `useReviewAlert` |
| `/analytics` | Algorithm picker + result renderer | `useAnalyticsJob` |
| `/scenario` | Scenario Generator wizard | `useScenarioTypes`, `useScenarioJob` |
| `/settings` | Data/Appearance/Performance/About, all backed by real stats | `useDashboardSummary` |

## App shell and layout

`app/(app)/layout.tsx` wraps every product page in `<AppShell>` (`components/layout/AppShell.tsx`), which composes `Sidebar` + `Topbar` + the page content + a globally-mounted `AskArgusPanel` (renders nothing if the optional assistant is unavailable — see [ai-layer.md](ai-layer.md)).

`PageShell` (`components/layout/PageShell.tsx`) is the per-page content wrapper: it renders a title/subtitle/actions header for normal pages, or — passed `full` — a zero-padding full-bleed container for the two canvas-style pages (Graph, Map) that need to own their own layout.

Navigation is data-driven from `lib/constants.ts`'s `NAV_GROUPS`, grouped around the investigator's loop rather than by implementation area:

| Group | Items | Why |
|---|---|---|
| _(ungrouped)_ | Dashboard | Situational overview — the landing surface |
| **Triage** | Alerts, Cases | What the system flagged, and what is already being worked |
| **Investigate** | Search, Graph Explorer, Map, Timeline | The four analysis surfaces over the same graph |
| **Analyze** | Analytics | Step back from a single entity to whole-graph patterns |
| **System** | Scenario Generator, Settings | Instance tooling |

`Sidebar` renders this list and highlights the active route via `usePathname()`. Each item carries a one-line `hint` used as its tooltip — the only affordance left when the rail collapses to icons. It holds collapse state in `uiStore` (Zustand), reuses the Dashboard's `useDashboardSummary()` query (same cache, so no extra request) for live counts on Alerts and Cases, and forces icon-only mode below 900px via CSS regardless of the manual toggle. Count badges are neutral by default; only the unreviewed-alert queue renders red, so the one badge that means "work is waiting" keeps its signal.

`Topbar` carries breadcrumbs, a full-width global search field (opens the command palette), the world's entity count, and a persistent `Synthetic` chip — stating the data's nature once in chrome rather than repeating a banner per page.

`CommandPalette` (`components/layout/CommandPalette.tsx`) is a portal-based overlay — opened via the Topbar search field, `⌘K`/`Ctrl+K` from anywhere, or the shared `uiStore.commandPaletteOpen` flag. It lists every page from `NAV_GROUPS` **and** debounced live entity results from `GET /api/search`, so `⌘K` resolves real graph entities rather than only page names, with arrow-key navigation and Enter to jump.

Keyboard shortcuts (registered in `CommandPalette.tsx` and `AskArgusPanel.tsx` via `window.addEventListener("keydown", ...)`):

| Shortcut | Action |
|---|---|
| `⌘K` / `Ctrl+K` | Toggle the command palette |
| `Escape` | Close the command palette (or a `Modal`, if one's open) |
| `⌘J` / `Ctrl+J` | Toggle Ask ARGUS (only registered when the assistant is available) |

## Navigation model

Application navigation and marketing navigation are deliberately separate.

- The sidebar brand links to `/dashboard`, the **application** home. This is the
  convention in comparable products, and the inverse would eject an analyst out
  of the workspace mid-investigation via the control they are most likely to
  click by reflex. It was previously an inert `<div>`, which left no way back to
  anything.
- Leaving the workspace is an explicit, labelled **Product overview** item in
  the sidebar footer, styled as a quieter sibling of the nav items because it
  does something categorically different from moving between surfaces.
- Both directions are plain `<Link>`s, so browser back/forward behave normally.

## Data fetching

`lib/api.ts`'s `apiFetch<T>(path, init)` is the single fetch wrapper every hook uses: prefixes `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`), sends the session cookie via `credentials: "include"` and echoes the CSRF cookie in `X-CSRF-Token` on state-changing requests (there is deliberately no token in the bundle), throws a typed `ApiError` (carries `status`) on any non-2xx response, and returns the parsed `Envelope<T>` (mirrors the backend's [Envelope shape](backend.md#response-envelope) — `lib/api.ts` redeclares the interface rather than sharing a types package, consistent with the deliberate frontend/backend separation described in [architecture.md](architecture.md#why-three-separate-deployables-instead-of-one)).

`lib/queryClient.ts` configures TanStack Query defaults: 30s `staleTime`, `refetchOnWindowFocus: false`, one retry. Every `hooks/use*.ts` file follows the same shape: a `useQuery` wrapping `apiFetch` for reads, `useMutation` + `queryClient.invalidateQueries` for writes.

### The job-polling hook pattern

`useAnalyticsJob<T>()` (`hooks/useAnalytics.ts`) and `useScenarioJob()` (`hooks/useScenario.ts`) both implement the same client-side half of the [background-job contract](backend.md#background-jobs): a `useMutation` (`start`) kicks off the job and captures the returned `job_id` into local state, and a `useQuery` (`job`) polls `GET .../results/{job_id}` (or `.../status/{job_id}`) with `refetchInterval` conditional on `status === "running"` — so polling stops itself the instant the job settles. `useAnalyticsJob` polls every 1.2s; `useScenarioJob` every 0.9s (it's rendering live per-stage progress, so a tighter interval reads better).

## Command Center

The dashboard is one workspace with a single reading order — situation, then
where, then who, then what changed — rather than a grid of parallel cards with
no relationship between them.

- **`SituationBrief`** states the position in a sentence before showing any
  figure, with the counters as corroboration beneath it. Every clause is
  composed from values the summary and region rollup actually contain.
- **`RegionStrip`** makes regional posture a *filter* rather than a set of exits
  to the map. Selecting a region scopes the lead queue, so "Europe is elevated"
  becomes a question pursued in place. It is one horizontally scrolling row: an
  auto-fit grid left the eleventh cell stranded on a second row beside a wide
  gap, which read as a layout fault rather than a filter.
- **`LeadQueue` + `LeadContext`** are master-detail. The queue selects; the
  panel argues, using the scorer's own recorded `risk_factors` under "why it
  surfaced", the alerts and cases already referencing the entity, and its real
  connection counts. The previous queue navigated straight out to a profile, so
  comparing two leads meant leaving and coming back.

Leads are drawn from **both** Person and Organization. The earlier queue asked
only for Persons, silently excluding every elevated Organization — the label
carrying the shell-company and corporate-network findings.

The selection is *derived*, not synced in an effect: `leads.find(...) ?? leads[0]`.
A region filter that drops the current selection therefore resolves on the same
render, with no intermediate frame showing a stale or absent lead.

## Alerts triage

Queue selects, detail argues — the same shape as the Command Center, for the
same reason. A stack of self-contained cards forced every alert to carry its
full context inline, so the page could only be skimmed.

`AlertDetail` answers the six questions triage needs before a decision. Two are
computed rather than stored:

- **Spread** — the distinct countries and regions across the alert's involved
  entities. An alert touching five countries across four regions is a materially
  different finding from a local one.
- **Related alerts** — matched on shared `storyline_id`, a real link in the
  graph rather than a similarity heuristic over text. Alerts planted by one
  storyline are one investigation.

## Case workspace

`CaseFootprint` opens the case with reach and cause: countries, regions and peak
risk computed across the linked entities' own geography, and the alerts that
involve anything on the evidence board. Related alerts are matched by
intersecting `involved_entity_ids` with the board, which costs one request for
the whole alert set rather than one per entity.

## Graph Explorer

`components/graph/GraphCanvas.tsx` wraps Cytoscape.js behind an imperative handle (`GraphCanvasHandle`): `addElements`, `fit`, `runLayout`, `highlightNeighborhood`, `highlightPath`. The Cytoscape instance itself is created **once**, in a mount-only `useEffect` (`[]` deps) — rebuilding it on every parent re-render would destroy the user's pan/zoom/layout state. This creates a classic stale-closure risk: `cy.on("tap", ...)` handlers registered in that effect would otherwise close over whatever `onSelectNode`/`onExpandNode` props existed on the *first* render, forever. The fix is a pair of refs (`onSelectNodeRef`, `onExpandNodeRef`) updated on every render, with the Cytoscape event handlers calling through the ref rather than the prop directly — see the comment block at the top of `GraphCanvas.tsx` for the full reasoning. This exact bug was what surfaced when the shortest-path feature needed the tap handler to read fresh `pathMode` state; `highlightNeighborhood` alone had never exposed it because it only touches a ref.

`app/(app)/graph/page.tsx` owns the interaction state: selected node (drives `NodeDetailPanel`), selected edge (drives `RelationshipPanel`), current layout, risk floor, focus target, and path-finding mode (`pathMode`/`pathFrom` — clicking two nodes while active calls `GET /api/graph/shortest-path` and highlights the result via `highlightPath`).

### Visual encoding

Two independent channels, so neither has to compete with the other:

- **Fill colour = entity type** (`Person`, `Organization`, `Account`, …) from `lib/theme.ts`'s `ENTITY_COLORS`.
- **Border ring = risk tier** from `riskTier()`, widening and gaining chroma from medium → critical. Because risk is not folded into the fill, a critical Person and a critical Organization read as equally urgent. `GraphLegend` documents both channels; without the ring key that second channel is invisible.

Node diameter scales with risk score (`nodeSize()`), so importance survives even when labels are hidden.

### Progressive disclosure

The default view is the **risk-led overview** (`GET /api/graph/overview` — highest-risk persons/orgs plus their immediate neighbours), not the whole graph. On top of that:

- **Zoom/importance-gated labels.** `updateLabelVisibility()` recomputes on every zoom (rAF-throttled): below 0.7× only critical nodes are labelled; to 1.1× critical/high plus hub nodes (degree ≥ 4); above that, everything. Selected and highlighted nodes always keep their label.
- **Focus mode.** `isolateNeighborhood(id)` hides everything outside the node's closed neighbourhood and fits the camera to it. Cleared from either the detail panel or the toolbar badge.
- **Filters.** Entity-type toggles (via the legend) and a risk floor compose with focus mode: `applyVisibility()` unions all three reasons a node can be hidden into a single `.hidden` class per element, so they never fight each other. Elements are hidden, never removed, so re-showing is instant and needs no refetch.

### Inspection

Clicking a **node** opens `NodeDetailPanel` — identity, risk badge, type-specific properties, and a ranked list of its on-canvas connections (each row pivots selection to that neighbour). Clicking an **edge** opens `RelationshipPanel`, which answers "why are these two connected?" directly: relationship type, both endpoints, and every property the edge actually carries (amount formatted as INR, dates formatted, booleans as Yes/No). Internal `*_id` foreign keys are filtered out — they duplicate the endpoints already named above.

Layout uses `cytoscape-fcose` (registered once behind a module-level guard so StrictMode/HMR re-execution can't double-register), which packs disconnected components rather than scattering them.

## Map

`components/map/ArgusMap.tsx` layers deck.gl on top of a MapLibre GL base map via `MapboxOverlay` — both the base map instance and the overlay are created once in a mount-only effect, mirroring the Graph Explorer's pattern. `maplibre-gl` is pinned to `^3.6.2` specifically — newer major versions break deck.gl's shared WebGL context in this stack, confirmed during development.

> Do **not** add a retry/`setStyle` guard around the base-map style load. React StrictMode's dev-only double-mount aborts the first `Map` instance's in-flight `style.json` fetch, which looks like a failure in the network panel but is harmless — the surviving instance's own fetch succeeds. A previous "resilience" fix that re-issued `setStyle()` raced with that successful load and was itself the cause of intermittent blank basemaps. See [troubleshooting.md](troubleshooting.md#map-renders-without-a-basemap).

### Scale tiers

The map opens on the **world**, not a country — the product models a global picture, and opening on one country frames every investigation as local before the analyst has asked anything. `scaleForZoom()` maps the current zoom to one of three tiers, and each tier renders a *different dataset* rather than restyling one:

| Tier | Zoom | Entities | Routes |
|---|---|---|---|
| `world` | < 3.3 | Region bubbles from `/api/map/regions` | Region-to-region corridors from `/api/map/corridors` |
| `regional` | 3.3–5.8 | Country bubbles from `/api/map/countries` | Individual shipment routes |
| `local` | ≥ 5.8 | Individual entities; labels for critical/selected above 7.2 | Individual shipment routes |

They swap datasets because they answer different questions: at world zoom the analyst is reading "which regions are active", and several thousand individual points cannot express that however they are drawn. Bubble radius is area-proportional (`√count`) — sizing by radius alone over-weights large aggregates.

### Arcs are chords, not great circles

Every `ArcLayer` sets `greatCircle: false`. A true great-circle path between, say, Central Asia and North America passes near the pole, which Web Mercator projects **off the top of the viewport** as a stray vertical line. `getHeight` cannot rein this in either: ArcLayer bows arcs along Z, which projects flat in a top-down view. These arcs abstract a trade relationship rather than claim a sailed route, so a straight chord is both more readable and more honest about what it represents.

A `circuitous` shipment is drawn as **two** legs through its `via` port — collapsing it to one origin→destination arc would hide the detour, which is the entire reason the route was flagged.

### Viewport scoping

Once zoomed past the world tier, both the route layer and `MapContextPanel` filter to the visible extent (`withinBounds`). Without this, drilling into a region was decorative: the camera moved but the panel still listed Germany and Brazil, and intercontinental arcs merely transiting the view were the loudest thing on screen. Filtering on the viewport rather than a remembered "active region" also stays correct when the analyst pans and zooms freely instead of clicking through.

### The context panel

`MapContextPanel` is the ranked companion to the canvas — regions at world tier, countries at regional tier, ordered by elevated entities then route anomalies. It exists for two reasons: comparing two similar circles across a world map is a poor way to answer "where is risk highest", and region names drawn onto the canvas collided with the basemap's own continent labels. It also gives drill-down an explicit affordance rather than relying on the analyst guessing that bubbles are clickable.

### Route hierarchy

Routes are split across two `ArcLayer`s so anomalies are never out-shouted by routine traffic. Anomalous routes are the only pickable ones; normal routes render only when the filter is set to "all", at 0.6px and 22% opacity — present as texture, not as competition. At world tier the route filter applies to corridors too, so the control means the same thing at every scale; `ELEVATED_ANOMALY_RATE` (4.5%) sits meaningfully above the generator's 3% base rate, since a threshold below the baseline would paint most corridors red and make "anomalous" meaningless.

Person points use a lighter neutral than the design system's low-risk slate (`PERSON_MAP_COLOR`). The UI token is deliberately quiet, but at 3.5px on a near-black basemap it was invisible — hiding 4,000 people and leaving 400 organizations looking like the whole dataset.

`MapControls` exposes entity-type, risk-floor and route filters (all on the shared `SelectControl`), a "World" reset, an entity search that flies to a result, and a badge naming the current tier and what it shows.

Clicking an entity opens `SelectedEntityPopup`; clicking an anomalous route opens `ShipmentDetailPopup`, which explains *why* the route was flagged (off-lane / circuitous with its detour ratio and via-port / manifest discrepancy) rather than reporting `Route anomaly: Yes`.

`app/(app)/map/page.tsx` reads two query params. `?focus=<entityId>` (from the entity profile's "View on Map") derives the matching entity via `useMemo` over the already-loaded list rather than storing it in state, and flies the camera to it; manual selection is tracked separately (`undefined` = no override yet, so the focused entity still wins; `null` = the popup was explicitly closed). `?region=<name>` (from the dashboard's Global posture panel) waits on the region rollup **and** on the map having reported bounds — MapLibre ignores `flyTo` before its style has loaded, and an earlier version latched its "already flown" ref before the map existed, so the link silently did nothing.

## Timeline

The page is a temporal investigation workspace, not a single chart. `components/timeline/timelineModel.ts` holds the pure model — day bucketing, range filtering, and burst detection — so the analysis is testable and separate from rendering.

- **Burst detection.** A day is a burst when its flagged volume exceeds the mean by `BURST_SIGMA` (2) standard deviations, guarded against zero variance so a flat dataset doesn't mark every day. Two sigma isolates a handful of days on this dataset; a threshold that fired constantly would be decoration, not a finding.
- **`ActivityHistogram`** answers "what changed" — daily volume with flagged activity stacked in front of the baseline, burst days marked explicitly rather than left to be eyeballed. Each bar has a full-height transparent hit area, because a 2px bar is far too small a click target. Selecting a day narrows the rest of the page.
- **`TimelineChart`** — a hand-built @visx swimlane chart (four lanes: Incidents, Transactions, Communications, Events), not a Recharts chart, because it needs heterogeneous point types on shared lanes with custom tooltips, which is easier with @visx's low-level primitives than through a pre-built chart component. Baseline points render at 1.6px/0.3 opacity and flagged records are drawn **last**: at 3px/0.55 they merged into solid bands that buried the very records the lane exists to surface, and source ordering could let an ordinary record occlude a finding.
- **`NotableMoments`** ranks everything flagged inside the current selection, incidents first by severity. It deliberately covers flagged transactions and communications too — bursts here are driven by those, so an incidents-only panel went empty exactly when the analyst clicked the most interesting day on the chart. Transactions and communications are relationships rather than nodes, so those rows stay informational instead of pretending to link somewhere.

### Search facets

`/search` offers entity-type, region and minimum-risk facets. Two rules keep them honest:

- Type counts come from the result set actually on screen, so a facet never advertises a number the current query cannot deliver.
- Region counts deliberately **ignore the region filter itself** — computing them post-filter would make every unselected region read zero the moment one was ticked.

Result rows show `city, country` rather than a bare city: across 70 cities in 50 countries, "Bengaluru" and "Santos" carry very different context, and an analyst scanning results shouldn't have to open each one to find out where it is.

## Cross-page linking

Entity, Case, Alert, Graph, and Map are meant to be jumped between, not treated as separate silos:

- Entity profile → `/graph?seed={id}` ("View in Graph"), `/map?focus={id}` (when the entity has `lat`/`lng`), and a "Cases & Alerts" tab backed by `GET /api/entities/{id}/cases` / `/alerts` — both reverse the same `Case-[:LINKED_TO]->Entity` and `Incident-[:INVOLVES]->Entity` relationships the forward-direction case/alert queries already use.
- Dashboard stat cards → `/cases` and `/alerts?status=Open` (the latter pre-selects the status tab via `useSearchParams`, which requires wrapping the page in `<Suspense>` per Next's static-export rules).
- Timeline incident tooltips → `/alerts`. (Getting a tooltip's embedded link to actually be clickable took a debounced-hide fix — a bare `onMouseLeave` on the 3px SVG circle closed the tooltip before the cursor could reach it; see the comment in `TimelineChart.tsx`.)
- Scenario Generator results → `/graph?seed=`, `/cases/{id}`, `/entities/{id}` for the storyline's key entity, plus a "what to look for" brief naming the storyline's signature and the surface that shows it.
- Dashboard Global posture → `/map?region={name}`, which flies the map to that region rather than dropping the analyst at the world view with no indication of what they clicked.
- Entity profile → an "already referenced in N cases and N alerts" banner that opens the Cases & Alerts tab. Whether an entity is already under investigation changes what to do next, so it belongs on arrival rather than three clicks in. Connection counts link into the graph — "9 Persons" is only useful if the analyst can go and see them.

## Entity display for denormalized references

`Case.linked_entities` and `Incident.involved_entities` come back from the API as raw `{label, properties}` pairs (the node's native Neo4j properties), not the normalized `GraphNode` shape (`id`/`name`/`risk_score`/...) that `/api/entities/*` returns. `lib/entityDisplay.ts`'s `entityId()`/`entityName()` resolve the correct ID/name field per label (mirroring `backend/app/repositories/entity_labels.py`'s mapping) so the Cases and Alerts pages can link to `/entities/{id}` without special-casing every label inline.

## State management

Three layers, each with a distinct job:

- **TanStack Query** — all server state (everything fetched from the API). This is the large majority of state in the app.
- **Zustand** (`stores/uiStore.ts`) — the one piece of cross-component client UI state: sidebar collapsed/expanded.
- **Local component `useState`** — everything else (form inputs, selected tabs, graph interaction mode). `cases/[id]/page.tsx`'s `NotesPanel` is a deliberate example: it's extracted as its own keyed child component with its own local `useState(initialNotes)` rather than syncing server data into local state via `useEffect`, specifically to avoid a "setState in effect" anti-pattern — remounting via `key={caseDetail.case_id}` resets the local draft cleanly when the case changes.

## Design system

CSS Modules per component/page (`*.module.css` next to each `.tsx`), CSS custom properties for the shared palette (`--text-primary`, `--surface-border`, `--risk-critical`, etc. — defined in `styles/tokens.css`). Fixed dark theme by design (see the Settings page's Appearance tab) — no light mode planned. Icons are `lucide-react`; motion is Framer Motion, used selectively (panel transitions, not globally).

### Risk colour is monotonic in salience

The single most load-bearing rule in the palette. Risk colours are ordered by how strongly they pull the eye, not merely by hue:

| Tier | Token | Rationale |
|---|---|---|
| Critical | `--risk-critical` `#ff3b47` | Loudest thing on any screen |
| High | `--risk-high` `#ff7d1a` | |
| Medium | `--risk-medium` `#e0a800` | |
| Low / none | `--risk-low` `#64748b`, `--risk-none` | Quiet slate — a baseline, not an achievement |

`--risk-low` was previously a saturated green. Because >99% of entities sit in that band, the calm baseline became the loudest element on every screen — the dashboard's risk donut rendered as one big green ring reading "all clear" while genuinely critical entities went unnoticed. Green is now reserved as `--status-ok` for real positive confirmations (resolved, cleared, closed).

`lib/theme.ts` mirrors these values for consumers that can't read CSS custom properties (Cytoscape stylesheets, deck.gl layer props, Recharts/visx). It also owns `riskTier(score)`, the shared 80/60/35 banding used by both the Graph Explorer's ring colours and the Map's point colours — the two surfaces must agree on what "high risk" looks like.

### Density

`--row-height` (44px), `--row-height-compact` (36px) and `--control-height` (34px) drive list/table/toolbar rhythm so every surface scans at the same cadence. ARGUS is a data-dense product: list screens (Alerts, Cases, Search) target ~15–20 rows per screen rather than oversized cards.

`lib/cn.ts` is the one shared helper for conditional class names (`cn(styles.item, active && styles.itemActive)`), used everywhere instead of each component re-implementing `[a, b && c].filter(Boolean).join(" ")`. `lib/theme.ts` is the single source for colors that must be readable from plain JS/TS — Cytoscape stylesheets, recharts/deck.gl props — where a CSS custom property can't be used directly; its values are kept in sync with `styles/tokens.css` by convention, not by import (CSS can't be imported into JS here).

`components/ui/` holds the shared primitives every page builds on: `Badge`, `Button`, `Card`, `EmptyState`, `Input`/`Select`/`Textarea`, `Modal` (portal-based, Escape/backdrop-close, returns focus on close), `RiskBadge`, `Skeleton`, `Spinner`, `Table` (generic `columns`/`rows`/`getRowKey` — used by the Cases queue and Analytics' result tables instead of each hand-rolling its own `<table>`), `Tabs`, and `Toast` (`ToastProvider` mounted once in `app/providers.tsx`; call `useToast().showToast(message, tone)` from anywhere — Cases and Scenario both use it for create/generate feedback).

Four form/control primitives exist specifically because native controls render with OS chrome that breaks the dark surface language:

- **`Checkbox`** — the styled box used by Search's facets, with an optional trailing count.
- **`RangeSlider`** — labelled slider; `riskRamp` paints the filled track with the risk gradient so a risk threshold explains itself.
- **`SelectControl`** — toolbar-grade select with a leading icon and an `active` state so a non-default filter is visible without opening the menu. Used by both canvas toolbars.
- **`SegmentedControl`** — mutually-exclusive filter switch with optional counts, used where two competing underline tab-rows previously left it ambiguous which row scoped which axis (Alerts, Cases).

`ToastProvider` resolves its client-only portal through `useSyncExternalStore` rather than a `useEffect` mount flag, so the first client render matches the server's exactly and hydration has nothing to reconcile.
