import { cn } from "@/lib/cn";
import { ENTITY_COLORS, RISK_COLORS } from "@/lib/theme";
import styles from "./MapControls.module.css";

interface MapControlsProps {
  showEntities: boolean;
  showShipments: boolean;
  highRiskOnly: boolean;
  onToggleEntities: () => void;
  onToggleShipments: () => void;
  onToggleHighRiskOnly: () => void;
}

export function MapControls({
  showEntities,
  showShipments,
  highRiskOnly,
  onToggleEntities,
  onToggleShipments,
  onToggleHighRiskOnly,
}: MapControlsProps) {
  return (
    <div className={styles.bar}>
      <button type="button" className={cn(styles.toggle, showEntities && styles.toggleActive)} onClick={onToggleEntities}>
        <span className={styles.dot} style={{ background: ENTITY_COLORS.Person }} />
        Entities
      </button>
      <button
        type="button"
        className={cn(styles.toggle, showEntities && highRiskOnly && styles.toggleActive)}
        onClick={onToggleHighRiskOnly}
        disabled={!showEntities}
        title="Only show entities with risk score 60 or higher"
      >
        <span className={styles.dot} style={{ background: RISK_COLORS.Critical }} />
        High Risk Only
      </button>
      <button type="button" className={cn(styles.toggle, showShipments && styles.toggleActive)} onClick={onToggleShipments}>
        <span className={styles.dot} style={{ background: RISK_COLORS.High }} />
        Shipment Routes
      </button>
    </div>
  );
}

const LEGEND_ITEMS = [
  { label: "Standard entity", color: ENTITY_COLORS.Person },
  { label: "Organization", color: ENTITY_COLORS.Organization },
  { label: "High risk (60+)", color: RISK_COLORS.Critical },
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
