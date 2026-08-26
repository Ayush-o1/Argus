"use client";

import type { Core } from "cytoscape";
import { useEffect, useRef, useState } from "react";
import { GraphCanvas, type GraphCanvasHandle } from "@/components/graph/GraphCanvas";
import { GraphMinimap } from "@/components/graph/GraphMinimap";
import { useGraphOverview, useSubgraph } from "@/hooks/useGraph";
import { apiFetch } from "@/lib/api";
import type { Subgraph } from "@/lib/types";
import { useNextScopeStore } from "@/stores/nextScopeStore";
import styles from "./InvestigateWorkspace.module.css";

/**
 * The Graph lens — the real Cytoscape canvas (`GraphCanvas`) and its
 * existing minimap. `isolateNeighborhood` is the same focus mechanism
 * already shipping on `/graph` (`GraphCanvasHandle`, see
 * `app/(app)/graph/page.tsx`) — reused here rather than reimplemented,
 * driven by the shared scope bus's `focusId` instead of page-local state.
 *
 * Live-wired (Phase 12): `useGraphOverview`/`useSubgraph`/`onExpandNode`'s
 * `/api/entities/{id}/graph` call are the exact three data sources the real
 * `/graph` page uses (`seed ? seedQuery : overviewQuery`, and `handleExpand`)
 * — verified against the live backend at 257 nodes / 252 edges for the
 * overview, a size Cytoscape renders without difficulty; a 4,400-entity
 * unbounded fetch would not have been.
 *
 * The correlation-tier edge styling added to `graphStyle.ts` (solid/dashed
 * by established/probable/possible) doesn't apply to this data: real graph
 * edges carry a relationship type (TRANSACTED_WITH, COMMUNICATED_WITH, …),
 * not a correlation tier — that distinction lives in `/api/correlation`,
 * a separate resource this lens doesn't fetch. Those styling rules stay in
 * `graphStyle.ts` (harmless — they simply never match a real `relType`) but
 * the footnote below was corrected to describe what real edges actually
 * encode, rather than continuing to describe the fixture-only view.
 */
export function GraphLens() {
  const canvasRef = useRef<GraphCanvasHandle>(null);
  const [cy, setCy] = useState<Core | null>(null);
  const select = useNextScopeStore((s) => s.select);
  const focusId = useNextScopeStore((s) => s.focusId);
  const setFocus = useNextScopeStore((s) => s.setFocus);

  const { data: overview, isLoading: overviewLoading } = useGraphOverview();
  const { data: seeded, isLoading: seededLoading } = useSubgraph(focusId ?? undefined, 1);
  const data = focusId ? seeded : overview;
  const loading = focusId ? seededLoading : overviewLoading;

  useEffect(() => {
    canvasRef.current?.isolateNeighborhood(focusId);
  }, [focusId]);

  useEffect(() => {
    canvasRef.current?.highlightNeighborhood(focusId);
  }, [focusId]);

  if (loading || !data) {
    return <div className={styles.footnote}>Loading graph…</div>;
  }

  return (
    <>
      <GraphCanvas
        key={focusId ?? "overview"}
        ref={canvasRef}
        initialNodes={data.nodes}
        initialEdges={data.edges}
        onSelectNode={(id) => select(id)}
        onSelectEdge={() => {}}
        onExpandNode={async (nodeId) => {
          const result = await apiFetch<Subgraph>(`/api/entities/${encodeURIComponent(nodeId)}/graph?depth=1`);
          canvasRef.current?.addElements(result.data.nodes, result.data.edges);
        }}
        onReady={setCy}
      />
      <GraphMinimap cy={cy} />
      {focusId ? (
        <button type="button" className={styles.isolateExit} onClick={() => setFocus(null)}>
          EXIT ISOLATION
        </button>
      ) : null}
      <div className={styles.footnote}>
        RING = RISK TIER · EDGE COLOR = RELATIONSHIP TYPE · DOUBLE-CLICK A NODE TO EXPAND ITS NEIGHBORHOOD
      </div>
    </>
  );
}
