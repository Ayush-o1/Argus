"use client";

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { Severity } from "@/lib/types";
import styles from "./RiskDonut.module.css";

const COLORS: Record<Severity, string> = {
  Critical: "#FF3B47",
  High: "#FF7D1A",
  Medium: "#FFB800",
  Low: "#1AE87B",
};

interface RiskDonutProps {
  data: { level: Severity; count: number }[];
}

export function RiskDonut({ data }: RiskDonutProps) {
  const total = data.reduce((sum, d) => sum + d.count, 0);

  return (
    <div className={styles.wrap}>
      <div style={{ width: 140, height: 140, flexShrink: 0 }}>
        <ResponsiveContainer>
          <PieChart>
            <Pie data={data} dataKey="count" nameKey="level" innerRadius={42} outerRadius={62} paddingAngle={2} stroke="none">
              {data.map((entry) => (
                <Cell key={entry.level} fill={COLORS[entry.level]} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                background: "var(--surface-overlay)",
                border: "1px solid var(--surface-border)",
                borderRadius: 8,
                fontSize: 13,
              }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className={styles.legend}>
        {data.map((entry) => (
          <div key={entry.level} className={styles.legendRow}>
            <span className={styles.dot} style={{ background: COLORS[entry.level] }} />
            <span className={styles.legendLabel}>{entry.level}</span>
            <span className={styles.legendValue}>
              {entry.count} {total > 0 ? `(${((entry.count / total) * 100).toFixed(0)}%)` : ""}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
