"use client";

import { motion } from "framer-motion";
import { RISK_COLORS } from "@/lib/theme";

const ROWS = [
  { w: 62, score: 100, tier: "critical" as const },
  { w: 74, score: 100, tier: "critical" as const },
  { w: 55, score: 79, tier: "high" as const },
  { w: 68, score: 49, tier: "medium" as const },
  { w: 48, score: 38, tier: "medium" as const },
  { w: 71, score: 12, tier: "low" as const },
  { w: 58, score: 8, tier: "low" as const },
];

const TIER_COLOR = {
  critical: RISK_COLORS.Critical,
  high: RISK_COLORS.High,
  medium: RISK_COLORS.Medium,
  low: RISK_COLORS.Low,
};

/** Abstracted priority queue — the ranked triage list the command center
 * opens on. Decorative, but it mirrors the product's real visual grammar:
 * severity carried by a bar whose length and colour both encode risk. */
export function TriageMotif({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 460 300" className={className} role="presentation" aria-hidden="true">
      {ROWS.map((row, i) => {
        const y = 22 + i * 38;
        const color = TIER_COLOR[row.tier];
        return (
          <g key={i}>
            <motion.rect
              x={18}
              y={y}
              width={424}
              height={28}
              rx={6}
              fill="var(--surface-raised)"
              stroke="var(--surface-border-faint)"
              initial={{ opacity: 0, x: -8 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.4, delay: i * 0.07, ease: [0.16, 1, 0.3, 1] }}
            />
            <motion.rect
              x={18}
              y={y}
              width={3}
              height={28}
              fill={color}
              initial={{ opacity: 0 }}
              whileInView={{ opacity: 1 }}
              viewport={{ once: true }}
              transition={{ duration: 0.3, delay: 0.15 + i * 0.07 }}
            />
            <rect x={34} y={y + 9} width={row.w} height={5} rx={2.5} fill="var(--text-tertiary)" opacity={0.55} />
            <rect x={34 + row.w + 10} y={y + 9} width={38} height={5} rx={2.5} fill="var(--surface-border)" />
            <motion.rect
              x={352}
              y={y + 11}
              height={4}
              rx={2}
              fill={color}
              initial={{ width: 0 }}
              whileInView={{ width: Math.max(row.score * 0.6, 6) }}
              viewport={{ once: true }}
              transition={{ duration: 0.6, delay: 0.25 + i * 0.07, ease: [0.16, 1, 0.3, 1] }}
            />
          </g>
        );
      })}
    </svg>
  );
}
