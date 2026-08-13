"use client";

import { motion } from "framer-motion";
import { ArrowRight, Waypoints, X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { EntityTypeIcon } from "@/components/entity/EntityTypeIcon";
import { formatDate, formatINR } from "@/lib/formatters";
import type { EdgeDetail } from "./GraphCanvas";
import styles from "./NodeDetailPanel.module.css";

function formatRelType(type: string): string {
  return type.replace(/_/g, " ").toLowerCase();
}

function formatPropertyValue(key: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  const lowerKey = key.toLowerCase();
  if (typeof value === "number" && (lowerKey.includes("amount") || lowerKey.includes("balance"))) {
    return formatINR(value);
  }
  if (typeof value === "string" && (lowerKey.includes("date") || lowerKey.includes("timestamp") || lowerKey.includes("_at"))) {
    const parsed = Date.parse(value);
    if (!Number.isNaN(parsed)) return formatDate(value);
  }
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

interface RelationshipPanelProps {
  detail: EdgeDetail;
  onSelectEntity: (entityId: string) => void;
  onClose: () => void;
}

/** Answers "why are these two entities connected?" directly — the
 * relationship type plus every property the edge actually carries (amount,
 * date, device id, whatever the data has), instead of leaving the analyst to
 * infer it from an unlabeled line. */
export function RelationshipPanel({ detail, onSelectEntity, onClose }: RelationshipPanelProps) {
  const { edge, source, target } = detail;
  // Internal correlation/foreign-key ids are redundant with the "Between"
  // section above, which already names both endpoints by their actual entity.
  const propertyEntries = Object.entries(edge.properties).filter(([key]) => !key.endsWith("_id"));

  return (
    <motion.div
      className={styles.panel}
      initial={{ opacity: 0, x: 12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.2 }}
    >
      <div className={styles.header}>
        <span className={styles.iconWrap}>
          <Waypoints size={17} color="var(--accent-primary-hover)" />
        </span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className={styles.name}>{formatRelType(edge.type)}</div>
          <div className={styles.subtitle}>Relationship</div>
        </div>
        <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close">
          <X size={14} />
        </Button>
      </div>

      <div className={styles.section}>
        <span className={styles.sectionTitle}>Between</span>
        <button type="button" className={styles.connectionRow} onClick={() => onSelectEntity(source.id)}>
          <span className={styles.connectionIcon}>
            <EntityTypeIcon label={source.label} size={13} />
          </span>
          <span className={styles.connectionBody}>
            <div className={styles.connectionName}>{source.name}</div>
            <div className={styles.connectionRel}>{source.label}</div>
          </span>
        </button>
        <div style={{ display: "flex", justifyContent: "center", color: "var(--text-tertiary)" }}>
          <ArrowRight size={14} />
        </div>
        <button type="button" className={styles.connectionRow} onClick={() => onSelectEntity(target.id)}>
          <span className={styles.connectionIcon}>
            <EntityTypeIcon label={target.label} size={13} />
          </span>
          <span className={styles.connectionBody}>
            <div className={styles.connectionName}>{target.name}</div>
            <div className={styles.connectionRel}>{target.label}</div>
          </span>
        </button>
      </div>

      {propertyEntries.length > 0 && (
        <div className={styles.section}>
          <span className={styles.sectionTitle}>Details</span>
          {propertyEntries.map(([key, value]) => (
            <div key={key} className={styles.propertyRow}>
              <span className={styles.propertyKey}>{key.replace(/_/g, " ")}</span>
              <span className={styles.propertyValue}>{formatPropertyValue(key, value)}</span>
            </div>
          ))}
        </div>
      )}
    </motion.div>
  );
}
