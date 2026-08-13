import { ArrowRight, X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { RiskBadge, riskLevelFromScore } from "@/components/ui/RiskBadge";
import type { ShipmentRoute } from "@/hooks/useMap";
import styles from "./ShipmentDetailPopup.module.css";

export function ShipmentDetailPopup({ shipment, onClose }: { shipment: ShipmentRoute; onClose: () => void }) {
  return (
    <div className={styles.popup}>
      <div className={styles.header}>
        <div>
          <div className={styles.title}>{shipment.shipment_id}</div>
          <div className={styles.route}>
            {shipment.origin_city} <ArrowRight size={13} /> {shipment.dest_city}
          </div>
        </div>
        <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close">
          <X size={14} />
        </Button>
      </div>

      {shipment.risk_score > 0 && <RiskBadge level={riskLevelFromScore(shipment.risk_score)} />}

      <div className={styles.rows}>
        <div className={styles.row}>
          <span className={styles.rowKey}>Carrier</span>
          <span className={styles.rowValue}>{shipment.carrier}</span>
        </div>
        <div className={styles.row}>
          <span className={styles.rowKey}>Status</span>
          <span className={styles.rowValue}>{shipment.status}</span>
        </div>
        <div className={styles.row}>
          <span className={styles.rowKey}>Route anomaly</span>
          <span className={styles.rowValue}>{shipment.route_anomaly ? "Yes" : "No"}</span>
        </div>
        <div className={styles.row}>
          <span className={styles.rowKey}>Risk score</span>
          <span className={styles.rowValue}>{shipment.risk_score}</span>
        </div>
      </div>
    </div>
  );
}
