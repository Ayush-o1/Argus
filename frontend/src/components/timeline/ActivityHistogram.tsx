"use client";

import { ParentSize } from "@visx/responsive";
import { scaleLinear, scaleTime } from "@visx/scale";
import { AxisBottom } from "@visx/axis";
import { Group } from "@visx/group";
import { useMemo } from "react";
import { RISK_COLORS } from "@/lib/theme";
import type { DayBucket } from "./timelineModel";
import styles from "./ActivityHistogram.module.css";

/**
 * Daily volume with flagged activity stacked in front of the baseline.
 *
 * This is the "what changed" view the page was missing: a scatter of individual
 * records shows that activity exists, but volume-over-time is what makes a
 * burst visible at a glance. Days flagged as bursts get an explicit marker
 * rather than relying on the reader to eyeball a tall bar.
 */

const MARGIN = { top: 10, right: 12, bottom: 26, left: 40 };
const BASELINE_COLOR = "#3A4152";

interface ActivityHistogramProps {
  buckets: DayBucket[];
  selectedDay: string | null;
  onSelectDay: (day: string | null) => void;
}

export function ActivityHistogram(props: ActivityHistogramProps) {
  return (
    <div className={styles.wrap}>
      <ParentSize>{({ width }) => <Inner {...props} width={width} height={148} />}</ParentSize>
    </div>
  );
}

function Inner({
  buckets,
  selectedDay,
  onSelectDay,
  width,
  height,
}: ActivityHistogramProps & { width: number; height: number }) {
  const innerWidth = Math.max(width - MARGIN.left - MARGIN.right, 10);
  const innerHeight = Math.max(height - MARGIN.top - MARGIN.bottom, 10);

  const xScale = useMemo(() => {
    const times = buckets.map((b) => b.date.getTime());
    const domain: [Date, Date] = times.length
      ? [new Date(Math.min(...times)), new Date(Math.max(...times))]
      : [new Date(), new Date()];
    return scaleTime({ domain, range: [0, innerWidth] });
  }, [buckets, innerWidth]);

  const yScale = useMemo(
    () =>
      scaleLinear({
        domain: [0, Math.max(1, ...buckets.map((b) => b.total))],
        range: [innerHeight, 0],
        nice: true,
      }),
    [buckets, innerHeight],
  );

  // One bar per day, minus a hairline gap. Bars narrower than a pixel render as
  // gaps, so the width is floored.
  const barWidth = Math.max(1.5, innerWidth / Math.max(buckets.length, 1) - 1);

  if (!buckets.length) return <div className={styles.empty}>No activity in this range.</div>;

  return (
    <svg width={width} height={height} role="img" aria-label="Daily activity volume">
      <Group left={MARGIN.left} top={MARGIN.top}>
        {buckets.map((b) => {
          const x = xScale(b.date) - barWidth / 2;
          const totalY = yScale(b.total);
          const flaggedY = yScale(b.flagged);
          const isSelected = selectedDay === b.day;
          return (
            <g
              key={b.day}
              className={styles.bar}
              onClick={() => onSelectDay(isSelected ? null : b.day)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelectDay(isSelected ? null : b.day);
                }
              }}
              aria-label={`${b.day}: ${b.total} records, ${b.flagged} flagged${b.burst ? ", burst" : ""}`}
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
              {b.flagged > 0 ? (
                <rect
                  x={x}
                  y={flaggedY}
                  width={barWidth}
                  height={Math.max(0, innerHeight - flaggedY)}
                  fill={b.burst ? RISK_COLORS.Critical : RISK_COLORS.High}
                  opacity={isSelected || !selectedDay ? 1 : 0.35}
                  rx={1}
                />
              ) : null}
              {b.burst ? <circle cx={x + barWidth / 2} cy={-4} r={2.5} fill={RISK_COLORS.Critical} /> : null}
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
      </Group>
    </svg>
  );
}
