"use client";

import { motion } from "framer-motion";
import { ENTITY_COLORS, RISK_COLORS } from "@/lib/theme";

interface MotifNode {
  id: string;
  x: number;
  y: number;
  r: number;
  color: string;
  risk?: boolean;
}

interface MotifEdge {
  from: string;
  to: string;
}

const NODES: MotifNode[] = [
  { id: "hub", x: 300, y: 240, r: 15, color: RISK_COLORS.Critical, risk: true },
  { id: "p1", x: 168, y: 150, r: 8, color: ENTITY_COLORS.Person },
  { id: "p2", x: 130, y: 270, r: 6, color: ENTITY_COLORS.Person },
  { id: "p3", x: 210, y: 360, r: 7, color: ENTITY_COLORS.Person },
  { id: "o1", x: 420, y: 130, r: 10, color: ENTITY_COLORS.Organization },
  { id: "o2", x: 452, y: 300, r: 9, color: ENTITY_COLORS.Organization },
  { id: "a1", x: 330, y: 90, r: 5, color: ENTITY_COLORS.Account },
  { id: "a2", x: 500, y: 210, r: 5, color: ENTITY_COLORS.Account },
  { id: "l1", x: 370, y: 400, r: 6, color: ENTITY_COLORS.Location },
  { id: "d1", x: 80, y: 190, r: 5, color: ENTITY_COLORS.Device },
  { id: "e1", x: 260, y: 460, r: 5, color: ENTITY_COLORS.Event },
  { id: "o3", x: 540, y: 380, r: 6, color: ENTITY_COLORS.Organization },
];

const EDGES: MotifEdge[] = [
  { from: "hub", to: "p1" },
  { from: "hub", to: "p2" },
  { from: "hub", to: "p3" },
  { from: "hub", to: "o1" },
  { from: "hub", to: "o2" },
  { from: "p1", to: "a1" },
  { from: "p1", to: "d1" },
  { from: "o1", to: "a1" },
  { from: "o2", to: "a2" },
  { from: "o2", to: "o3" },
  { from: "p3", to: "l1" },
  { from: "p3", to: "e1" },
  { from: "p2", to: "d1" },
];

function nodeById(id: string) {
  return NODES.find((n) => n.id === id)!;
}

/** Hand-composed constellation used as the hero/spotlight motif — not a live
 * graph render. A real Cytoscape instance is too heavy to mount decoratively
 * and would visually contradict the redesigned Graph Explorer's restraint. */
export function GraphMotif({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 600 520" className={className} role="presentation" aria-hidden="true">
      <defs>
        <radialGradient id="motif-hub-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor={RISK_COLORS.Critical} stopOpacity="0.45" />
          <stop offset="100%" stopColor={RISK_COLORS.Critical} stopOpacity="0" />
        </radialGradient>
      </defs>

      {EDGES.map((edge, i) => {
        const from = nodeById(edge.from);
        const to = nodeById(edge.to);
        return (
          <motion.line
            key={`${edge.from}-${edge.to}`}
            x1={from.x}
            y1={from.y}
            x2={to.x}
            y2={to.y}
            stroke="var(--surface-border)"
            strokeWidth={1}
            initial={{ pathLength: 0, opacity: 0 }}
            animate={{ pathLength: 1, opacity: 0.8 }}
            transition={{ duration: 0.9, delay: 0.15 + i * 0.045, ease: [0.16, 1, 0.3, 1] }}
          />
        );
      })}

      <circle cx={NODES[0].x} cy={NODES[0].y} r={64} fill="url(#motif-hub-glow)" />

      {NODES.map((node, i) => (
        <motion.circle
          key={node.id}
          cx={node.x}
          cy={node.y}
          r={node.r}
          fill={node.color}
          stroke="var(--surface-base)"
          strokeWidth={2}
          initial={{ opacity: 0, scale: 0.4 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, delay: 0.5 + i * 0.05, ease: [0.34, 1.56, 0.64, 1] }}
        />
      ))}

      <motion.circle
        cx={NODES[0].x}
        cy={NODES[0].y}
        r={NODES[0].r + 6}
        fill="none"
        stroke={RISK_COLORS.Critical}
        strokeWidth={1.5}
        initial={{ opacity: 0 }}
        animate={{ opacity: [0, 0.6, 0] }}
        transition={{ duration: 2.4, delay: 1.4, repeat: Infinity, ease: "easeInOut" }}
      />
    </svg>
  );
}
