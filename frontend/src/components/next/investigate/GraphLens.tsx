"use client";

import type { Core } from "cytoscape";
import { useEffect, useRef, useState } from "react";
import { GraphCanvas, type GraphCanvasHandle } from "@/components/graph/GraphCanvas";
import { GraphMinimap } from "@/components/graph/GraphMinimap";
import { nextFixtureGraphEdges, nextFixtureSubjects } from "@/lib/next/fixtures";
import { useNextScopeStore } from "@/stores/nextScopeStore";
import styles from "./InvestigateWorkspace.module.css";

/**
 * The Graph lens — the real Cytoscape canvas (`GraphCanvas`) and its
 * existing minimap, fed fixture nodes/edges instead of a live subgraph
 * fetch. `isolateNeighborhood` is the same focus mechanism already shipping
 * on `/graph` (`GraphCanvasHandle`, see `app/(app)/graph/page.tsx`) — reused
 * here rather than reimplemented, driven by the shared scope bus's
 * `focusId` instead of page-local state.
 *
 * `onExpandNode` is a required prop on `GraphCanvas` but has nothing to do
 * in fixture mode: expanding a node's neighborhood needs the real
 * `/api/entities/{id}/graph` endpoint, which doesn't know about fixture IDs.
 * Left as a documented no-op rather than silently wired to something that
 * would 404 — this becomes real in Phase 12 alongside everything else.
 */
export function GraphLens() {
  const canvasRef = useRef<GraphCanvasHandle>(null);
  const [cy, setCy] = useState<Core | null>(null);
  const select = useNextScopeStore((s) => s.select);
  const focusId = useNextScopeStore((s) => s.focusId);
  const setFocus = useNextScopeStore((s) => s.setFocus);

  useEffect(() => {
    canvasRef.current?.isolateNeighborhood(focusId);
  }, [focusId]);

  useEffect(() => {
    canvasRef.current?.highlightNeighborhood(focusId);
  }, [focusId]);

  return (
    <>
      <GraphCanvas
        ref={canvasRef}
        initialNodes={nextFixtureSubjects}
        initialEdges={nextFixtureGraphEdges}
        onSelectNode={(id) => select(id)}
        onSelectEdge={() => {}}
        onExpandNode={() => {
          // No-op in the fixture phase — see the module docstring.
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
        RING = RISK TIER · EDGE SOLID/DASHED = CORRELATION TIER (ESTABLISHED · PROBABLE · POSSIBLE)
      </div>
    </>
  );
}
