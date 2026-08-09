import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import styles from "./Badge.module.css";

type Tone = "neutral" | "accent" | "critical" | "high" | "medium" | "low";

interface BadgeProps {
  tone?: Tone;
  children: ReactNode;
  className?: string;
}

export function Badge({ tone = "neutral", children, className }: BadgeProps) {
  return <span className={cn(styles.badge, styles[tone], className)}>{children}</span>;
}
