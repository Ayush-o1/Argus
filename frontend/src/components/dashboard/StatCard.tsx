"use client";

import { motion, useMotionValue, useSpring } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import styles from "./StatCard.module.css";

interface StatCardProps {
  label: string;
  value: number;
  suffix?: string;
  icon: LucideIcon;
  decimals?: number;
  /** When set, the whole card links to a filtered investigation view instead
   * of just displaying the number — e.g. "Open Alerts" -> /alerts?status=Open. */
  href?: string;
}

export function StatCard({ label, value, suffix, icon: Icon, decimals = 0, href }: StatCardProps) {
  const motionValue = useMotionValue(0);
  const spring = useSpring(motionValue, { duration: 0.6, bounce: 0 });
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    motionValue.set(value);
  }, [value, motionValue]);

  useEffect(() => {
    const unsubscribe = spring.on("change", (latest) => setDisplay(latest));
    return unsubscribe;
  }, [spring]);

  const card = (
    <motion.div className={styles.card} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
      <div className={styles.header}>
        <span className={styles.label}>{label}</span>
        <span className={styles.iconWrap}>
          <Icon size={15} strokeWidth={2} />
        </span>
      </div>
      <div className={styles.row}>
        <span className={styles.value}>{display.toFixed(decimals)}</span>
        {suffix ? <span className={styles.suffix}>{suffix}</span> : null}
      </div>
    </motion.div>
  );

  return href ? (
    <Link href={href} className={styles.link} aria-label={`${label}: view details`}>
      {card}
    </Link>
  ) : (
    card
  );
}
