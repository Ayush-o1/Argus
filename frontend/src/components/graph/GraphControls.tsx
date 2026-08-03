import { Maximize2 } from "lucide-react";
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
}

export function GraphControls({ layout, onLayoutChange, onFit, nodeCount, edgeCount }: GraphControlsProps) {
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
      <div className={styles.spacer} />
      <span className={styles.countBadge}>
        {nodeCount} nodes · {edgeCount} edges
      </span>
    </div>
  );
}

const LEGEND_ITEMS = [
  { label: "Person", color: "#3D7BFF" },
  { label: "Organization", color: "#A855F7" },
  { label: "Account", color: "#F97316" },
  { label: "Device", color: "#06B6D4" },
  { label: "Location", color: "#1AE87B" },
  { label: "Event", color: "#EC4899" },
  { label: "Document", color: "#84CC16" },
];

export function GraphLegend() {
  return (
    <div className={styles.legend}>
      {LEGEND_ITEMS.map((item) => (
        <span key={item.label} className={styles.legendItem}>
          <span className={styles.legendDot} style={{ background: item.color }} />
          {item.label}
        </span>
      ))}
    </div>
  );
}
