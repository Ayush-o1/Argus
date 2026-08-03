"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { EmptyState } from "@/components/ui/EmptyState";
import { formatRelativeTime } from "@/lib/formatters";
import type { Incident } from "@/lib/types";
import { ShieldAlert } from "lucide-react";
import styles from "./IncidentFeed.module.css";

const MARKER_COLOR: Record<Incident["severity"], string> = {
  Critical: "var(--risk-critical)",
  High: "var(--risk-high)",
  Medium: "var(--risk-medium)",
  Low: "var(--risk-low)",
};

export function IncidentFeed({ incidents }: { incidents: Incident[] }) {
  if (incidents.length === 0) {
    return <EmptyState icon={ShieldAlert} title="No incidents" description="Nothing has been flagged yet." />;
  }

  return (
    <div className={styles.list}>
      {incidents.map((incident, i) => (
        <motion.div
          key={incident.incident_id}
          initial={{ opacity: 0, x: 8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.25, delay: i * 0.04 }}
        >
          <Link href="/alerts" className={styles.row}>
            <span className={styles.marker} style={{ background: MARKER_COLOR[incident.severity] }} />
            <div className={styles.body}>
              <div className={styles.topRow}>
                <span className={styles.type}>{incident.type.replace(/([A-Z])/g, " $1").trim()}</span>
              </div>
              <span className={styles.description}>{incident.description}</span>
            </div>
            <span className={styles.time}>{formatRelativeTime(incident.timestamp)}</span>
          </Link>
        </motion.div>
      ))}
    </div>
  );
}
