import { type ButtonHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/cn";
import styles from "./Button.module.css";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", size = "md", className, ...props }, ref) => {
    return <button ref={ref} className={cn(styles.button, styles[variant], styles[size], className)} {...props} />;
  },
);

Button.displayName = "Button";
