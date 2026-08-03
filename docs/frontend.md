# Frontend

Scope: the Next.js application — routes, data fetching, state management, and the three canvas-heavy modules (Graph Explorer, Map, Timeline) that carry the most implementation complexity. For the API contract every hook talks to, see [api.md](api.md).

Next.js 16 (App Router), TypeScript, React 19. Vanilla CSS Modules — no Tailwind, no component library. Dependency manifest: `frontend/package.json`.

> **Next.js 16 note**: `frontend/AGENTS.md` flags that this Next.js major version has breaking changes from what most training data assumes — check `node_modules/next/dist/docs/` before relying on remembered App Router conventions.

## Folder structure

```
frontend/src/
├── app/                     # App Router pages — one folder per route
│   ├── layout.tsx            # root layout: fonts, <Providers>, <AppShell>
│   ├── providers.tsx          # TanStack Query provider
│   ├── error.tsx               # root error boundary
│   ├── dashboard/, graph/, map/, timeline/, search/,
│   │   entities/[id]/, cases/, cases/[id]/, alerts/,
│   │   analytics/, scenario/, settings/
├── components/
│   ├── layout/                # AppShell, Sidebar, Topbar, PageShell
│   ├── graph/                  # GraphCanvas, GraphControls, NodeDetailPanel
│   ├── map/                    # ArgusMap, MapControls, SelectedEntityPopup
│   ├── timeline/                # TimelineChart
│   ├── dashboard/                # StatCard, RiskDonut, CaseList, IncidentFeed
│   ├── entity/                    # EntityCard, EntityTypeIcon, RiskScoreWidget
│   ├── assistant/                  # AskArgusPanel
│   └── ui/                          # Badge, Button, Card, EmptyState, RiskBadge, Skeleton, Spinner, Tabs
├── hooks/                    # one file per resource, TanStack Query wrappers over lib/api.ts
├── lib/                      # api.ts, types.ts, constants.ts, entityDisplay.ts, formatters.ts, queryClient.ts
└── stores/                   # uiStore.ts (Zustand)
```

## Routes

| Path | Renders | Primary hook(s) |
|---|---|---|
| `/dashboard` | Command-center overview: stat cards, incident feed, risk donut, recent cases | `useDashboardSummary` |
| `/graph` | Cytoscape.js canvas — the Graph Explorer | `useGraphOverview`, `useSubgraph` |
| `/search` | Full-text search with type/risk facets | `useSearch` |
| `/map` | MapLibre + deck.gl over India | `useMapEntities`, `useMapShipments` |
| `/timeline` | @visx swimlane chart | `useGlobalTimeline` |
| `/entities/[id]` | Entity profile — Properties/Risk/Activity/Summary tabs | `useEntity`, `useEntityTimeline`, `useEntitySummary` |
| `/cases`, `/cases/[id]` | Case list + workspace (evidence board, notes, summary) | `useCases`, `useCase`, `useCaseSummary` |
| `/alerts` | Alert review queue | `useAlerts`, `useReviewAlert` |
| `/analytics` | Algorithm picker + result renderer | `useAnalyticsJob` |
| `/scenario` | Scenario Generator wizard | `useScenarioTypes`, `useScenarioJob` |
| `/settings` | Data/Appearance/Performance/About, all backed by real stats | `useDashboardSummary` |

## App shell and layout

`app/layout.tsx` wraps every page in `<Providers>` (TanStack Query) and `<AppShell>` (`components/layout/AppShell.tsx`), which composes `Sidebar` + `Topbar` + the page content + a globally-mounted `AskArgusPanel` (renders nothing if the optional assistant is unavailable — see [ai-layer.md](ai-layer.md)).

`PageShell` (`components/layout/PageShell.tsx`) is the per-page content wrapper: it renders a title/subtitle/actions header for normal pages, or — passed `full` — a zero-padding full-bleed container for the two canvas-style pages (Graph, Map) that need to own their own layout.

Navigation is data-driven from `lib/constants.ts`'s `NAV_GROUPS` (four groups: primary nav, Investigation, Tools, Settings) — `Sidebar` renders this list and highlights the active route via `usePathname()`. It also holds its own collapse state in `uiStore` (Zustand).

Keyboard shortcuts (registered in `Topbar.tsx` and `AskArgusPanel.tsx` via `window.addEventListener("keydown", ...)`):

| Shortcut | Action |
|---|---|
| `⌘K` / `Ctrl+K` | Navigate to `/search` |
| `⌘B` / `Ctrl+B` | Navigate to `/graph` |
| `⌘J` / `Ctrl+J` | Toggle Ask ARGUS (only registered when the assistant is available) |

## Data fetching

`lib/api.ts`'s `apiFetch<T>(path, init)` is the single fetch wrapper every hook uses: prefixes `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`), attaches `Authorization: Bearer {NEXT_PUBLIC_ARGUS_API_TOKEN}`, throws a typed `ApiError` (carries `status`) on any non-2xx response, and returns the parsed `Envelope<T>` (mirrors the backend's [Envelope shape](backend.md#response-envelope) — `lib/api.ts` redeclares the interface rather than sharing a types package, consistent with the deliberate frontend/backend separation described in [architecture.md](architecture.md#why-three-separate-deployables-instead-of-one)).

`lib/queryClient.ts` configures TanStack Query defaults: 30s `staleTime`, `refetchOnWindowFocus: false`, one retry. Every `hooks/use*.ts` file follows the same shape: a `useQuery` wrapping `apiFetch` for reads, `useMutation` + `queryClient.invalidateQueries` for writes.

### The job-polling hook pattern

`useAnalyticsJob<T>()` (`hooks/useAnalytics.ts`) and `useScenarioJob()` (`hooks/useScenario.ts`) both implement the same client-side half of the [background-job contract](backend.md#background-jobs): a `useMutation` (`start`) kicks off the job and captures the returned `job_id` into local state, and a `useQuery` (`job`) polls `GET .../results/{job_id}` (or `.../status/{job_id}`) with `refetchInterval` conditional on `status === "running"` — so polling stops itself the instant the job settles. `useAnalyticsJob` polls every 1.2s; `useScenarioJob` every 0.9s (it's rendering live per-stage progress, so a tighter interval reads better).

## Graph Explorer

`components/graph/GraphCanvas.tsx` wraps Cytoscape.js behind an imperative handle (`GraphCanvasHandle`): `addElements`, `fit`, `runLayout`, `highlightNeighborhood`, `highlightPath`. The Cytoscape instance itself is created **once**, in a mount-only `useEffect` (`[]` deps) — rebuilding it on every parent re-render would destroy the user's pan/zoom/layout state. This creates a classic stale-closure risk: `cy.on("tap", ...)` handlers registered in that effect would otherwise close over whatever `onSelectNode`/`onExpandNode` props existed on the *first* render, forever. The fix is a pair of refs (`onSelectNodeRef`, `onExpandNodeRef`) updated on every render, with the Cytoscape event handlers calling through the ref rather than the prop directly — see the comment block at the top of `GraphCanvas.tsx` for the full reasoning. This exact bug was what surfaced when the shortest-path feature needed the tap handler to read fresh `pathMode` state; `highlightNeighborhood` alone had never exposed it because it only touches a ref.

`app/graph/page.tsx` owns the interaction state: selected node (drives `NodeDetailPanel`), current layout, and path-finding mode (`pathMode`/`pathFrom` — clicking two nodes while active calls `GET /api/graph/shortest-path` and highlights the result via `highlightPath`). `GraphControls.tsx` renders the layout picker, fit button, and the path-mode toggle; `GraphLegend` is a static color key.

## Map

`components/map/ArgusMap.tsx` layers deck.gl (`ScatterplotLayer` for entities, `ArcLayer` for shipment routes) on top of a MapLibre GL base map via `MapboxOverlay` — both the base map instance and the overlay are created once in a mount-only effect, mirroring the Graph Explorer's pattern. `maplibre-gl` is pinned to `^3.6.2` specifically — newer major versions break deck.gl's shared WebGL context in this stack, confirmed during development. Route anomalies render as thicker, differently-colored arcs; risk ≥60 entities render larger and red.

## Timeline

`components/timeline/TimelineChart.tsx` — a hand-built @visx swimlane chart (four lanes: Incidents, Transactions, Communications, Events), not a Recharts chart, because the timeline needs heterogeneous point types on shared lanes with custom tooltips, which is easier to get right with @visx's low-level primitives (`scaleTime`, `scaleBand`, `Group`, `useTooltip`) than to force through a pre-built chart component.

## Entity display for denormalized references

`Case.linked_entities` and `Incident.involved_entities` come back from the API as raw `{label, properties}` pairs (the node's native Neo4j properties), not the normalized `GraphNode` shape (`id`/`name`/`risk_score`/...) that `/api/entities/*` returns. `lib/entityDisplay.ts`'s `entityId()`/`entityName()` resolve the correct ID/name field per label (mirroring `backend/app/repositories/entity_labels.py`'s mapping) so the Cases and Alerts pages can link to `/entities/{id}` without special-casing every label inline.

## State management

Three layers, each with a distinct job:

- **TanStack Query** — all server state (everything fetched from the API). This is the large majority of state in the app.
- **Zustand** (`stores/uiStore.ts`) — the one piece of cross-component client UI state: sidebar collapsed/expanded.
- **Local component `useState`** — everything else (form inputs, selected tabs, graph interaction mode). `cases/[id]/page.tsx`'s `NotesPanel` is a deliberate example: it's extracted as its own keyed child component with its own local `useState(initialNotes)` rather than syncing server data into local state via `useEffect`, specifically to avoid a "setState in effect" anti-pattern — remounting via `key={caseDetail.case_id}` resets the local draft cleanly when the case changes.

## Design system

CSS Modules per component/page (`*.module.css` next to each `.tsx`), CSS custom properties for the shared palette (`--text-primary`, `--surface-border`, `--risk-critical`, etc. — see any component's module CSS for the variable names in use). Fixed dark theme by design (see `app/settings/page.tsx`'s Appearance tab) — no light mode planned. Icons are `lucide-react`; motion is Framer Motion, used selectively (panel transitions, not globally).
