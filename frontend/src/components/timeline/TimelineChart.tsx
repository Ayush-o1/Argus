"use client";

import { AxisBottom } from "@visx/axis";
import { Group } from "@visx/group";
import { ParentSize } from "@visx/responsive";
import { scaleBand, scaleTime } from "@visx/scale";
import { defaultStyles, useTooltip, TooltipWithBounds } from "@visx/tooltip";
import { useMemo } from "react";
import type { GlobalTimeline } from "@/hooks/useTimeline";

interface Point {
  id: string;
  lane: string;
  timestamp: Date;
  flagged: boolean;
  color: string;
  label: string;
  detail: string;
}

const LANES = ["Incidents", "Transactions", "Communications", "Events"];
const MARGIN = { top: 20, right: 24, bottom: 40, left: 110 };

const SEVERITY_COLOR: Record<string, string> = {
  Critical: "#FF3B47",
  High: "#FF7D1A",
  Medium: "#FFB800",
  Low: "#1AE87B",
};

function buildPoints(data: GlobalTimeline): Point[] {
  const points: Point[] = [];

  for (const t of data.transactions) {
    points.push({
      id: t.id,
      lane: "Transactions",
      timestamp: new Date(t.timestamp),
      flagged: t.flagged,
      color: t.flagged ? "#FF3B47" : "#F97316",
      label: t.id,
      detail: `${t.subtype} · ₹${t.amount.toLocaleString("en-IN")}`,
    });
  }
  for (const c of data.communications) {
    points.push({
      id: c.id,
      lane: "Communications",
      timestamp: new Date(c.timestamp),
      flagged: c.flagged,
      color: c.flagged ? "#FF3B47" : "#06B6D4",
      label: c.id,
      detail: `${c.subtype} · ${c.duration_seconds}s`,
    });
  }
  for (const e of data.events) {
    points.push({
      id: e.id,
      lane: "Events",
      timestamp: new Date(e.timestamp),
      flagged: false,
      color: "#EC4899",
      label: e.id,
      detail: e.subtype,
    });
  }
  for (const i of data.incidents) {
    points.push({
      id: i.id,
      lane: "Incidents",
      timestamp: new Date(i.timestamp),
      flagged: true,
      color: SEVERITY_COLOR[i.severity] ?? "#8892A4",
      label: i.id,
      detail: `${i.subtype} (${i.severity}) — ${i.description}`,
    });
  }

  return points;
}

export function TimelineChart({ data }: { data: GlobalTimeline }) {
  return (
    <div style={{ width: "100%", height: 420 }}>
      <ParentSize>{({ width, height }) => <TimelineChartInner data={data} width={width} height={height} />}</ParentSize>
    </div>
  );
}

function TimelineChartInner({ data, width, height }: { data: GlobalTimeline; width: number; height: number }) {
  const points = useMemo(() => buildPoints(data), [data]);
  const { tooltipData, tooltipLeft, tooltipTop, showTooltip, hideTooltip } = useTooltip<Point>();

  const innerWidth = Math.max(width - MARGIN.left - MARGIN.right, 10);
  const innerHeight = Math.max(height - MARGIN.top - MARGIN.bottom, 10);

  const timeExtent = useMemo(() => {
    if (points.length === 0) return [new Date(), new Date()] as [Date, Date];
    const timestamps = points.map((p) => p.timestamp.getTime());
    return [new Date(Math.min(...timestamps)), new Date(Math.max(...timestamps))] as [Date, Date];
  }, [points]);

  const xScale = useMemo(
    () => scaleTime({ domain: timeExtent, range: [0, innerWidth] }),
    [timeExtent, innerWidth],
  );
  const yScale = useMemo(
    () => scaleBand({ domain: LANES, range: [0, innerHeight], padding: 0.5 }),
    [innerHeight],
  );

  if (points.length === 0) {
    return null;
  }

  return (
    <div style={{ position: "relative" }}>
      <svg width={width} height={height}>
        <Group left={MARGIN.left} top={MARGIN.top}>
          {LANES.map((lane) => (
            <g key={lane}>
              <line
                x1={0}
                x2={innerWidth}
                y1={(yScale(lane) ?? 0) + yScale.bandwidth() / 2}
                y2={(yScale(lane) ?? 0) + yScale.bandwidth() / 2}
                stroke="var(--surface-border-faint)"
                strokeWidth={1}
              />
              <text x={-16} y={(yScale(lane) ?? 0) + yScale.bandwidth() / 2} dy=".33em" textAnchor="end" fontSize={12} fill="var(--text-secondary)">
                {lane}
              </text>
            </g>
          ))}
          {points.map((p) => (
            <circle
              key={p.id}
              cx={xScale(p.timestamp)}
              cy={(yScale(p.lane) ?? 0) + yScale.bandwidth() / 2}
              r={p.flagged ? 4.5 : 3}
              fill={p.color}
              opacity={p.flagged ? 0.95 : 0.55}
              onMouseEnter={() =>
                showTooltip({
                  tooltipData: p,
                  tooltipLeft: xScale(p.timestamp) + MARGIN.left,
                  tooltipTop: (yScale(p.lane) ?? 0) + MARGIN.top,
                })
              }
              onMouseLeave={hideTooltip}
            />
          ))}
          <AxisBottom
            top={innerHeight}
            scale={xScale}
            stroke="var(--surface-border)"
            tickStroke="var(--surface-border)"
            tickLabelProps={() => ({ fill: "var(--text-tertiary)", fontSize: 11, textAnchor: "middle" })}
          />
        </Group>
      </svg>
      {tooltipData ? (
        <TooltipWithBounds
          left={tooltipLeft}
          top={tooltipTop}
          style={{
            ...defaultStyles,
            background: "var(--surface-overlay)",
            border: "1px solid var(--surface-border)",
            color: "var(--text-primary)",
            fontSize: 12,
            padding: "8px 10px",
          }}
        >
          <strong>{tooltipData.label}</strong>
          <div>{tooltipData.detail}</div>
        </TooltipWithBounds>
      ) : null}
    </div>
  );
}
