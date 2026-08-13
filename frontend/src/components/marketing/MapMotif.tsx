"use client";

import { motion } from "framer-motion";
import { ENTITY_COLORS, RISK_COLORS } from "@/lib/theme";

const POINTS = [
  { x: 120, y: 90, r: 4 },
  { x: 150, y: 130, r: 3 },
  { x: 95, y: 150, r: 3 },
  { x: 480, y: 100, r: 4 },
  { x: 450, y: 140, r: 3 },
  { x: 300, y: 340, r: 4 },
  { x: 340, y: 370, r: 3 },
  { x: 270, y: 390, r: 3 },
  { x: 420, y: 300, r: 3 },
];

const ROUTES = [
  { path: "M150,130 C220,60 380,60 450,140", anomaly: false },
  { path: "M95,150 C160,220 220,260 300,340", anomaly: false },
  { path: "M450,140 C420,220 350,280 340,370", anomaly: true },
  { path: "M120,90 C260,20 420,40 480,100", anomaly: false },
];

/** Abstract geospatial motif — a stylized lat/long grid with clustered
 * entities and a highlighted anomalous route. Decorative only; not a live
 * map render. */
export function MapMotif({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 560 440" className={className} role="presentation" aria-hidden="true">
      <defs>
        <pattern id="motif-grid" width="40" height="40" patternUnits="userSpaceOnUse">
          <path d="M40 0 L0 0 0 40" fill="none" stroke="var(--surface-border-faint)" strokeWidth="1" />
        </pattern>
        <radialGradient id="motif-cluster-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor={ENTITY_COLORS.Person} stopOpacity="0.18" />
          <stop offset="100%" stopColor={ENTITY_COLORS.Person} stopOpacity="0" />
        </radialGradient>
      </defs>

      <rect width="560" height="440" fill="url(#motif-grid)" />
      <circle cx={120} cy={125} r={70} fill="url(#motif-cluster-glow)" />
      <circle cx={310} cy={365} r={60} fill="url(#motif-cluster-glow)" />

      {ROUTES.map((route, i) => (
        <motion.path
          key={route.path}
          d={route.path}
          fill="none"
          stroke={route.anomaly ? RISK_COLORS.Critical : "var(--surface-border)"}
          strokeWidth={route.anomaly ? 2.25 : 1.25}
          strokeOpacity={route.anomaly ? 0.95 : 0.55}
          initial={{ pathLength: 0, opacity: 0 }}
          animate={{ pathLength: 1, opacity: route.anomaly ? 0.95 : 0.55 }}
          transition={{ duration: 1, delay: 0.2 + i * 0.15, ease: [0.16, 1, 0.3, 1] }}
        />
      ))}

      {POINTS.map((pt, i) => (
        <motion.circle
          key={`${pt.x}-${pt.y}`}
          cx={pt.x}
          cy={pt.y}
          r={pt.r}
          fill={ENTITY_COLORS.Person}
          initial={{ opacity: 0, scale: 0.4 }}
          animate={{ opacity: 0.9, scale: 1 }}
          transition={{ duration: 0.4, delay: 0.6 + i * 0.04 }}
        />
      ))}

      <motion.circle
        cx={340}
        cy={370}
        r={7}
        fill={RISK_COLORS.Critical}
        initial={{ opacity: 0, scale: 0.4 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.4, delay: 1.1 }}
      />
      <motion.circle
        cx={340}
        cy={370}
        r={7}
        fill="none"
        stroke={RISK_COLORS.Critical}
        strokeWidth={1.5}
        initial={{ opacity: 0 }}
        animate={{ opacity: [0, 0.6, 0], scale: [1, 2.2, 2.2] }}
        transition={{ duration: 2.2, delay: 1.4, repeat: Infinity, ease: "easeOut" }}
      />
    </svg>
  );
}
