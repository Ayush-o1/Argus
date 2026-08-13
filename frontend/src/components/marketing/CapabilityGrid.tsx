"use client";

import { AlertTriangle, BarChart3, Cpu, FlaskConical, Map, Waypoints, type LucideIcon } from "lucide-react";
import { motion } from "framer-motion";
import styles from "./CapabilityGrid.module.css";

interface Capability {
  icon: LucideIcon;
  title: string;
  desc: string;
}

const CAPABILITIES: Capability[] = [
  {
    icon: Waypoints,
    title: "Graph Explorer",
    desc: "A risk-led entity graph over live Neo4j data — neighborhood expansion, shortest-path finding, and focus mode instead of a static hairball.",
  },
  {
    icon: Map,
    title: "Geospatial Intelligence",
    desc: "Shipment routes and entity locations across real Indian geography, clustered and filtered so anomalies stand out instead of drowning in lines.",
  },
  {
    icon: BarChart3,
    title: "Analytics Engine",
    desc: "PageRank, betweenness, Louvain communities, and cycle detection via Neo4j GDS, plus Isolation Forest anomaly detection over transactions.",
  },
  {
    icon: AlertTriangle,
    title: "Cases & Alerts",
    desc: "An investigation workspace with an evidence board, notes, and status tracking, backed by a review queue over system-flagged incidents.",
  },
  {
    icon: Cpu,
    title: "Local Intelligence Layer",
    desc: "Deterministic, template-composed entity and case narratives with zero network calls — plus an entirely optional local-LLM assistant.",
  },
  {
    icon: FlaskConical,
    title: "Scenario Generator",
    desc: "Injects a new, realistic investigation storyline into the live graph on demand, using the same engine that built the synthetic world.",
  },
];

export function CapabilityGrid() {
  return (
    <section className={styles.section}>
      <motion.div
        className={styles.header}
        initial={{ opacity: 0, y: 12 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-80px" }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      >
        <span className={styles.eyebrow}>Capabilities</span>
        <h2 className={`${styles.title} text-display-sm`}>One dataset, every angle of investigation.</h2>
        <p className={styles.desc}>
          Every surface in ARGUS reads from the same live graph — nothing here is a mockup or a
          disconnected demo screen.
        </p>
      </motion.div>

      <div className={styles.grid}>
        {CAPABILITIES.map((cap, i) => (
          <motion.div
            key={cap.title}
            className={styles.card}
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-60px" }}
            transition={{ duration: 0.45, delay: i * 0.05, ease: [0.16, 1, 0.3, 1] }}
          >
            <span className={styles.iconWrap}>
              <cap.icon size={17} strokeWidth={1.75} />
            </span>
            <div className={styles.cardTitle}>{cap.title}</div>
            <p className={styles.cardDesc}>{cap.desc}</p>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
