import { ArrowRight, X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { RiskBadge, riskLevelFromScore } from "@/components/ui/RiskBadge";
import { formatDate } from "@/lib/formatters";
import type { AnomalyKind, ShipmentRoute } from "@/hooks/useMap";
import styles from "./ShipmentDetailPopup.module.css";

/**
 * Why the route was flagged, not just that it was.
 *
 * "Route anomaly: Yes" states a conclusion and leaves the analyst to guess the
 * reasoning. Each kind is a different finding with a different follow-up, so
 * each gets its own explanation grounded in the fields that produced it.
 */
const ANOMALY_EXPLANATION: Record<AnomalyKind, { title: string; detail: string }> = {
  off_lane: {
    title: "Off-lane routing",
    detail: "These two regions have no established freight relationship in this dataset.",
  },
  circuitous: {
    title: "Circuitous detour",
    detail: "The shipment called at a port well off the direct path between origin and destination.",
  },
  manifest_shift: {
    title: "Manifest discrepancy",
    detail: "Goods declared at origin do not match what was recorded on arrival.",
  },
};

// A route flagged without a recorded kind still has to say something; silently
// rendering nothing would put the analyst back to reading a red line with no
// reasoning attached.
const UNSPECIFIED_ANOMALY = {
  title: "Route flagged",
  detail: "This route was flagged as anomalous, but no specific finding was recorded against it.",
};

export function ShipmentDetailPopup({ shipment, onClose }: { shipment: ShipmentRoute; onClose: () => void }) {
  const explanation = shipment.anomaly_kind
    ? ANOMALY_EXPLANATION[shipment.anomaly_kind]
    : shipment.route_anomaly
      ? UNSPECIFIED_ANOMALY
      : null;

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

      {explanation ? (
        <div className={styles.finding}>
          <div className={styles.findingHead}>
            <RiskBadge level={riskLevelFromScore(shipment.risk_score)} />
            <span className={styles.findingTitle}>{explanation.title}</span>
          </div>
          <p className={styles.findingDetail}>{explanation.detail}</p>
          {shipment.via_city ? (
            <p className={styles.findingDetail}>
              Called at <strong>{shipment.via_city}</strong>
              {shipment.via_country ? `, ${shipment.via_country}` : ""}
              {shipment.detour_ratio && shipment.detour_ratio > 1
                ? ` — ${shipment.detour_ratio}× the direct distance.`
                : "."}
            </p>
          ) : null}
        </div>
      ) : null}

      <div className={styles.rows}>
        <Row label="Lane" value={shipment.lane ?? "—"} />
        <Row label="Carrier" value={shipment.carrier} />
        <Row label="Status" value={shipment.status} />
        {shipment.departure ? <Row label="Departed" value={formatDate(shipment.departure)} /> : null}
        {shipment.arrival ? <Row label="Arrived" value={formatDate(shipment.arrival)} /> : null}
        {shipment.distance_km ? <Row label="Distance" value={`${shipment.distance_km.toLocaleString()} km`} /> : null}
        {shipment.manifest?.length ? <Row label="Manifest" value={shipment.manifest.join(", ")} /> : null}
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.row}>
      <span className={styles.rowKey}>{label}</span>
      <span className={styles.rowValue}>{value}</span>
    </div>
  );
}
