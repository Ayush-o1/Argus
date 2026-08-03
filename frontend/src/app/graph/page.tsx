"use client";

import { Waypoints } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useRef, useState } from "react";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { PageShell } from "@/components/layout/PageShell";
import { GraphCanvas, type GraphCanvasHandle, type LayoutName } from "@/components/graph/GraphCanvas";
import { GraphControls, GraphLegend } from "@/components/graph/GraphControls";
import { NodeDetailPanel } from "@/components/graph/NodeDetailPanel";
import { useGraphOverview, useSubgraph } from "@/hooks/useGraph";
import { apiFetch } from "@/lib/api";
import type { Subgraph } from "@/lib/types";
import styles from "./page.module.css";

export default function GraphPage() {
  return (
    <Suspense fallback={<GraphLoadingFallback />}>
      <GraphPageInner />
    </Suspense>
  );
}

function GraphLoadingFallback() {
  return (
    <PageShell full>
      <div className={styles.wrap}>
        <div className={styles.centerState}>
          <Spinner size={28} />
        </div>
      </div>
    </PageShell>
  );
}

function GraphPageInner() {
  const searchParams = useSearchParams();
  const seed = searchParams.get("seed") ?? undefined;

  const overviewQuery = useGraphOverview();
  const seedQuery = useSubgraph(seed, 1);
  const { data, isLoading } = seed ? seedQuery : overviewQuery;

  return (
    <PageShell full>
      <div className={styles.wrap}>
        {isLoading || !data ? (
          <div className={styles.centerState}>
            <Spinner size={28} />
          </div>
        ) : data.nodes.length === 0 ? (
          <div className={styles.centerState}>
            <EmptyState
              icon={Waypoints}
              title="No graph data"
              description="No entities have been generated yet, or this entity has no connections."
            />
          </div>
        ) : (
          <GraphExplorerView key={seed ?? "overview"} data={data} />
        )}
      </div>
    </PageShell>
  );
}

function GraphExplorerView({ data }: { data: Subgraph }) {
  const canvasRef = useRef<GraphCanvasHandle>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [layout, setLayout] = useState<LayoutName>("cose");
  const [counts, setCounts] = useState({ nodes: data.nodes.length, edges: data.edges.length });

  function handleSelect(nodeId: string | null) {
    setSelectedId(nodeId);
    canvasRef.current?.highlightNeighborhood(nodeId);
  }

  async function handleExpand(nodeId: string) {
    const result = await apiFetch<Subgraph>(`/api/entities/${nodeId}/graph?depth=1`);
    canvasRef.current?.addElements(result.data.nodes, result.data.edges);
    setCounts((prev) => ({
      nodes: prev.nodes + result.data.nodes.length,
      edges: prev.edges + result.data.edges.length,
    }));
  }

  function handleLayoutChange(name: LayoutName) {
    setLayout(name);
    canvasRef.current?.runLayout(name);
  }

  return (
    <>
      <GraphControls
        layout={layout}
        onLayoutChange={handleLayoutChange}
        onFit={() => canvasRef.current?.fit()}
        nodeCount={counts.nodes}
        edgeCount={counts.edges}
      />
      <GraphCanvas
        ref={canvasRef}
        initialNodes={data.nodes}
        initialEdges={data.edges}
        onSelectNode={handleSelect}
        onExpandNode={handleExpand}
      />
      <GraphLegend />
      {selectedId ? (
        <NodeDetailPanel entityId={selectedId} onExpand={handleExpand} onClose={() => handleSelect(null)} />
      ) : null}
    </>
  );
}
