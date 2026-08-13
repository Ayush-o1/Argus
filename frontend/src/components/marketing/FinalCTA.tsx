"use client";

import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import styles from "./FinalCTA.module.css";

export function FinalCTA() {
  return (
    <section className={styles.section}>
      <motion.div
        className={styles.panel}
        initial={{ opacity: 0, y: 16 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-100px" }}
        transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
      >
        <div className={styles.glow} />
        <h2 className={`${styles.title} text-display-sm`}>Open the graph. Follow the pattern.</h2>
        <p className={styles.desc}>
          The full instance is running right now — synthetic data, real architecture, no signup.
        </p>
        <div className={styles.actions}>
          <Link href="/dashboard">
            <Button variant="primary" size="lg">
              Enter Argus <ArrowRight size={16} />
            </Button>
          </Link>
          <Link href="/graph">
            <Button variant="secondary" size="lg">
              Open Graph Explorer
            </Button>
          </Link>
        </div>
      </motion.div>
    </section>
  );
}
