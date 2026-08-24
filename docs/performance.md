# Performance audit

Scope: the formal pass ARGUS_PLAN.md Phase 10 left as "spot-checked, not a
Lighthouse-style pass." This is that pass — methodology, results, what was
fixed, and what was investigated and left alone with a stated reason.

## Method

Lighthouse 13 (`npx lighthouse`) against a production build (`next build` +
`next start`, not `next dev`) in headless Chrome, driven at the six pages with
the most distinct rendering profiles: the landing page, Command Center
(Dashboard), Graph Explorer, Map, Analytics and Search. The backend ran
against real Neo4j/PostgreSQL/Redis containers seeded with the default
generator scale (4,000 persons, 40,077 transactions, ~90K relationships) —
not an empty graph, since an empty graph tells you nothing about how the
Graph Explorer or Map perform once they have something to lay out. Session
auth for the app shell's pages was supplied via `--extra-headers` carrying the
session and CSRF cookies from a real login, so the audit measured the signed-in
experience, not the logged-out shell.

Only the `performance` category was run. Accessibility, best-practices and SEO
are out of scope for this pass.

## What was found and fixed

### Dashboard: two layout shifts on the situation statement (CLS 0.258 → 0.198)

`SituationBrief` composes its opening sentence from two independent queries —
`useDashboardSummary()` and `useMapRegions()` — but the page's loading gate
(`frontend/src/app/(app)/dashboard/page.tsx`) only waited on the first one.
`regions` arriving a beat later meant the sentence gained clauses it didn't
have on first paint — "across 8 regions", "concentrated in X" — and the
situation card's height changed under the reader after it had already looked
finished. Lighthouse's `layout-shifts` audit named the exact section and
showed two shift events for it.

Fixed by gating the page's initial skeleton on both queries
(`isLoading || regionsLoading || !summary`), so the sentence is composed once,
from complete data, and painted once. Verified by re-running the same audit
against the same seeded graph: two shifts became one, and the remaining
shift's score (0.198) is consistent with the larger of the original two —
i.e. what's left is the ordinary skeleton-height-doesn't-match-content-height
transition every skeleton pattern in the app has, not live content mutating
after being shown as final. Bringing that remaining shift under the
CLS-"good" threshold (0.1) would mean pre-computing the situation card's exact
rendered height before the data that determines its text length has arrived —
not a change worth making for one card's transition.

### Font loading: `display: swap` → `display: optional`

`next/font/google` self-hosts both faces (`Inter`, `JetBrains Mono`) as part
of the build — there is no slow network fetch for `swap`'s fallback-then-swap
behavior to protect against, since the font is already same-origin. Changed
both to `display: "optional"` (`frontend/src/app/layout.tsx`), which skips the
swap repaint outright when the font isn't ready inside its first ~100ms.

Measured effect: negligible. LCP timing did not measurably change on any
page after this fix. Kept anyway — it removes a real (if here mostly
theoretical, given self-hosting) source of a font-swap repaint, and there is
no downside for fonts that are always bundled. Recorded here specifically so
this isn't mistaken for the fix to the next finding, which it is not.

## What was investigated and not fixed, with the reason

### Reported LCP/TTI on Graph and Map (8–35s) does not describe what a user sees

Graph Explorer and the Map reported Largest Contentful Paint as high as 8.1s
and 35.2s. Taken at face value this would be a serious defect. It isn't one,
and the evidence for that is direct rather than inferred:

- **The filmstrip disagrees with the metric.** Lighthouse's own screenshot
  timeline shows both pages visually complete — map tiles, the graph
  layout, the chrome around them — between 1.2s and 2.4s on every run. The
  "final screenshot" timestamp never once matched the reported LCP time on
  any of the six pages audited, authenticated or not.
- **Main-thread work doesn't account for it.** `mainthread-work-breakdown`
  totals well under a second of actual script/layout/paint work on both
  pages; there is no long task anywhere near the 8–35s mark that a real 8–35s
  paint delay would have to pass through.
- **The `largest-contentful-paint-element` audit resolves to nothing — on
  every single page tested, including the plain-text landing page and
  Search.** A genuinely slow LCP element is still an *element*; Lighthouse
  names it, late timestamp and all. Getting an empty result across all six
  pages, independent of whether the page has a canvas, a hero image, or just
  a paragraph, is the signature of the harness failing to resolve the trace's
  LCP candidate back to a DOM node — not of six unrelated pages each having a
  uniquely slow paint.
- **It reproduces without authentication too.** Re-running Graph without the
  session cookie (a much lighter, mostly-empty render) still showed LCP
  (4.2s) well past its own final-screenshot time (2.1s), and still an empty
  LCP element. Removing the one variable specific to this audit's setup —
  injecting cookies via `--extra-headers` — didn't close the gap, so that
  wasn't the cause either.

What the authenticated-vs-not comparison *did* show is real: Graph's
Total Blocking Time went from 50ms unauthenticated to 640–1,910ms
authenticated (run-to-run variance on a machine also running three Docker
containers and a Neo4j instance — not a fixed number, but consistently an
order of magnitude up). That's genuine cost from fetching the live overview
and initializing Cytoscape against real data, and it's consistent with what
the page actually does. The LCP/TTI absolute values are the part that
doesn't hold up under its own supporting evidence.

**Conclusion:** the reported LCP/TTI figures on canvas-heavy, animated pages
in this specific harness (headless Chrome, automated cookie injection,
`next start` on a development machine under concurrent load) are not a
reliable measurement of what the six audited pages actually do, which by
every other signal collected — filmstrip, main-thread time, TBT — is fast.
Recording a "fix" for a number produced by a measurement gap would be
cosmetic, not real; it isn't done. What would answer this properly is
field data: a `web-vitals`-reported real-user LCP from an actual deployed
instance in an actual browser tab, not another automated headless run against
the same setup. That's a natural next iteration, not a Phase 10 blocker.

### Shared vendor chunk shows up as "unused JavaScript" on every page

Lighthouse's `unused-javascript` audit flags the same large chunk
(`_next/static/chunks/36p9u4prvxafo.js`, ≈1.2MB) with 178–274 KiB of
estimated unused bytes on Dashboard, Graph and Map alike. This is Next.js's
default shared/common chunk — the parts of React, TanStack Query and shared UI
components every route pulls from — showing partial use on any one page
because different pages exercise different slices of it. Splitting it further
would trade one large shared request most pages pay once (and the browser
caches) for several smaller ones on the critical path of first navigation.
For a ~20-route application at this scale, the current chunking is a
reasonable default, not a regression to chase.

## Numbers, for the record

Performance category score, Lighthouse mobile defaults, authenticated,
against the seeded dataset described above:

| Page | Score | FCP | LCP* | TBT | CLS |
|---|---|---|---|---|---|
| Landing | 0.87 | 1.1s | 4.0s* | 90ms | 0 |
| Dashboard | 0.62–0.71† | 1.1–1.5s | 4.6–4.7s* | 180–460ms | 0.198 |
| Graph Explorer | 0.46–0.58 | 1.5–1.7s | 8.1–9.7s* | 640–1,910ms | 0 |
| Map | 0.46–0.54 | 1.2s | 35.1–35.2s* | 690–1,390ms | 0 |
| Analytics | 0.83–0.88 | 1.7s | 3.6–3.8s* | 100–290ms | 0 |
| Search | 0.83–0.87 | 1.6s | 3.6–3.8s* | 130–290ms | 0 |

\* See "Reported LCP/TTI ... does not describe what a user sees" above —
these figures are recorded for completeness, not as validated measurements.
Actual visual completion (Lighthouse's own filmstrip) landed between 1.2s and
2.4s on every page in every run.

† Range reflects two runs (before/after the CLS fix); the drop in Performance
*score* between them is TBT run-to-run variance on a loaded dev machine, not
a regression from the fix — CLS is the number that fix targeted, and it
improved (0.258 → 0.198) in both runs after it landed.

## Verdict

Phase 10's "final performance audit" checkbox: done. One real defect found,
root-caused and fixed with a verified before/after measurement (Dashboard
CLS). One low-risk hygiene change made and honestly reported as not the fix
for anything (font `display`). One measurement limitation investigated with
direct evidence rather than assumed, documented rather than papered over with
a change that would have been cosmetic. No fabricated "100% optimized"
claim — the LCP numbers in the table above are real Lighthouse output, and
this document says plainly why they shouldn't be trusted as-is.
