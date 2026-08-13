import type { InputHTMLAttributes } from "react";
import { cn } from "@/lib/cn";
import { RISK_COLORS } from "@/lib/theme";
import styles from "./RangeSlider.module.css";

interface RangeSliderProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "value"> {
  label: string;
  value: number;
  min?: number;
  max?: number;
  /** Rendered next to the label, e.g. "60+" or "All". */
  valueLabel?: string;
  ticks?: string[];
  /** Paints the filled portion with the risk ramp, so the control itself
   * communicates what the threshold means rather than being a neutral bar. */
  riskRamp?: boolean;
}

export function RangeSlider({
  label,
  value,
  min = 0,
  max = 100,
  valueLabel,
  ticks,
  riskRamp,
  className,
  ...props
}: RangeSliderProps) {
  const pct = ((value - min) / (max - min)) * 100;
  const fill = riskRamp
    ? `linear-gradient(90deg, ${RISK_COLORS.Low} 0%, ${RISK_COLORS.Medium} 35%, ${RISK_COLORS.High} 60%, ${RISK_COLORS.Critical} 80%)`
    : "var(--accent-primary)";
  const track = `linear-gradient(90deg, transparent 0 ${pct}%, var(--surface-border) ${pct}% 100%), ${fill}`;

  return (
    <div className={cn(styles.wrap, className)}>
      <div className={styles.head}>
        <span className={styles.label}>{label}</span>
        <span className={styles.value}>{valueLabel ?? value}</span>
      </div>
      <input
        type="range"
        className={styles.input}
        min={min}
        max={max}
        value={value}
        style={{ ["--track" as string]: track }}
        aria-label={label}
        {...props}
      />
      {ticks ? (
        <div className={styles.ticks}>
          {ticks.map((t) => (
            <span key={t}>{t}</span>
          ))}
        </div>
      ) : null}
    </div>
  );
}
