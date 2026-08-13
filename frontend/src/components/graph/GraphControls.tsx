import { Crosshair, Maximize2, Network, RotateCcw, ShieldAlert, Waypoints } from "lucide-react";
import { EntitySearchBox } from "@/components/entity/EntitySearchBox";
import { SelectControl } from "@/components/ui/SelectControl";
import { cn } from "@/lib/cn";
import { ENTITY_COLORS, RISK_COLORS } from "@/lib/theme";
import type { GraphNode } from "@/lib/types";
import type { LayoutName } from "./GraphCanvas";
import styles from "./GraphControls.module.css";

const LAYOUTS: { value: LayoutName; label: string }[] = [
  { value: "fcose", label: "Force-directed" },
  { value: "breadthfirst", label: "Hierarchical" },
  { value: "concentric", label: "Radial" },
  { value: "grid", label: "Grid" },
];

const RISK_FILTERS = [
  { value: 0, label: "All risk levels" },
  { value: 35, label: "Medium and above" },
  { value: 60, label: "High and above" },
  { value: 80, label: "Critical only" },
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
  riskFilter: number;
  onRiskFilterChange: (minRisk: number) => void;
  isFocused: boolean;
  onClearFocus: () => void;
  onSearchSelect: (node: GraphNode) => void;
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
  riskFilter,
  onRiskFilterChange,
  isFocused,
  onClearFocus,
  onSearchSelect,
  onResetView,
}: GraphControlsProps) {
  return (
    <div className={styles.bar}>
      <EntitySearchBox onSelect={onSearchSelect} />

      <SelectControl
        icon={Network}
        options={LAYOUTS}
        value={layout}
        onChange={(e) => onLayoutChange(e.target.value as LayoutName)}
        aria-label="Graph layout"
      />

      <SelectControl
        icon={ShieldAlert}
        options={RISK_FILTERS}
        value={riskFilter}
        active={riskFilter > 0}
        onChange={(e) => onRiskFilterChange(Number(e.target.value))}
        aria-label="Minimum risk level"
      />

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
      {isFocused && (
        <button type="button" className={cn(styles.countBadge, styles.focusBadge)} onClick={onClearFocus}>
          <Crosshair size={12} /> Focused — click to clear
        </button>
      )}
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
const RISK_KEY = [
  { label: "Critical", color: RISK_COLORS.Critical },
  { label: "High", color: RISK_COLORS.High },
  { label: "Medium", color: RISK_COLORS.Medium },
];

export function GraphLegend({ hiddenTypes, onToggleType }: GraphLegendProps) {
  return (
    <div className={styles.legend}>
      <div className={styles.legendSection}>
        <span className={styles.legendTitle}>Entity type — click to filter</span>
        <div className={styles.legendRow}>
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
      </div>

      {/* Risk is encoded as a ring around each node, independent of the fill
          colour above. Without this key that second channel is invisible —
          an analyst has no way to know the outline means anything. */}
      <div className={styles.legendSection}>
        <span className={styles.legendTitle}>Risk ring</span>
        <div className={styles.legendRow}>
          {RISK_KEY.map((item) => (
            <span key={item.label} className={styles.legendItem}>
              <span className={styles.legendRing} style={{ borderColor: item.color }} />
              {item.label}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
