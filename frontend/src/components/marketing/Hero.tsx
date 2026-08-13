"use client";

import { motion } from "framer-motion";
import { ArrowRight, Waypoints } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { useDashboardSummary } from "@/hooks/useDashboard";
import { formatCompactNumber } from "@/lib/formatters";
import { GraphMotif } from "./GraphMotif";
import styles from "./Hero.module.css";

const FALLBACK_STATS = [
  { label: "Synthetic persons", value: "4,000" },
  { label: "Organizations", value: "409" },
  { label: "Transactions", value: "40,080" },
  { label: "Active cases", value: "20" },
];

export function Hero() {
  const { data: summary } = useDashboardSummary();

  const stats = summary
    ? [
        { label: "Synthetic persons", value: formatCompactNumber(summary.total_persons) },
        { label: "Organizations", value: formatCompactNumber(summary.total_organizations) },
        { label: "Transactions", value: formatCompactNumber(summary.total_transactions) },
        { label: "Active cases", value: String(summary.active_cases) },
      ]
    : FALLBACK_STATS;

  return (
    <section className={styles.hero} id="platform">
      <div className={styles.copy}>
        <motion.span
          className={styles.eyebrow}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        >
          <span className={styles.eyebrowDot} />
          Live instance · 100% synthetic data
        </motion.span>

        <motion.h1
          className={`${styles.headline} text-display-md`}
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.05, ease: [0.16, 1, 0.3, 1] }}
        >
          See the connections <span className={styles.headlineAccent}>others miss.</span>
        </motion.h1>

        <motion.p
          className={styles.subhead}
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.12, ease: [0.16, 1, 0.3, 1] }}
        >
          ARGUS is a graph-native investigation platform — entity graphs, geospatial patterns, and
          case management over a fully synthetic, India-grounded dataset. No real individuals, no
          scraping, no surveillance. An engineering demonstration built to work like the real thing.
        </motion.p>

        <motion.div
          className={styles.ctaRow}
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.18, ease: [0.16, 1, 0.3, 1] }}
        >
          <Link href="/dashboard">
            <Button variant="primary" size="lg">
              Enter Argus <ArrowRight size={16} />
            </Button>
          </Link>
          <a href="#intelligence" className={styles.secondaryLink}>
            <Waypoints size={15} />
            See the Graph Explorer
          </a>
        </motion.div>

        <motion.div
          className={styles.statStrip}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.3 }}
        >
          {stats.map((stat) => (
            <div key={stat.label} className={styles.stat}>
              <div className={styles.statValue}>{stat.value}</div>
              <div className={styles.statLabel}>{stat.label}</div>
            </div>
          ))}
        </motion.div>
      </div>

      <motion.div
        className={styles.visual}
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.8, delay: 0.15, ease: [0.16, 1, 0.3, 1] }}
      >
        <div className={styles.visualFrame} />
        <GraphMotif />
      </motion.div>
    </section>
  );
}
