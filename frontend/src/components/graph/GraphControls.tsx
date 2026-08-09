import { Maximize2, RotateCcw, Waypoints } from "lucide-react";
import { cn } from "@/lib/cn";
import { ENTITY_COLORS } from "@/lib/theme";
import type { LayoutName } from "./GraphCanvas";
import styles from "./GraphControls.module.css";

const LAYOUTS: { value: LayoutName; label: string }[] = [
  { value: "cose", label: "Force-directed" },
  { value: "breadthfirst", label: "Hierarchical" },
  { value: "concentric", label: "Radial" },
  { value: "grid", label: "Grid" },
];

interface GraphControlsProps {
  layout: LayoutName;
  onLayoutChange: (layout: LayoutName) => void;
  onFit: () => void;
  nodeCount: number;
  edgeCount: number;
  pathMode: boolean;
  onTogglePathMode: () => void;
  pathModeHint?: string;
  /** Shown only when viewing a seeded subgraph (e.g. arrived via ?seed=), so
   * there's always a way back to the full overview without editing the URL. */
  onResetView?: () => void;
}

export function GraphControls({
  layout,
  onLayoutChange,
  onFit,
  nodeCount,
  edgeCount,
  pathMode,
  onTogglePathMode,
  pathModeHint,
  onResetView,
}: GraphControlsProps) {
  return (
    <div className={styles.bar}>
      <select className={styles.select} value={layout} onChange={(e) => onLayoutChange(e.target.value as LayoutName)}>
        {LAYOUTS.map((l) => (
          <option key={l.value} value={l.value}>
            {l.label}
          </option>
        ))}
      </select>
      <button type="button" className={styles.iconButton} onClick={onFit} title="Fit to screen">
        <Maximize2 size={15} />
      </button>
      <button
        type="button"
        className={cn(styles.iconButton, pathMode && styles.iconButtonActive)}
        onClick={onTogglePathMode}
        title="Find shortest path between two entities"
      >
        <Waypoints size={15} />
      </button>
      {onResetView ? (
        <button type="button" className={styles.iconButton} onClick={onResetView} title="Back to full overview">
          <RotateCcw size={15} />
        </button>
      ) : null}
      {pathMode && <span className={styles.countBadge}>{pathModeHint ?? "Click a start entity"}</span>}
      <div className={styles.spacer} />
      <span className={styles.countBadge}>
        {nodeCount} nodes · {edgeCount} edges
      </span>
    </div>
  );
}

const LEGEND_ITEMS = (["Person", "Organization", "Account", "Device", "Location", "Event", "Document"] as const).map(
  (label) => ({ label, color: ENTITY_COLORS[label] }),
);

interface GraphLegendProps {
  hiddenTypes: string[];
  onToggleType: (label: string) => void;
}

/** Doubles as a complexity-management control: click a type to hide/show it
 * on the canvas, rather than always rendering every node the graph returns. */
export function GraphLegend({ hiddenTypes, onToggleType }: GraphLegendProps) {
  return (
    <div className={styles.legend}>
      {LEGEND_ITEMS.map((item) => {
        const hidden = hiddenTypes.includes(item.label);
        return (
          <button
            key={item.label}
            type="button"
            className={cn(styles.legendItem, hidden && styles.legendItemHidden)}
            onClick={() => onToggleType(item.label)}
            title={hidden ? `Show ${item.label} nodes` : `Hide ${item.label} nodes`}
            aria-pressed={!hidden}
          >
            <span className={styles.legendDot} style={{ background: item.color }} />
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
