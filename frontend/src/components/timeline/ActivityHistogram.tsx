"use client";

import { ParentSize } from "@visx/responsive";
import { scaleLinear, scaleTime } from "@visx/scale";
import { AxisBottom } from "@visx/axis";
import { Group } from "@visx/group";
import { useMemo, useRef, useState } from "react";
import { RISK_COLORS } from "@/lib/theme";
import type { AnalysedDay } from "./timelineModel";
import styles from "./ActivityHistogram.module.css";

/**
 * Daily volume with flagged activity stacked in front of the baseline.
 *
 * This is the "what changed" view the page was missing: a scatter of individual
 * records shows that activity exists, but volume-over-time is what makes a
 * unusual visible at a glance. Days flagged as bursts get an explicit marker
 * rather than relying on the reader to eyeball a tall bar.
 *
 * Drag horizontally to zoom into the days under the selection — deferred at
 * Phase 5 on the reasoning that a 180-day window renders fully at a legible
 * density without it. That is a statement about density, not about whether an
 * analyst ever wants to isolate three days out of ninety without hand-picking
 * a day count from a fixed list, which is what this adds: a plain drag
 * gesture on the chart itself, not a new control competing for space with the
 * range buttons that already exist. A single click still selects one day —
 * distinguished by whether the pointer actually moved between down and up,
 * not by which element it landed on.
 */

const MARGIN = { top: 10, right: 12, bottom: 26, left: 40 };
const BASELINE_COLOR = "#3A4152";
const DRAG_THRESHOLD_PX = 4;

interface ActivityHistogramProps {
  days: AnalysedDay[];
  selectedDay: string | null;
  onSelectDay: (day: string | null) => void;
  /** A drag gesture across the chart selected this [start, end] span (epoch
   * ms). Optional so a caller that has no use for zooming can render the
   * chart without a zoom affordance at all. */
  onZoom?: (range: { start: number; end: number }) => void;
}

export function ActivityHistogram(props: ActivityHistogramProps) {
  return (
    <div className={styles.wrap}>
      <ParentSize>{({ width }) => <Inner {...props} width={width} height={148} />}</ParentSize>
    </div>
  );
}

function Inner({
  days,
  selectedDay,
  onSelectDay,
  onZoom,
  width,
  height,
}: ActivityHistogramProps & { width: number; height: number }) {
  const innerWidth = Math.max(width - MARGIN.left - MARGIN.right, 10);
  const innerHeight = Math.max(height - MARGIN.top - MARGIN.bottom, 10);

  const xScale = useMemo(() => {
    const times = days.map((b) => b.date.getTime());
    const domain: [Date, Date] = times.length
      ? [new Date(Math.min(...times)), new Date(Math.max(...times))]
      : [new Date(), new Date()];
    return scaleTime({ domain, range: [0, innerWidth] });
  }, [days, innerWidth]);

  const yScale = useMemo(
    () =>
      scaleLinear({
        domain: [0, Math.max(1, ...days.map((b) => b.total))],
        range: [innerHeight, 0],
        nice: true,
      }),
    [days, innerHeight],
  );

  // One bar per day, minus a hairline gap. Bars narrower than a pixel render as
  // gaps, so the width is floored.
  const barWidth = Math.max(1.5, innerWidth / Math.max(days.length, 1) - 1);

  // Drag state lives in refs, not state, for the same reason GraphCanvas's
  // pointer handlers do: a value read inside the pointer handlers that fired
  // on *this* gesture, not one captured by a stale render closure. `dragBox`
  // is the one piece that needs to trigger a re-render — it's what's drawn.
  const dragStartRef = useRef<number | null>(null);
  const draggedRef = useRef(false);
  const [dragBox, setDragBox] = useState<[number, number] | null>(null);

  function toInnerX(clientX: number, rect: DOMRect): number {
    return clientX - rect.left - MARGIN.left;
  }

  function handlePointerDown(e: React.PointerEvent<SVGSVGElement>) {
    if (!onZoom) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    dragStartRef.current = toInnerX(e.clientX, e.currentTarget.getBoundingClientRect());
    draggedRef.current = false;
  }

  function handlePointerMove(e: React.PointerEvent<SVGSVGElement>) {
    if (dragStartRef.current === null) return;
    const x = toInnerX(e.clientX, e.currentTarget.getBoundingClientRect());
    if (!draggedRef.current && Math.abs(x - dragStartRef.current) < DRAG_THRESHOLD_PX) return;
    draggedRef.current = true;
    setDragBox([Math.min(dragStartRef.current, x), Math.max(dragStartRef.current, x)]);
  }

  function handlePointerUp(e: React.PointerEvent<SVGSVGElement>) {
    e.currentTarget.releasePointerCapture(e.pointerId);
    if (draggedRef.current && dragBox && onZoom) {
      const [x0, x1] = dragBox;
      const start = xScale.invert(Math.max(0, x0)).getTime();
      // End-of-day: a drag that ends mid-bar on day D should still include
      // all of D, not cut it off at midnight.
      const end = xScale.invert(Math.min(innerWidth, x1)).getTime() + 86_400_000 - 1;
      onZoom({ start, end });
    }
    dragStartRef.current = null;
    setDragBox(null);
    // draggedRef.current is left true through the `click` event this pointerup
    // is about to produce — cleared on the next pointerdown — so the bar
    // underneath doesn't also register this gesture as a day selection.
  }

  if (!days.length) return <div className={styles.empty}>No activity in this range.</div>;

  return (
    <svg
      width={width}
      height={height}
      role="img"
      aria-label="Daily activity volume — drag to zoom into a span of days"
      style={{ cursor: onZoom ? "crosshair" : undefined, touchAction: onZoom ? "none" : undefined }}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
    >
      <Group left={MARGIN.left} top={MARGIN.top}>
        {days.map((b) => {
          const x = xScale(b.date) - barWidth / 2;
          const totalY = yScale(b.total);
          const flaggedY = yScale(b.sourceReported);
          const isSelected = selectedDay === b.day;
          return (
            <g
              key={b.day}
              className={styles.bar}
              onClick={() => {
                // This click is the tail end of a drag-to-zoom gesture that
                // just fired onZoom, not an attempt to select this one day.
                if (draggedRef.current) {
                  draggedRef.current = false;
                  return;
                }
                onSelectDay(isSelected ? null : b.day);
              }}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelectDay(isSelected ? null : b.day);
                }
              }}
              aria-label={`${b.day}: ${b.total} records, ${b.sourceReported} flagged${b.unusual ? ", unusual" : ""}`}
            >
              {/* Full-height hit area — a 2px bar is far too small a target. */}
              <rect x={x - 1} y={0} width={barWidth + 2} height={innerHeight} fill="transparent" />
              <rect
                x={x}
                y={totalY}
                width={barWidth}
                height={Math.max(0, innerHeight - totalY)}
                fill={BASELINE_COLOR}
                opacity={isSelected || !selectedDay ? 1 : 0.35}
                rx={1}
              />
              {b.sourceReported > 0 ? (
                <rect
                  x={x}
                  y={flaggedY}
                  width={barWidth}
                  height={Math.max(0, innerHeight - flaggedY)}
                  fill={b.unusual ? RISK_COLORS.Critical : RISK_COLORS.High}
                  opacity={isSelected || !selectedDay ? 1 : 0.35}
                  rx={1}
                />
              ) : null}
              {b.unusual ? <circle cx={x + barWidth / 2} cy={-4} r={2.5} fill={RISK_COLORS.Critical} /> : null}
              {isSelected ? (
                <rect x={x - 1} y={0} width={barWidth + 2} height={innerHeight} className={styles.selection} rx={2} />
              ) : null}
            </g>
          );
        })}
        <AxisBottom
          top={innerHeight}
          scale={xScale}
          numTicks={6}
          stroke="var(--surface-border)"
          tickStroke="var(--surface-border)"
          tickLabelProps={() => ({
            fill: "var(--text-tertiary)",
            fontSize: 10,
            textAnchor: "middle",
            fontFamily: "var(--font-mono)",
          })}
        />
        {dragBox ? (
          <rect
            x={dragBox[0]}
            y={0}
            width={dragBox[1] - dragBox[0]}
            height={innerHeight}
            fill="rgba(61, 123, 255, 0.16)"
            stroke="var(--accent-primary, #3d7bff)"
            strokeWidth={1}
            pointerEvents="none"
          />
        ) : null}
      </Group>
    </svg>
  );
}
