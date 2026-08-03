"use client";

import cytoscape, { type Core, type ElementDefinition, type Layouts } from "cytoscape";
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import type { GraphEdge, GraphNode } from "@/lib/types";
import { buildGraphStylesheet, nodeSize } from "./graphStyle";

export interface GraphCanvasHandle {
  addElements: (nodes: GraphNode[], edges: GraphEdge[]) => void;
  fit: () => void;
  runLayout: (name: LayoutName) => void;
  highlightNeighborhood: (nodeId: string | null) => void;
}

export type LayoutName = "cose" | "breadthfirst" | "concentric" | "grid";

interface GraphCanvasProps {
  initialNodes: GraphNode[];
  initialEdges: GraphEdge[];
  onSelectNode: (nodeId: string | null) => void;
  onExpandNode: (nodeId: string) => void;
}

function toElement(node: GraphNode): ElementDefinition {
  return {
    data: {
      id: node.id,
      label: node.name,
      entityLabel: node.label,
      riskScore: node.risk_score,
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
    },
  };
}

export const GraphCanvas = forwardRef<GraphCanvasHandle, GraphCanvasProps>(
  ({ initialNodes, initialEdges, onSelectNode, onExpandNode }, ref) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const cyRef = useRef<Core | null>(null);
    const currentLayoutRef = useRef<Layouts | null>(null);

    function runLayoutInternal(cy: Core, options: cytoscape.LayoutOptions) {
      currentLayoutRef.current?.stop();
      const layout = cy.layout(options);
      currentLayoutRef.current = layout;
      layout.run();
    }

    useEffect(() => {
      if (!containerRef.current) return;

      const cy = cytoscape({
        container: containerRef.current,
        elements: [...initialNodes.map(toElement), ...initialEdges.map(toEdgeElement)],
        style: buildGraphStylesheet(),
        minZoom: 0.15,
        maxZoom: 3,
        wheelSensitivity: 0.25,
      });
      runLayoutInternal(cy, { name: "cose", animate: true, randomize: true, fit: true, padding: 40 });

      cy.on("tap", "node", (evt) => {
        onSelectNode(evt.target.id());
      });
      cy.on("tap", (evt) => {
        if (evt.target === cy) onSelectNode(null);
      });
      cy.on("dbltap", "node", (evt) => {
        onExpandNode(evt.target.id());
      });

      cyRef.current = cy;
      return () => {
        // Stop the running layout's animation-frame loop *before* destroying —
        // cose's physics simulation schedules many recursive rAF ticks, and
        // React StrictMode's dev-only mount/unmount/remount cycle otherwise lets
        // a tick fire after destroy, throwing from cytoscape's now-null internals.
        currentLayoutRef.current?.stop();
        cy.stop();
        cy.destroy();
        cyRef.current = null;
      };
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useImperativeHandle(ref, () => ({
      addElements(nodes, edges) {
        const cy = cyRef.current;
        if (!cy) return;
        const newNodes = nodes.filter((n) => cy.getElementById(n.id).empty()).map(toElement);
        const newEdges = edges.filter((e) => cy.getElementById(e.id).empty()).map(toEdgeElement);
        if (newNodes.length === 0 && newEdges.length === 0) return;
        cy.add([...newNodes, ...newEdges]);
        runLayoutInternal(cy, { name: "cose", animate: true, randomize: false, fit: false });
      },
      fit() {
        cyRef.current?.fit(undefined, 40);
      },
      runLayout(name) {
        const cy = cyRef.current;
        if (!cy) return;
        const options = name === "breadthfirst" ? { name, directed: true, spacingFactor: 1.4 } : { name };
        runLayoutInternal(cy, { ...options, animate: true, fit: true, padding: 40 } as cytoscape.LayoutOptions);
      },
      highlightNeighborhood(nodeId) {
        const cy = cyRef.current;
        if (!cy) return;
        cy.elements().removeClass("faded highlighted");
        if (!nodeId) return;
        const node = cy.getElementById(nodeId);
        const neighborhood = node.closedNeighborhood();
        cy.elements().difference(neighborhood).addClass("faded");
        neighborhood.addClass("highlighted");
      },
    }));

    return <div ref={containerRef} style={{ width: "100%", height: "100%" }} />;
  },
);

GraphCanvas.displayName = "GraphCanvas";
