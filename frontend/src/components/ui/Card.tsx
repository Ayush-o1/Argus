import type { HTMLAttributes } from "react";
import styles from "./Card.module.css";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  interactive?: boolean;
}

export function Card({ interactive, className, ...props }: CardProps) {
  const classes = [styles.card, interactive && styles.interactive, className].filter(Boolean).join(" ");
  return <div className={classes} {...props} />;
}
