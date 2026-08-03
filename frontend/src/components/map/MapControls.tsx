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
        <span className={styles.dot} style={{ background: "#3D7BFF" }} />
        Entities
      </button>
      <button
        type="button"
        className={[styles.toggle, showShipments && styles.toggleActive].filter(Boolean).join(" ")}
        onClick={onToggleShipments}
      >
        <span className={styles.dot} style={{ background: "#FF7D1A" }} />
        Shipment Routes
      </button>
    </div>
  );
}
