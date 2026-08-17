import { ArrowRight, X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { AssessmentBadge } from "@/components/ui/AssessmentBadge";
import { formatDate } from "@/lib/formatters";
import type { ShipmentRoute } from "@/hooks/useMap";
import { useSubjectAssessment } from "@/hooks/useAssessment";
import styles from "./ShipmentDetailPopup.module.css";

/**
 * Why the route was flagged, not just that it was.
 *
 * This used to render a fixed explanation per `anomaly_kind` — a label the
 * scenario generator writes onto the shipments it made anomalous. The map was
 * restating the answer key with a confident heading over it. The finding now
 * comes from ARGUS's own assessment of that shipment, which names the measured
 * quantity that produced it: the detour ratio, the corridor's share of traffic,
 * or the two manifests that disagree.
 */
export function ShipmentDetailPopup({ shipment, onClose }: { shipment: ShipmentRoute; onClose: () => void }) {
  const { data: assessment } = useSubjectAssessment(shipment.shipment_id);
  const fired = (assessment?.signals ?? []).filter((s) => s.evaluable && (s.magnitude ?? 0) > 0);
  const blind = (assessment?.signals ?? []).filter((s) => !s.evaluable);

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

      {shipment.argus_band ? (
        <div className={styles.finding}>
          <div className={styles.findingHead}>
            <AssessmentBadge
              assessment={
                shipment.argus_band
                  ? {
                      band: shipment.argus_band as never,
                      score: shipment.argus_score,
                      coverage: shipment.argus_coverage,
                    }
                  : null
              }
            />
            <span className={styles.findingTitle}>
              {fired.length > 0
                ? `${fired.length} signal${fired.length === 1 ? "" : "s"} fired`
                : assessment
                  ? "Examined, nothing found"
                  : "ARGUS assessment"}
            </span>
          </div>
          {fired.map((signal) => (
            <p key={signal.signal_id} className={styles.findingDetail}>
              {signal.summary}
            </p>
          ))}
          {/* Stated, not omitted: a shipment whose manifests were never both
              recorded has not been cleared of a discrepancy. */}
          {blind.length > 0 ? (
            <p className={styles.findingDetail}>
              {blind.length} signal{blind.length === 1 ? "" : "s"} could not be evaluated.
            </p>
          ) : null}
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
