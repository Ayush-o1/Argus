import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import styles from "./Badge.module.css";

type Tone = "neutral" | "accent" | "critical" | "high" | "medium" | "low" | "ok";

interface BadgeProps {
  tone?: Tone;
  children: ReactNode;
  className?: string;
  /** Hover text. Used by AssessmentBadge to carry the evidence coverage
   * alongside a score, so the qualifier is always within reach of the number
   * even where space forces the badge to be terse. */
  title?: string;
}

export function Badge({ tone = "neutral", children, className, title }: BadgeProps) {
  return (
    <span className={cn(styles.badge, styles[tone], className)} title={title}>
      {children}
    </span>
  );
}
