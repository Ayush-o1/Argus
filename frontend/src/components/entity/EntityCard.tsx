import { ArrowUpRight } from "lucide-react";
import { AssessmentBadge } from "@/components/ui/AssessmentBadge";
import Link from "next/link";
import type { GraphNode } from "@/lib/types";
import { EntityTypeIcon } from "./EntityTypeIcon";
import styles from "./EntityCard.module.css";

// City alone is ambiguous in a world with 70 of them across 50 countries —
// "Bengaluru" and "Santos" carry very different context, and an analyst
// scanning results shouldn't have to open each one to find out where it is.
function placeOf(node: GraphNode): string {
  const p = node.properties;
  const city = p.city ?? p.registered_city;
  return [city, p.country].filter(Boolean).join(", ");
}

function metaLine(node: GraphNode): string {
  const p = node.properties;
  switch (node.label) {
    case "Person":
      return [p.occupation, placeOf(node)].filter(Boolean).join(" · ");
    case "Organization":
      return [p.industry, placeOf(node)].filter(Boolean).join(" · ");
    case "Location":
      return [p.type, placeOf(node)].filter(Boolean).join(" · ");
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
      <AssessmentBadge assessment={node.assessment} />
      <span className={styles.actions}>
        <ArrowUpRight size={16} color="var(--text-tertiary)" />
      </span>
    </Link>
  );
}
