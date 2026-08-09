import type { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";
import styles from "./Card.module.css";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  interactive?: boolean;
}

export function Card({ interactive, className, ...props }: CardProps) {
  return <div className={cn(styles.card, interactive && styles.interactive, className)} {...props} />;
}
