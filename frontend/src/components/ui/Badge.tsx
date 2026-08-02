import type { ReactNode } from "react";
import styles from "./Badge.module.css";

type Tone = "neutral" | "accent" | "critical" | "high" | "medium" | "low";

interface BadgeProps {
  tone?: Tone;
  children: ReactNode;
  className?: string;
}

export function Badge({ tone = "neutral", children, className }: BadgeProps) {
  return <span className={[styles.badge, styles[tone], className].filter(Boolean).join(" ")}>{children}</span>;
}
