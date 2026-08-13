"use client";

import { Boxes, Cpu, Database, GitBranch, Lock, Server } from "lucide-react";
import { motion } from "framer-motion";
import styles from "./TechCredibility.module.css";

const STACK = [
  { icon: GitBranch, label: "Neo4j 5 + GDS", role: "Graph database & algorithms" },
  { icon: Server, label: "FastAPI", role: "Async Python backend" },
  { icon: Boxes, label: "Next.js 16", role: "App Router frontend" },
  { icon: Cpu, label: "scikit-learn", role: "Isolation Forest anomaly detection" },
  { icon: Database, label: "Redis", role: "Cache & async job status" },
  { icon: Lock, label: "Ollama (optional)", role: "Local-only LLM assistant" },
];

export function TechCredibility() {
  return (
    <section id="architecture" className={styles.section}>
      <motion.div
        className={styles.panel}
        initial={{ opacity: 0, y: 16 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-100px" }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      >
        <div>
          <span className={styles.eyebrow}>Local-first, by design</span>
          <h2 className={`${styles.title} text-display-sm`}>No hosted AI dependency. Ever.</h2>
          <p className={styles.desc}>
            Every &quot;intelligence&quot; feature in ARGUS is a graph algorithm, a classical ML
            model trained fresh on its own synthetic data, or a deterministic template composer —
            never an API call to a hosted model. The one optional LLM surface talks only to a local
            Ollama instance you run yourself, and the rest of the product has zero dependency on it.
          </p>
        </div>

        <div className={styles.stackGrid}>
          {STACK.map((item) => (
            <div key={item.label} className={styles.stackItem}>
              <item.icon size={16} strokeWidth={1.75} color="var(--accent-primary-hover)" />
              <div>
                <div className={styles.stackLabel}>{item.label}</div>
                <div className={styles.stackRole}>{item.role}</div>
              </div>
            </div>
          ))}
        </div>
      </motion.div>
    </section>
  );
}
