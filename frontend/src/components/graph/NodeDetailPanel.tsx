"use client";

import { motion } from "framer-motion";
import { Waypoints } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { RiskBadge, riskLevelFromScore } from "@/components/ui/RiskBadge";
import { EntityTypeIcon } from "@/components/entity/EntityTypeIcon";
import { useEntity } from "@/hooks/useEntities";
import styles from "./NodeDetailPanel.module.css";

const DISPLAY_KEYS: Record<string, string[]> = {
  Person: ["occupation", "city", "state", "status"],
  Organization: ["type", "industry", "registered_city", "status"],
  Vehicle: ["make", "model", "plate"],
  Account: ["bank", "type", "balance_class"],
  Device: ["type", "carrier"],
};

interface NodeDetailPanelProps {
  entityId: string;
  onExpand: (entityId: string) => void;
  onClose: () => void;
}

export function NodeDetailPanel({ entityId, onExpand, onClose }: NodeDetailPanelProps) {
  const { data: entity } = useEntity(entityId);

  if (!entity) return null;

  const keys = DISPLAY_KEYS[entity.label] ?? [];

  return (
    <motion.div
      className={styles.panel}
      initial={{ opacity: 0, x: 12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.2 }}
    >
      <div className={styles.header}>
        <span className={styles.iconWrap}>
          <EntityTypeIcon label={entity.label} size={18} />
        </span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className={styles.name}>{entity.name}</div>
          <div className={styles.subtitle}>
            {entity.label} · {entity.id}
          </div>
        </div>
      </div>

      {entity.risk_score > 0 && (
        <div className={styles.section}>
          <span className={styles.sectionTitle}>Risk</span>
          <RiskBadge level={riskLevelFromScore(entity.risk_score)} />
        </div>
      )}

      {keys.length > 0 && (
        <div className={styles.section}>
          <span className={styles.sectionTitle}>Properties</span>
          {keys.map((key) => (
            <div key={key} className={styles.propertyRow}>
              <span className={styles.propertyKey}>{key.replace(/_/g, " ")}</span>
              <span className={styles.propertyValue}>{String(entity.properties[key] ?? "—")}</span>
            </div>
          ))}
        </div>
      )}

      {entity.degree !== undefined && (
        <div className={styles.section}>
          <span className={styles.sectionTitle}>Connections</span>
          <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>{entity.degree} total relationships</span>
        </div>
      )}

      <div className={styles.actions}>
        <Button variant="secondary" size="sm" onClick={() => onExpand(entityId)}>
          <Waypoints size={14} /> Expand Neighbors
        </Button>
        <Link href={`/entities/${entityId}`}>
          <Button variant="primary" size="sm" style={{ width: "100%" }}>
            View Full Profile
          </Button>
        </Link>
        <Button variant="ghost" size="sm" onClick={onClose}>
          Close
        </Button>
      </div>
    </motion.div>
  );
}
