import { cn } from "@/lib/cn";
import styles from "./SegmentedControl.module.css";

export interface Segment<T extends string> {
  value: T;
  label: string;
  count?: number;
}

interface SegmentedControlProps<T extends string> {
  segments: Segment<T>[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
  ariaLabel?: string;
}

/** Mutually-exclusive filter switch. Used where the app previously stacked two
 * competing underline tab-rows on one screen, which left it ambiguous which
 * row was scoping which axis of the list. */
export function SegmentedControl<T extends string>({
  segments,
  value,
  onChange,
  className,
  ariaLabel,
}: SegmentedControlProps<T>) {
  return (
    <div className={cn(styles.group, className)} role="tablist" aria-label={ariaLabel}>
      {segments.map((s) => {
        const active = s.value === value;
        return (
          <button
            key={s.value}
            type="button"
            role="tab"
            aria-selected={active}
            className={cn(styles.item, active && styles.itemActive)}
            onClick={() => onChange(s.value)}
          >
            {s.label}
            {s.count !== undefined ? <span className={styles.count}>{s.count}</span> : null}
          </button>
        );
      })}
    </div>
  );
}
