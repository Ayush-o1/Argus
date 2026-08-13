"use client";

import cytoscape, { type Core, type ElementDefinition, type Layouts } from "cytoscape";
import fcose from "cytoscape-fcose";
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import type { GraphEdge, GraphNode } from "@/lib/types";
import { riskTier } from "@/lib/theme";
import { buildGraphStylesheet, nodeSize } from "./graphStyle";

if (typeof cytoscape !== "undefined") {
  // Guarded so React StrictMode / HMR re-executing this module doesn't
  // register the extension twice, which cytoscape throws on.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const cy = cytoscape as any;
  if (!cy.__argusFcoseRegistered) {
    cytoscape.use(fcose);
    cy.__argusFcoseRegistered = true;
  }
}

export interface AddElementsResult {
  addedNodes: number;
  addedEdges: number;
}

export interface NeighborConnection {
  edge: GraphEdge;
  other: { id: string; name: string; label: string; riskScore: number };
  direction: "outgoing" | "incoming";
}

export interface EdgeDetail {
  edge: GraphEdge;
  source: { id: string; name: string; label: string };
  target: { id: string; name: string; label: string };
}

export interface GraphCanvasHandle {
  addElements: (nodes: GraphNode[], edges: GraphEdge[]) => AddElementsResult;
  fit: () => void;
  centerOn: (nodeId: string) => void;
  runLayout: (name: LayoutName) => void;
  highlightNeighborhood: (nodeId: string | null) => void;
  highlightPath: (nodeIds: string[]) => void;
  /** Hides every node whose entityLabel is in `hiddenLabels` (and any edge
   * touching one), without removing elements — re-showing a type is instant. */
  setTypeVisibility: (hiddenLabels: string[]) => void;
  /** Hides nodes below `minRisk` (0 = show all). */
  setRiskFilter: (minRisk: number) => void;
  /** Focus mode: hides everything outside the given node's neighborhood.
   * Pass null to clear. Composes with type/risk filters. */
  isolateNeighborhood: (nodeId: string | null) => void;
  getNeighborConnections: (nodeId: string) => NeighborConnection[];
  getEdgeDetail: (edgeId: string) => EdgeDetail | null;
}

export type LayoutName = "fcose" | "breadthfirst" | "concentric" | "grid";

interface GraphCanvasProps {
  initialNodes: GraphNode[];
  initialEdges: GraphEdge[];
  onSelectNode: (nodeId: string | null) => void;
  onSelectEdge: (edgeId: string | null) => void;
  onExpandNode: (nodeId: string) => void;
}

function truncateLabel(name: string): string {
  return name.length > 22 ? `${name.slice(0, 20)}…` : name;
}

function toElement(node: GraphNode): ElementDefinition {
  return {
    data: {
      id: node.id,
      label: node.name,
      displayLabel: truncateLabel(node.name),
      entityLabel: node.label,
      riskScore: node.risk_score,
      riskTier: riskTier(node.risk_score),
      size: nodeSize(node.risk_score),
    },
  };
}

function toEdgeElement(edge: GraphEdge): ElementDefinition {
  return {
    data: {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      relType: edge.type,
      properties: edge.properties ?? {},
    },
  };
}

const LABEL_HUB_DEGREE = 4;

export const GraphCanvas = forwardRef<GraphCanvasHandle, GraphCanvasProps>(
  ({ initialNodes, initialEdges, onSelectNode, onSelectEdge, onExpandNode }, ref) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const cyRef = useRef<Core | null>(null);
    const currentLayoutRef = useRef<Layouts | null>(null);
    const rafRef = useRef<number | null>(null);

    // The setup effect below only runs once (on mount) so Cytoscape's own
    // event handlers stay attached across re-renders — but that means a
    // handler closing directly over the callback props would keep calling
    // whatever those props were on that first render forever. Refs updated
    // every render sidestep that stale-closure trap without needing to tear
    // down and rebuild the whole graph instance on every parent re-render.
    const onSelectNodeRef = useRef(onSelectNode);
    const onSelectEdgeRef = useRef(onSelectEdge);
    const onExpandNodeRef = useRef(onExpandNode);
    onSelectNodeRef.current = onSelectNode;
    onSelectEdgeRef.current = onSelectEdge;
    onExpandNodeRef.current = onExpandNode;

    // Visibility state lives outside React — three independent reasons a node
    // can be hidden (type filter, risk floor, focus isolation) are unioned
    // into a single `.hidden` class per element every time any one changes.
    const hiddenTypesRef = useRef<string[]>([]);
    const minRiskRef = useRef(0);
    const focusIdRef = useRef<string | null>(null);

    function runLayoutInternal(cy: Core, options: cytoscape.LayoutOptions) {
      currentLayoutRef.current?.stop();
      const layout = cy.layout(options);
      currentLayoutRef.current = layout;
      layout.run();
    }

    function applyVisibility(cy: Core) {
      const focusNode = focusIdRef.current ? cy.getElementById(focusIdRef.current) : null;
      const allowed = focusNode && focusNode.nonempty() ? focusNode.closedNeighborhood() : null;

      cy.batch(() => {
        cy.nodes().forEach((n) => {
          const typeHidden = hiddenTypesRef.current.includes(n.data("entityLabel"));
          const riskHidden = (n.data("riskScore") ?? 0) < minRiskRef.current;
          const focusHidden = allowed ? allowed.filter((x) => x.same(n)).empty() : false;
          n.toggleClass("hidden", typeHidden || riskHidden || focusHidden);
        });
        cy.edges().forEach((e) => {
          e.toggleClass("hidden", e.source().hasClass("hidden") || e.target().hasClass("hidden"));
        });
      });
    }

    /** Importance-gated labels: always show selected/highlighted nodes; below
     * that, only high-risk and high-degree "hub" entities earn a label at low
     * zoom, and everything opens up once the analyst has zoomed in far enough
     * that crowding stops being a problem. */
    function updateLabelVisibility(cy: Core) {
      const zoom = cy.zoom();
      cy.batch(() => {
        cy.nodes().forEach((n) => {
          if (n.hasClass("highlighted") || n.selected()) {
            n.removeClass("label-hidden");
            return;
          }
          const tier = n.data("riskTier");
          const isHub = n.degree(false) >= LABEL_HUB_DEGREE;
          let show: boolean;
          if (zoom >= 1.1) show = true;
          else if (zoom >= 0.7) show = tier === "critical" || tier === "high" || isHub;
          else show = tier === "critical";
          n.toggleClass("label-hidden", !show);
        });
      });
    }

    function scheduleLabelUpdate(cy: Core) {
      if (rafRef.current !== null) return;
      rafRef.current = requestAnimationFrame(() => {
        rafRef.current = null;
        updateLabelVisibility(cy);
      });
    }

    useEffect(() => {
      if (!containerRef.current) return;

      const cy = cytoscape({
        container: containerRef.current,
        elements: [...initialNodes.map(toElement), ...initialEdges.map(toEdgeElement)],
        style: buildGraphStylesheet(),
        minZoom: 0.1,
        maxZoom: 3,
        wheelSensitivity: 0.25,
      });
      runLayoutInternal(cy, {
        name: "fcose",
        quality: "default",
        animate: true,
        randomize: true,
        fit: true,
        padding: 48,
        nodeRepulsion: 9000,
        idealEdgeLength: 85,
        nodeSeparation: 80,
        packComponents: true,
      } as cytoscape.LayoutOptions);
      updateLabelVisibility(cy);

      cy.on("tap", "node", (evt) => {
        onSelectEdgeRef.current(null);
        onSelectNodeRef.current(evt.target.id());
      });
      cy.on("tap", "edge", (evt) => {
        onSelectNodeRef.current(null);
        cy.elements().removeClass("edge-selected");
        evt.target.addClass("edge-selected");
        onSelectEdgeRef.current(evt.target.id());
      });
      cy.on("tap", (evt) => {
        if (evt.target === cy) {
          onSelectNodeRef.current(null);
          onSelectEdgeRef.current(null);
        }
      });
      cy.on("dbltap", "node", (evt) => {
        onExpandNodeRef.current(evt.target.id());
      });
      cy.on("zoom", () => scheduleLabelUpdate(cy));
      cy.on("layoutstop", () => updateLabelVisibility(cy));

      cyRef.current = cy;
      return () => {
        // Stop the running layout's animation-frame loop *before* destroying —
        // fcose's physics simulation schedules many recursive rAF ticks, and
        // React StrictMode's dev-only mount/unmount/remount cycle otherwise lets
        // a tick fire after destroy, throwing from cytoscape's now-null internals.
        currentLayoutRef.current?.stop();
        if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
        cy.stop();
        cy.destroy();
        cyRef.current = null;
      };
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useImperativeHandle(ref, () => ({
      addElements(nodes, edges) {
        const cy = cyRef.current;
        if (!cy) return { addedNodes: 0, addedEdges: 0 };
        // Nodes/edges the caller fetched (e.g. a neighborhood expansion or a
        // shortest path) commonly overlap with what's already on the canvas —
        // the return value here reports only the genuinely new count, so the
        // "N nodes · M edges" badge in GraphControls doesn't drift from what's
        // actually rendered.
        const newNodeDefs = nodes.filter((n) => cy.getElementById(n.id).empty());
        const newEdgeDefs = edges.filter((e) => cy.getElementById(e.id).empty());
        if (newNodeDefs.length === 0 && newEdgeDefs.length === 0) {
          return { addedNodes: 0, addedEdges: 0 };
        }
        cy.add([...newNodeDefs.map(toElement), ...newEdgeDefs.map(toEdgeElement)]);
        runLayoutInternal(cy, { name: "fcose", quality: "default", animate: true, randomize: false, fit: false } as cytoscape.LayoutOptions);
        applyVisibility(cy);
        return { addedNodes: newNodeDefs.length, addedEdges: newEdgeDefs.length };
      },
      fit() {
        cyRef.current?.fit(undefined, 40);
      },
      centerOn(nodeId) {
        const cy = cyRef.current;
        if (!cy) return;
        const node = cy.getElementById(nodeId);
        if (node.empty()) return;
        cy.animate({ fit: { eles: node.closedNeighborhood(), padding: 90 } }, { duration: 450 });
      },
      runLayout(name) {
        const cy = cyRef.current;
        if (!cy) return;
        const options =
          name === "breadthfirst"
            ? { name, directed: true, spacingFactor: 1.4 }
            : name === "fcose"
              ? { name, quality: "default", nodeRepulsion: 9000, idealEdgeLength: 85, packComponents: true }
              : { name };
        runLayoutInternal(cy, { ...options, animate: true, fit: true, padding: 44 } as cytoscape.LayoutOptions);
      },
      highlightNeighborhood(nodeId) {
        const cy = cyRef.current;
        if (!cy) return;
        cy.elements().removeClass("faded highlighted");
        if (!nodeId) {
          updateLabelVisibility(cy);
          return;
        }
        const node = cy.getElementById(nodeId);
        const neighborhood = node.closedNeighborhood();
        cy.elements().difference(neighborhood).addClass("faded");
        neighborhood.addClass("highlighted");
        updateLabelVisibility(cy);
      },
      setTypeVisibility(hiddenLabels) {
        const cy = cyRef.current;
        if (!cy) return;
        hiddenTypesRef.current = hiddenLabels;
        applyVisibility(cy);
      },
      setRiskFilter(minRisk) {
        const cy = cyRef.current;
        if (!cy) return;
        minRiskRef.current = minRisk;
        applyVisibility(cy);
      },
      isolateNeighborhood(nodeId) {
        const cy = cyRef.current;
        if (!cy) return;
        focusIdRef.current = nodeId;
        applyVisibility(cy);
        if (nodeId) {
          const node = cy.getElementById(nodeId);
          if (node.nonempty()) {
            cy.animate({ fit: { eles: node.closedNeighborhood(), padding: 70 } }, { duration: 400 });
          }
        } else {
          cy.animate({ fit: { eles: cy.elements(".hidden").absoluteComplement(), padding: 44 } }, { duration: 400 });
        }
      },
      getNeighborConnections(nodeId) {
        const cy = cyRef.current;
        if (!cy) return [];
        const node = cy.getElementById(nodeId);
        if (node.empty()) return [];
        return node
          .connectedEdges()
          .map((e) => {
            const outgoing = e.source().id() === nodeId;
            const other = outgoing ? e.target() : e.source();
            return {
              edge: {
                id: e.id(),
                source: e.data("source"),
                target: e.data("target"),
                type: e.data("relType"),
                properties: e.data("properties") ?? {},
              },
              other: {
                id: other.id(),
                name: other.data("label"),
                label: other.data("entityLabel"),
                riskScore: other.data("riskScore") ?? 0,
              },
              direction: outgoing ? "outgoing" : "incoming",
            } as NeighborConnection;
          })
          .sort((a, b) => b.other.riskScore - a.other.riskScore);
      },
      getEdgeDetail(edgeId) {
        const cy = cyRef.current;
        if (!cy) return null;
        const edge = cy.getElementById(edgeId);
        if (edge.empty()) return null;
        const source = edge.source();
        const target = edge.target();
        return {
          edge: {
            id: edge.id(),
            source: source.id(),
            target: target.id(),
            type: edge.data("relType"),
            properties: edge.data("properties") ?? {},
          },
          source: { id: source.id(), name: source.data("label"), label: source.data("entityLabel") },
          target: { id: target.id(), name: target.data("label"), label: target.data("entityLabel") },
        };
      },
      highlightPath(nodeIds) {
        const cy = cyRef.current;
        if (!cy) return;
        cy.elements().removeClass("faded highlighted");
        if (nodeIds.length === 0) {
          updateLabelVisibility(cy);
          return;
        }
        const pathNodes = cy.collection();
        for (const id of nodeIds) pathNodes.merge(cy.getElementById(id));
        const pathEdges = pathNodes.edgesWith(pathNodes);
        const path = pathNodes.union(pathEdges);
        cy.elements().difference(path).addClass("faded");
        path.addClass("highlighted");
        updateLabelVisibility(cy);
        cy.animate({ fit: { eles: path, padding: 60 } }, { duration: 400 });
      },
    }));

    return <div ref={containerRef} style={{ width: "100%", height: "100%" }} />;
  },
);

GraphCanvas.displayName = "GraphCanvas";
