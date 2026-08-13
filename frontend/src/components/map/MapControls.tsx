import { Globe2, MapPin, Route, ShieldAlert, Shapes } from "lucide-react";
import { EntitySearchBox } from "@/components/entity/EntitySearchBox";
import { SelectControl } from "@/components/ui/SelectControl";
import { cn } from "@/lib/cn";
import { RISK_COLORS } from "@/lib/theme";
import type { MapScale } from "@/components/map/ArgusMap";
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
  scale: MapScale;
  onResetView: () => void;
}

/** What each zoom tier is actually showing, stated rather than left to be inferred. */
const SCALE_COPY: Record<MapScale, { label: string; hint: string }> = {
  world: { label: "World", hint: "Regions and trade corridors — click a region to drill in" },
  regional: { label: "Regional", hint: "Countries — click one to resolve individual entities" },
  local: { label: "Local", hint: "Individual entities and shipment routes" },
};

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
  scale,
  onResetView,
}: MapControlsProps) {
  return (
    <div className={styles.bar}>
      <EntitySearchBox onSelect={onSearchSelect} placeholder="Find an entity…" />

      <SelectControl
        icon={Shapes}
        value={entityType}
        active={entityType !== "all"}
        onChange={(e) => onEntityTypeChange(e.target.value as EntityTypeFilter)}
        aria-label="Entity type"
        options={[
          { value: "all", label: "All entity types" },
          { value: "Person", label: "Persons" },
          { value: "Organization", label: "Organizations" },
        ]}
      />

      <SelectControl
        icon={ShieldAlert}
        value={riskFilter}
        active={riskFilter > 0}
        onChange={(e) => onRiskFilterChange(Number(e.target.value))}
        aria-label="Minimum risk level"
        options={RISK_FILTERS}
      />

      <SelectControl
        icon={Route}
        value={routeFilter}
        active={routeFilter === "anomalies"}
        onChange={(e) => onRouteFilterChange(e.target.value as RouteFilter)}
        aria-label="Route filter"
        options={[
          { value: "anomalies", label: "Anomalous routes only" },
          { value: "all", label: "All shipment routes" },
        ]}
      />

      <button type="button" className={cn(styles.iconButton, showEntities && styles.iconButtonActive)} onClick={onToggleEntities}>
        <MapPin size={14} /> Entities
      </button>
      <button type="button" className={cn(styles.iconButton, showShipments && styles.iconButtonActive)} onClick={onToggleShipments}>
        <Route size={14} /> Routes
      </button>

      <button
        type="button"
        className={styles.iconButton}
        onClick={onResetView}
        disabled={scale === "world"}
        title="Return to the world view"
      >
        <Globe2 size={14} /> World
      </button>

      <div className={styles.spacer} />
      <span className={styles.scaleBadge}>
        <strong>{SCALE_COPY[scale].label}</strong>
        <span className={styles.scaleHint}>{SCALE_COPY[scale].hint}</span>
      </span>
    </div>
  );
}

// The legend describes what is actually on screen at the current tier. A single
// fixed legend was describing entity colours while the map was drawing regional
// aggregates, which made the encoding look wrong rather than absent.
const LEGEND_BY_SCALE: Record<MapScale, { label: string; color: string }[]> = {
  world: [
    { label: "No elevated entities", color: "#5685D6" },
    { label: "Elevated present", color: RISK_COLORS.High },
    { label: "Multiple elevated", color: RISK_COLORS.Critical },
    { label: "Corridor with anomalies", color: RISK_COLORS.Critical },
  ],
  regional: [
    { label: "No elevated entities", color: "#5685D6" },
    { label: "Elevated present", color: RISK_COLORS.High },
    { label: "Multiple elevated", color: RISK_COLORS.Critical },
    { label: "Anomalous route", color: RISK_COLORS.Critical },
  ],
  local: [
    { label: "Person", color: "#94A3B8" },
    { label: "Organization", color: "#A855F7" },
    { label: "High risk", color: RISK_COLORS.High },
    { label: "Critical risk", color: RISK_COLORS.Critical },
    { label: "Anomalous route", color: RISK_COLORS.Critical },
  ],
};

export function MapLegend({ scale }: { scale: MapScale }) {
  return (
    <div className={styles.legend}>
      {LEGEND_BY_SCALE[scale].map((item) => (
        <span key={item.label} className={styles.legendItem}>
          <span className={styles.dot} style={{ background: item.color }} />
          {item.label}
        </span>
      ))}
    </div>
  );
}
