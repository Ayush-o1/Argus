"use client";

import { Check } from "lucide-react";
import { motion } from "framer-motion";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import styles from "./SpotlightSection.module.css";

interface SpotlightSectionProps {
  id?: string;
  eyebrow: string;
  title: string;
  desc: string;
  points: string[];
  visual: ReactNode;
  reversed?: boolean;
}

export function SpotlightSection({ id, eyebrow, title, desc, points, visual, reversed }: SpotlightSectionProps) {
  return (
    <section id={id} className={cn(styles.section, reversed && styles.reversed)}>
      <motion.div
        className={styles.copy}
        initial={{ opacity: 0, y: 16 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-100px" }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      >
        <span className={styles.eyebrow}>{eyebrow}</span>
        <h2 className={`${styles.title} text-display-sm`}>{title}</h2>
        <p className={styles.desc}>{desc}</p>
        <div className={styles.points}>
          {points.map((point) => (
            <div key={point} className={styles.point}>
              <Check size={15} className={styles.pointIcon} strokeWidth={2.5} />
              <span>{point}</span>
            </div>
          ))}
        </div>
      </motion.div>

      <motion.div
        className={styles.visual}
        initial={{ opacity: 0, scale: 0.96 }}
        whileInView={{ opacity: 1, scale: 1 }}
        viewport={{ once: true, margin: "-100px" }}
        transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
      >
        {visual}
      </motion.div>
    </section>
  );
}
