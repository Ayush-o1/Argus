import { MapPin, Route } from "lucide-react";
import { EntitySearchBox } from "@/components/entity/EntitySearchBox";
import { cn } from "@/lib/cn";
import { RISK_COLORS } from "@/lib/theme";
import type { GraphNode } from "@/lib/types";
import styles from "./MapControls.module.css";

export type EntityTypeFilter = "all" | "Person" | "Organization";
export type RouteFilter = "anomalies" | "all";

const RISK_FILTERS = [
  { value: 0, label: "All risk levels" },
  { value: 35, label: "Medium and above" },
  { value: 60, label: "High and above" },
  { value: 80, label: "Critical only" },
];

interface MapControlsProps {
  entityType: EntityTypeFilter;
  onEntityTypeChange: (value: EntityTypeFilter) => void;
  riskFilter: number;
  onRiskFilterChange: (value: number) => void;
  routeFilter: RouteFilter;
  onRouteFilterChange: (value: RouteFilter) => void;
  showEntities: boolean;
  showShipments: boolean;
  onToggleEntities: () => void;
  onToggleShipments: () => void;
  onSearchSelect: (node: GraphNode) => void;
  clusteredView: boolean;
}

export function MapControls({
  entityType,
  onEntityTypeChange,
  riskFilter,
  onRiskFilterChange,
  routeFilter,
  onRouteFilterChange,
  showEntities,
  showShipments,
  onToggleEntities,
  onToggleShipments,
  onSearchSelect,
  clusteredView,
}: MapControlsProps) {
  return (
    <div className={styles.bar}>
      <EntitySearchBox onSelect={onSearchSelect} placeholder="Find an entity…" />

      <select className={styles.select} value={entityType} onChange={(e) => onEntityTypeChange(e.target.value as EntityTypeFilter)}>
        <option value="all">All entity types</option>
        <option value="Person">Persons</option>
        <option value="Organization">Organizations</option>
      </select>

      <select className={styles.select} value={riskFilter} onChange={(e) => onRiskFilterChange(Number(e.target.value))}>
        {RISK_FILTERS.map((f) => (
          <option key={f.value} value={f.value}>
            {f.label}
          </option>
        ))}
      </select>

      <select className={styles.select} value={routeFilter} onChange={(e) => onRouteFilterChange(e.target.value as RouteFilter)}>
        <option value="anomalies">Anomalous routes only</option>
        <option value="all">All shipment routes</option>
      </select>

      <button type="button" className={cn(styles.iconButton, showEntities && styles.iconButtonActive)} onClick={onToggleEntities}>
        <MapPin size={14} /> Entities
      </button>
      <button type="button" className={cn(styles.iconButton, showShipments && styles.iconButtonActive)} onClick={onToggleShipments}>
        <Route size={14} /> Routes
      </button>

      <div className={styles.spacer} />
      {clusteredView ? <span className={styles.countBadge}>Clustered view · zoom in for detail</span> : null}
    </div>
  );
}

const LEGEND_ITEMS = [
  { label: "Standard entity", color: "#3D7BFF" },
  { label: "Organization", color: "#A855F7" },
  { label: "High risk", color: RISK_COLORS.High },
  { label: "Critical risk", color: RISK_COLORS.Critical },
  { label: "Anomalous route", color: RISK_COLORS.Critical },
];

export function MapLegend() {
  return (
    <div className={styles.legend}>
      {LEGEND_ITEMS.map((item) => (
        <span key={item.label} className={styles.legendItem}>
          <span className={styles.dot} style={{ background: item.color }} />
          {item.label}
        </span>
      ))}
    </div>
  );
}
