"use client";

import { AxisBottom } from "@visx/axis";
import { Group } from "@visx/group";
import { ParentSize } from "@visx/responsive";
import { scaleBand, scaleTime } from "@visx/scale";
import { defaultStyles, useTooltip, TooltipWithBounds } from "@visx/tooltip";
import Link from "next/link";
import { useMemo, useRef } from "react";
import type { TimelineDetail } from "./timelineModel";
import { ENTITY_COLORS, RISK_COLOR_UNKNOWN, RISK_COLORS } from "@/lib/theme";

interface Point {
  id: string;
  lane: string;
  timestamp: Date;
  source_reported: boolean;
  color: string;
  label: string;
  detail: string;
}

const LANES = ["Incidents", "Transactions", "Communications", "Events"];
const MARGIN = { top: 20, right: 24, bottom: 40, left: 110 };

const SEVERITY_COLOR: Record<string, string> = RISK_COLORS;

function buildPoints(data: TimelineDetail): Point[] {
  const points: Point[] = [];

  for (const t of data.transactions) {
    points.push({
      id: t.id,
      lane: "Transactions",
      timestamp: new Date(t.timestamp),
      source_reported: t.source_reported,
      color: t.source_reported ? RISK_COLORS.Critical : ENTITY_COLORS.Account,
      label: t.id,
      detail: `${t.subtype} · ₹${t.amount.toLocaleString("en-IN")}`,
    });
  }
  for (const c of data.communications) {
    points.push({
      id: c.id,
      lane: "Communications",
      timestamp: new Date(c.timestamp),
      source_reported: c.source_reported,
      color: c.source_reported ? RISK_COLORS.Critical : ENTITY_COLORS.Device,
      label: c.id,
      detail: `${c.subtype} · ${c.duration_seconds}s`,
    });
  }
  for (const e of data.events) {
    points.push({
      id: e.id,
      lane: "Events",
      timestamp: new Date(e.timestamp),
      source_reported: false,
      color: ENTITY_COLORS.Event,
      label: e.id,
      detail: e.subtype,
    });
  }
  for (const i of data.incidents) {
    points.push({
      id: i.id,
      lane: "Incidents",
      timestamp: new Date(i.timestamp),
      source_reported: true,
      color: SEVERITY_COLOR[i.severity] ?? RISK_COLOR_UNKNOWN,
      label: i.id,
      detail: `${i.subtype} (${i.severity}) — ${i.description}`,
    });
  }

  return points;
}

export function TimelineChart({ data }: { data: TimelineDetail }) {
  return (
    <div style={{ width: "100%", height: 420 }}>
      <ParentSize>{({ width, height }) => <TimelineChartInner data={data} width={width} height={height} />}</ParentSize>
    </div>
  );
}

function TimelineChartInner({ data, width, height }: { data: TimelineDetail; width: number; height: number }) {
  const points = useMemo(() => buildPoints(data), [data]);
  // Draw baseline first so flagged records are never occluded by an ordinary
  // one that happens to come later in the payload.
  const orderedPoints = useMemo(
    () => [...points].sort((a, b) => Number(a.source_reported) - Number(b.source_reported)),
    [points],
  );
  const { tooltipData, tooltipLeft, tooltipTop, showTooltip, hideTooltip } = useTooltip<Point>();
  // Incident tooltips contain a real link (View in Alerts); a bare onMouseLeave
  // hides the tooltip the instant the cursor leaves the 3px circle, which fires
  // before the mouse reaches the tooltip itself and makes the link unclickable.
  // Debouncing the hide — and cancelling it if the tooltip itself is entered —
  // gives the cursor time to travel there, same pattern as any hoverable tooltip.
  const hideTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  function scheduleHide() {
    hideTimeoutRef.current = setTimeout(hideTooltip, 200);
  }
  function cancelHide() {
    clearTimeout(hideTimeoutRef.current);
  }

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
          {orderedPoints.map((p) => (
            <circle
              key={p.id}
              cx={xScale(p.timestamp)}
              cy={(yScale(p.lane) ?? 0) + yScale.bandwidth() / 2}
              r={p.source_reported ? 4.5 : 1.6}
              fill={p.color}
              opacity={p.source_reported ? 0.95 : 0.3}
              onMouseEnter={() => {
                cancelHide();
                showTooltip({
                  tooltipData: p,
                  tooltipLeft: xScale(p.timestamp) + MARGIN.left,
                  tooltipTop: (yScale(p.lane) ?? 0) + MARGIN.top,
                });
              }}
              onMouseLeave={scheduleHide}
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
          onMouseEnter={cancelHide}
          onMouseLeave={scheduleHide}
          style={{
            ...defaultStyles,
            background: "var(--surface-overlay)",
            border: "1px solid var(--surface-border)",
            color: "var(--text-primary)",
            fontSize: 12,
            padding: "8px 10px",
            pointerEvents: "auto",
          }}
        >
          <strong>{tooltipData.label}</strong>
          <div>{tooltipData.detail}</div>
          {tooltipData.lane === "Incidents" ? (
            <Link href="/alerts" style={{ color: "var(--accent-primary)", fontSize: 11 }}>
              View in Alerts →
            </Link>
          ) : null}
        </TooltipWithBounds>
      ) : null}
    </div>
  );
}
