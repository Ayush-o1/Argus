"use client";

import { motion } from "framer-motion";
import { Crosshair, Waypoints, X } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { RiskBadge, riskLevelFromScore } from "@/components/ui/RiskBadge";
import { EntityTypeIcon } from "@/components/entity/EntityTypeIcon";
import { useEntity } from "@/hooks/useEntities";
import type { NeighborConnection } from "./GraphCanvas";
import styles from "./NodeDetailPanel.module.css";

const DISPLAY_KEYS: Record<string, string[]> = {
  Person: ["occupation", "city", "state", "status"],
  Organization: ["type", "industry", "registered_city", "status"],
  Vehicle: ["make", "model", "plate"],
  Account: ["bank", "type", "balance_class"],
  Device: ["type", "carrier"],
};

function formatRelType(type: string): string {
  return type.replace(/_/g, " ").toLowerCase();
}

interface NodeDetailPanelProps {
  entityId: string;
  connections: NeighborConnection[];
  isFocused: boolean;
  onExpand: (entityId: string) => void;
  onFocus: (entityId: string) => void;
  onClearFocus: () => void;
  onSelectConnection: (entityId: string) => void;
  onClose: () => void;
}

export function NodeDetailPanel({
  entityId,
  connections,
  isFocused,
  onExpand,
  onFocus,
  onClearFocus,
  onSelectConnection,
  onClose,
}: NodeDetailPanelProps) {
  const { data: entity } = useEntity(entityId);

  if (!entity) return null;

  const keys = DISPLAY_KEYS[entity.label] ?? [];
  const shown = connections.slice(0, 12);

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
        <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close">
          <X size={14} />
        </Button>
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

      {connections.length > 0 && (
        <div className={styles.section}>
          <span className={styles.sectionTitle}>
            Connections on canvas ({connections.length})
          </span>
          <div className={styles.connectionsList}>
            {shown.map((c) => (
              <button
                key={c.edge.id}
                type="button"
                className={styles.connectionRow}
                onClick={() => onSelectConnection(c.other.id)}
                title={`${entity.name} ${c.direction === "outgoing" ? formatRelType(c.edge.type) : `← ${formatRelType(c.edge.type)}`} ${c.other.name}`}
              >
                <span className={styles.connectionIcon}>
                  <EntityTypeIcon label={c.other.label} size={13} />
                </span>
                <span className={styles.connectionBody}>
                  <div className={styles.connectionName}>{c.other.name}</div>
                  <div className={styles.connectionRel}>
                    {c.direction === "outgoing" ? "→" : "←"} {formatRelType(c.edge.type)}
                  </div>
                </span>
              </button>
            ))}
          </div>
          {connections.length > shown.length && (
            <div className={styles.connectionsMore}>+{connections.length - shown.length} more — expand to load</div>
          )}
        </div>
      )}

      <div className={styles.actions}>
        <div className={styles.actionRow}>
          <Button variant="secondary" size="sm" onClick={() => onExpand(entityId)}>
            <Waypoints size={14} /> Expand
          </Button>
          {isFocused ? (
            <Button variant="secondary" size="sm" onClick={onClearFocus}>
              <Crosshair size={14} /> Unfocus
            </Button>
          ) : (
            <Button variant="secondary" size="sm" onClick={() => onFocus(entityId)}>
              <Crosshair size={14} /> Focus
            </Button>
          )}
        </div>
        <Link href={`/entities/${entityId}`}>
          <Button variant="primary" size="sm" style={{ width: "100%" }}>
            View Full Profile
          </Button>
        </Link>
      </div>
    </motion.div>
  );
}
