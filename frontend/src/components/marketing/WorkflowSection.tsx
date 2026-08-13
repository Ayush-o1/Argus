"use client";

import { Map, Search, ShieldHalf, Waypoints, type LucideIcon } from "lucide-react";
import { motion } from "framer-motion";
import styles from "./WorkflowSection.module.css";

interface Step {
  icon: LucideIcon;
  title: string;
  desc: string;
}

const STEPS: Step[] = [
  {
    icon: Search,
    title: "Search",
    desc: "Jump to any entity by name, ID, or attribute — or press ⌘K from anywhere in the product.",
  },
  {
    icon: Waypoints,
    title: "Explore the graph",
    desc: "Follow relationships from a risk-led starting point, expand neighborhoods, trace shortest paths.",
  },
  {
    icon: Map,
    title: "Correlate",
    desc: "Cross-reference geography and time — shipment routes, locations, and activity on the timeline.",
  },
  {
    icon: ShieldHalf,
    title: "Investigate",
    desc: "Build a case, attach evidence, review alerts, and run analytics against the same live graph.",
  },
];

export function WorkflowSection() {
  return (
    <section id="workflow" className={styles.section}>
      <motion.div
        className={styles.header}
        initial={{ opacity: 0, y: 12 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-80px" }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      >
        <span className={styles.eyebrow}>Investigation workflow</span>
        <h2 className={`${styles.title} text-display-sm`}>From a name to a case, in one flow.</h2>
        <p className={styles.desc}>
          ARGUS is built around how an analyst actually works — not a collection of disconnected
          screens.
        </p>
      </motion.div>

      <div className={styles.steps}>
        {STEPS.map((step, i) => (
          <motion.div
            key={step.title}
            className={styles.step}
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-60px" }}
            transition={{ duration: 0.45, delay: i * 0.08, ease: [0.16, 1, 0.3, 1] }}
          >
            <span className={styles.stepIndex}>
              <step.icon size={17} strokeWidth={1.75} />
            </span>
            <div className={styles.stepTitle}>{step.title}</div>
            <p className={styles.stepDesc}>{step.desc}</p>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
