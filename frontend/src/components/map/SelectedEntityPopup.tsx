import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { RiskBadge, riskLevelFromScore } from "@/components/ui/RiskBadge";
import type { GraphNode } from "@/lib/types";
import styles from "./SelectedEntityPopup.module.css";

export function SelectedEntityPopup({ node, onClose }: { node: GraphNode; onClose: () => void }) {
  return (
    <div className={styles.popup}>
      <div className={styles.title}>{node.name}</div>
      <div className={styles.meta}>
        {node.label} · {node.properties.city ?? node.properties.registered_city}
      </div>
      {node.risk_score > 0 ? <RiskBadge level={riskLevelFromScore(node.risk_score)} /> : null}
      <Link href={`/entities/${node.id}`}>
        <Button variant="primary" size="sm" style={{ width: "100%" }}>
          View Profile
        </Button>
      </Link>
      <Button variant="ghost" size="sm" onClick={onClose}>
        Close
      </Button>
    </div>
  );
}
