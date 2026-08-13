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
| `/map` | MapLibre + deck.gl over India | `useMapEntities`, `useMapShipments` |
| `/timeline` | @visx swimlane chart | `useGlobalTimeline` |
| `/entities/[id]` | Entity profile — Properties/Risk/Activity/Cases & Alerts/Summary tabs | `useEntity`, `useEntityTimeline`, `useEntityCases`, `useEntityAlerts`, `useEntitySummary` |
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

## Data fetching

`lib/api.ts`'s `apiFetch<T>(path, init)` is the single fetch wrapper every hook uses: prefixes `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`), attaches `Authorization: Bearer {NEXT_PUBLIC_ARGUS_API_TOKEN}`, throws a typed `ApiError` (carries `status`) on any non-2xx response, and returns the parsed `Envelope<T>` (mirrors the backend's [Envelope shape](backend.md#response-envelope) — `lib/api.ts` redeclares the interface rather than sharing a types package, consistent with the deliberate frontend/backend separation described in [architecture.md](architecture.md#why-three-separate-deployables-instead-of-one)).

`lib/queryClient.ts` configures TanStack Query defaults: 30s `staleTime`, `refetchOnWindowFocus: false`, one retry. Every `hooks/use*.ts` file follows the same shape: a `useQuery` wrapping `apiFetch` for reads, `useMutation` + `queryClient.invalidateQueries` for writes.

### The job-polling hook pattern

`useAnalyticsJob<T>()` (`hooks/useAnalytics.ts`) and `useScenarioJob()` (`hooks/useScenario.ts`) both implement the same client-side half of the [background-job contract](backend.md#background-jobs): a `useMutation` (`start`) kicks off the job and captures the returned `job_id` into local state, and a `useQuery` (`job`) polls `GET .../results/{job_id}` (or `.../status/{job_id}`) with `refetchInterval` conditional on `status === "running"` — so polling stops itself the instant the job settles. `useAnalyticsJob` polls every 1.2s; `useScenarioJob` every 0.9s (it's rendering live per-stage progress, so a tighter interval reads better).

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

### Zoom-dependent rendering

The map switches representation at `HEX_ZOOM_THRESHOLD` (6.2) rather than drawing every point at every scale:

- **Below the threshold** — a `HexagonLayer` aggregates entities into density bins coloured by `MAX` risk within each bin, so a country-wide view shows *where* risk concentrates instead of thousands of overlapping dots. Hovering a bin reports its count; clicking flies in two zoom levels.
- **Above it** — a `ScatterplotLayer` of individual entities, sized and coloured by risk tier, with the selected entity drawn larger and ringed in white.
- **Above `LABEL_ZOOM_THRESHOLD` (7.5)** — a `TextLayer` labels only critical-risk entities and the current selection.

### Route hierarchy

Routes are split across two `ArcLayer`s so anomalies are never out-shouted by routine traffic. Anomalous routes always draw at full width and opacity and are the only pickable ones; normal routes render only when the filter is set to "all", at 0.6px and 22% opacity — present as texture, not as competition. `MapControls` exposes entity-type, risk-floor and route filters (all on the shared `SelectControl`, highlighted when non-default) plus an entity search that flies to a result.

Clicking an entity opens `SelectedEntityPopup` (profile + graph pivots); clicking an anomalous route opens `ShipmentDetailPopup` (carrier, status, anomaly flag, risk score).

`app/(app)/map/page.tsx` reads a `?focus=<entityId>` query param (used by the entity profile's "View on Map" action — see below): the matching entity is derived via `useMemo` over the already-loaded entity list rather than stored in state, and a `useEffect` flies the camera to it. Manual selection is tracked separately (`undefined` = no override yet, so the focused entity still wins; `null` = the popup was explicitly closed) to avoid syncing derived data into state.

## Timeline

`components/timeline/TimelineChart.tsx` — a hand-built @visx swimlane chart (four lanes: Incidents, Transactions, Communications, Events), not a Recharts chart, because the timeline needs heterogeneous point types on shared lanes with custom tooltips, which is easier to get right with @visx's low-level primitives (`scaleTime`, `scaleBand`, `Group`, `useTooltip`) than to force through a pre-built chart component.

## Cross-page linking

Entity, Case, Alert, Graph, and Map are meant to be jumped between, not treated as separate silos:

- Entity profile → `/graph?seed={id}` ("View in Graph"), `/map?focus={id}` (when the entity has `lat`/`lng`), and a "Cases & Alerts" tab backed by `GET /api/entities/{id}/cases` / `/alerts` — both reverse the same `Case-[:LINKED_TO]->Entity` and `Incident-[:INVOLVES]->Entity` relationships the forward-direction case/alert queries already use.
- Dashboard stat cards → `/cases` and `/alerts?status=Open` (the latter pre-selects the status tab via `useSearchParams`, which requires wrapping the page in `<Suspense>` per Next's static-export rules).
- Timeline incident tooltips → `/alerts`. (Getting a tooltip's embedded link to actually be clickable took a debounced-hide fix — a bare `onMouseLeave` on the 3px SVG circle closed the tooltip before the cursor could reach it; see the comment in `TimelineChart.tsx`.)
- Scenario Generator results → `/graph?seed=`, `/cases/{id}`, `/entities/{id}` for the storyline's key entity.

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
