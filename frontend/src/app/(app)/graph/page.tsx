"use client";

import { Waypoints } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useRef, useState } from "react";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { PageShell } from "@/components/layout/PageShell";
import { GraphCanvas, type EdgeDetail, type GraphCanvasHandle, type LayoutName, type NeighborConnection } from "@/components/graph/GraphCanvas";
import { GraphControls, GraphLegend } from "@/components/graph/GraphControls";
import { NodeDetailPanel } from "@/components/graph/NodeDetailPanel";
import { RelationshipPanel } from "@/components/graph/RelationshipPanel";
import { useGraphOverview, useSubgraph } from "@/hooks/useGraph";
import { apiFetch } from "@/lib/api";
import type { GraphNode, Subgraph } from "@/lib/types";
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
          <GraphExplorerView key={seed ?? "overview"} data={data} isSeeded={Boolean(seed)} />
        )}
      </div>
    </PageShell>
  );
}

function GraphExplorerView({ data, isSeeded }: { data: Subgraph; isSeeded: boolean }) {
  const router = useRouter();
  const canvasRef = useRef<GraphCanvasHandle>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [connections, setConnections] = useState<NeighborConnection[]>([]);
  const [selectedEdge, setSelectedEdge] = useState<EdgeDetail | null>(null);
  const [layout, setLayout] = useState<LayoutName>("fcose");
  const [counts, setCounts] = useState({ nodes: data.nodes.length, edges: data.edges.length });
  const [pathMode, setPathMode] = useState(false);
  const [pathFrom, setPathFrom] = useState<string | null>(null);
  const [hiddenTypes, setHiddenTypes] = useState<string[]>([]);
  const [riskFilter, setRiskFilter] = useState(0);
  const [focusedId, setFocusedId] = useState<string | null>(null);

  function toggleType(label: string) {
    setHiddenTypes((prev) => {
      const next = prev.includes(label) ? prev.filter((t) => t !== label) : [...prev, label];
      canvasRef.current?.setTypeVisibility(next);
      return next;
    });
  }

  function handleRiskFilterChange(minRisk: number) {
    setRiskFilter(minRisk);
    canvasRef.current?.setRiskFilter(minRisk);
  }

  function handleSelect(nodeId: string | null) {
    if (pathMode) {
      if (!nodeId) return;
      if (!pathFrom) {
        setPathFrom(nodeId);
        return;
      }
      void findPath(pathFrom, nodeId);
      return;
    }
    setSelectedEdge(null);
    setSelectedId(nodeId);
    canvasRef.current?.highlightNeighborhood(nodeId);
    setConnections(nodeId ? (canvasRef.current?.getNeighborConnections(nodeId) ?? []) : []);
  }

  function handleSelectEdge(edgeId: string | null) {
    if (!edgeId) {
      setSelectedEdge(null);
      return;
    }
    setSelectedId(null);
    canvasRef.current?.highlightNeighborhood(null);
    const detail = canvasRef.current?.getEdgeDetail(edgeId) ?? null;
    setSelectedEdge(detail);
  }

  function handleFocus(nodeId: string) {
    setFocusedId(nodeId);
    canvasRef.current?.isolateNeighborhood(nodeId);
  }

  function handleClearFocus() {
    setFocusedId(null);
    canvasRef.current?.isolateNeighborhood(null);
  }

  async function findPath(fromId: string, toId: string) {
    const result = await apiFetch<Subgraph & { length: number }>(
      `/api/graph/shortest-path?from_id=${fromId}&to_id=${toId}`,
    );
    if (result.data) {
      const added = canvasRef.current?.addElements(result.data.nodes, result.data.edges);
      canvasRef.current?.highlightPath(result.data.nodes.map((n) => n.id));
      if (added) {
        setCounts((prev) => ({ nodes: prev.nodes + added.addedNodes, edges: prev.edges + added.addedEdges }));
      }
    }
    setPathMode(false);
    setPathFrom(null);
  }

  function togglePathMode() {
    setPathMode((prev) => !prev);
    setPathFrom(null);
    canvasRef.current?.highlightPath([]);
  }

  async function handleExpand(nodeId: string) {
    const result = await apiFetch<Subgraph>(`/api/entities/${nodeId}/graph?depth=1`);
    const added = canvasRef.current?.addElements(result.data.nodes, result.data.edges);
    if (added) {
      setCounts((prev) => ({ nodes: prev.nodes + added.addedNodes, edges: prev.edges + added.addedEdges }));
    }
    if (selectedId === nodeId) {
      setConnections(canvasRef.current?.getNeighborConnections(nodeId) ?? []);
    }
  }

  async function handleSearchSelect(node: GraphNode) {
    const result = await apiFetch<Subgraph>(`/api/entities/${node.id}/graph?depth=1`);
    const added = canvasRef.current?.addElements(result.data.nodes, result.data.edges);
    if (added) {
      setCounts((prev) => ({ nodes: prev.nodes + added.addedNodes, edges: prev.edges + added.addedEdges }));
    }
    handleSelect(node.id);
    canvasRef.current?.centerOn(node.id);
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
        pathMode={pathMode}
        onTogglePathMode={togglePathMode}
        pathModeHint={pathFrom ? `From ${pathFrom} — click an end entity` : "Click a start entity"}
        riskFilter={riskFilter}
        onRiskFilterChange={handleRiskFilterChange}
        isFocused={focusedId !== null}
        onClearFocus={handleClearFocus}
        onSearchSelect={handleSearchSelect}
        onResetView={isSeeded ? () => router.push("/graph") : undefined}
      />
      <GraphCanvas
        ref={canvasRef}
        initialNodes={data.nodes}
        initialEdges={data.edges}
        onSelectNode={handleSelect}
        onSelectEdge={handleSelectEdge}
        onExpandNode={handleExpand}
      />
      <GraphLegend hiddenTypes={hiddenTypes} onToggleType={toggleType} />
      {selectedId && !pathMode ? (
        <NodeDetailPanel
          entityId={selectedId}
          connections={connections}
          isFocused={focusedId === selectedId}
          onExpand={handleExpand}
          onFocus={handleFocus}
          onClearFocus={handleClearFocus}
          onSelectConnection={handleSelect}
          onClose={() => handleSelect(null)}
        />
      ) : null}
      {selectedEdge && !pathMode ? (
        <RelationshipPanel detail={selectedEdge} onSelectEntity={handleSelect} onClose={() => handleSelectEdge(null)} />
      ) : null}
    </>
  );
}
