"use client";

import { EntityTypeIcon } from "@/components/entity/EntityTypeIcon";
import { formatScore, scoreWithCoverage } from "@/lib/assessment";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/lib/cn";
import { RISK_COLORS, assessmentTier } from "@/lib/theme";
import type { GraphNode } from "@/lib/types";
import styles from "./LeadQueue.module.css";

const TIER_COLOR: Record<string, string> = {
  critical: RISK_COLORS.Critical,
  high: RISK_COLORS.High,
  medium: RISK_COLORS.Medium,
  low: RISK_COLORS.Low,
  none: RISK_COLORS.Low,
};

/**
 * The ranked list of what to look at, as the selector for the context panel
 * beside it rather than as a set of links out.
 *
 * Selecting a lead keeps the analyst on the dashboard and fills in the case for
 * pursuing it. The previous queue navigated straight to an entity profile,
 * which meant the only way to compare two leads was to leave and come back.
 */
export function LeadQueue({
  leads,
  isLoading,
  selectedId,
  onSelect,
  emptyLabel,
}: {
  leads: GraphNode[];
  isLoading: boolean;
  selectedId: string | null;
  onSelect: (lead: GraphNode) => void;
  emptyLabel: string;
}) {
  if (isLoading) {
    return (
      <div className={styles.list}>
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} height={52} />
        ))}
      </div>
    );
  }

  if (leads.length === 0) {
    return <p className={styles.empty}>{emptyLabel}</p>;
  }

  return (
    <ul className={styles.list} role="listbox" aria-label="Investigation leads">
      {leads.map((lead, i) => {
        const tier = assessmentTier(lead.assessment?.band);
        const selected = lead.id === selectedId;
        const place = [lead.properties.city ?? lead.properties.registered_city, lead.properties.country]
          .filter(Boolean)
          .join(", ");
        return (
          <li key={lead.uuid}>
            <button
              type="button"
              role="option"
              aria-selected={selected}
              className={cn(styles.row, selected && styles.rowSelected)}
              onClick={() => onSelect(lead)}
            >
              <span className={styles.rank}>{i + 1}</span>
              <span className={styles.icon}>
                <EntityTypeIcon label={lead.label} size={15} />
              </span>
              <span className={styles.body}>
                <span className={styles.name}>{lead.name}</span>
                <span className={styles.meta}>{place || lead.label}</span>
              </span>
              <span
                className={styles.score}
                style={{ color: TIER_COLOR[tier] }}
                title={scoreWithCoverage(lead.assessment?.score, lead.assessment?.coverage)}
              >
                {formatScore(lead.assessment?.score) ?? "—"}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
