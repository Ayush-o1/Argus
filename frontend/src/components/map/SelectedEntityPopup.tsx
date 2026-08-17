import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { AssessmentBadge } from "@/components/ui/AssessmentBadge";
import type { GraphNode } from "@/lib/types";
import styles from "./SelectedEntityPopup.module.css";

export function SelectedEntityPopup({ node, onClose }: { node: GraphNode; onClose: () => void }) {
  return (
    <div className={styles.popup}>
      <div className={styles.title}>{node.name}</div>
      <div className={styles.meta}>
        {node.label} · {node.properties.city ?? node.properties.registered_city}
      </div>
      <AssessmentBadge assessment={node.assessment} />
      <div style={{ display: "flex", gap: "var(--space-2)" }}>
        <Link href={`/entities/${node.id}`} style={{ flex: 1 }}>
          <Button variant="primary" size="sm" style={{ width: "100%" }}>
            View Profile
          </Button>
        </Link>
        <Link href={`/graph?seed=${node.id}`} style={{ flex: 1 }}>
          <Button variant="secondary" size="sm" style={{ width: "100%" }}>
            View on Graph
          </Button>
        </Link>
      </div>
      <Button variant="ghost" size="sm" onClick={onClose}>
        Close
      </Button>
    </div>
  );
}
