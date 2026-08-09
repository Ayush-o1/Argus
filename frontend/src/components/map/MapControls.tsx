import { ENTITY_COLORS, RISK_COLORS } from "@/lib/theme";
import styles from "./MapControls.module.css";

interface MapControlsProps {
  showEntities: boolean;
  showShipments: boolean;
  onToggleEntities: () => void;
  onToggleShipments: () => void;
}

export function MapControls({ showEntities, showShipments, onToggleEntities, onToggleShipments }: MapControlsProps) {
  return (
    <div className={styles.bar}>
      <button
        type="button"
        className={[styles.toggle, showEntities && styles.toggleActive].filter(Boolean).join(" ")}
        onClick={onToggleEntities}
      >
        <span className={styles.dot} style={{ background: ENTITY_COLORS.Person }} />
        Entities
      </button>
      <button
        type="button"
        className={[styles.toggle, showShipments && styles.toggleActive].filter(Boolean).join(" ")}
        onClick={onToggleShipments}
      >
        <span className={styles.dot} style={{ background: RISK_COLORS.High }} />
        Shipment Routes
      </button>
    </div>
  );
}
