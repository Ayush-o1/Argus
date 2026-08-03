import { ArrowUpRight } from "lucide-react";
import Link from "next/link";
import { RiskBadge, riskLevelFromScore } from "@/components/ui/RiskBadge";
import type { GraphNode } from "@/lib/types";
import { EntityTypeIcon } from "./EntityTypeIcon";
import styles from "./EntityCard.module.css";

function metaLine(node: GraphNode): string {
  const p = node.properties;
  switch (node.label) {
    case "Person":
      return [p.occupation, p.city].filter(Boolean).join(" · ");
    case "Organization":
      return [p.industry, p.registered_city].filter(Boolean).join(" · ");
    case "Vehicle":
      return [p.make, p.model, p.plate].filter(Boolean).join(" · ");
    case "Device":
      return [p.type, p.carrier].filter(Boolean).join(" · ");
    default:
      return node.label;
  }
}

export function EntityCard({ node }: { node: GraphNode }) {
  return (
    <Link href={`/entities/${node.id}`} className={styles.card}>
      <span className={styles.iconWrap}>
        <EntityTypeIcon label={node.label} size={18} />
      </span>
      <div className={styles.body}>
        <div className={styles.topRow}>
          <span className={styles.name}>{node.name}</span>
        </div>
        <span className={styles.meta}>{metaLine(node)}</span>
      </div>
      {node.risk_score > 0 ? <RiskBadge level={riskLevelFromScore(node.risk_score)} /> : null}
      <span className={styles.actions}>
        <ArrowUpRight size={16} color="var(--text-tertiary)" />
      </span>
    </Link>
  );
}
