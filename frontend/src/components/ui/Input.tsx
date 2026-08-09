import { forwardRef, type InputHTMLAttributes, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/cn";
import styles from "./Input.module.css";

interface FieldWrapProps {
  label?: string;
  hint?: string;
  error?: string;
  id?: string;
}

function FieldWrap({ label, hint, error, id, children }: FieldWrapProps & { children: React.ReactNode }) {
  return (
    <div className={styles.field}>
      {label ? (
        <label className={styles.label} htmlFor={id}>
          {label}
        </label>
      ) : null}
      {children}
      {error ? <span className={styles.errorText}>{error}</span> : hint ? <span className={styles.hint}>{hint}</span> : null}
    </div>
  );
}

type InputProps = InputHTMLAttributes<HTMLInputElement> & FieldWrapProps;

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, hint, error, id, className, ...props }, ref) => (
    <FieldWrap label={label} hint={hint} error={error} id={id}>
      <input ref={ref} id={id} className={cn(styles.control, error && styles.controlError, className)} {...props} />
    </FieldWrap>
  ),
);
Input.displayName = "Input";

type TextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & FieldWrapProps;

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, hint, error, id, className, ...props }, ref) => (
    <FieldWrap label={label} hint={hint} error={error} id={id}>
      <textarea ref={ref} id={id} className={cn(styles.control, error && styles.controlError, className)} {...props} />
    </FieldWrap>
  ),
);
Textarea.displayName = "Textarea";

type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & FieldWrapProps;

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, hint, error, id, className, children, ...props }, ref) => (
    <FieldWrap label={label} hint={hint} error={error} id={id}>
      <select ref={ref} id={id} className={cn(styles.control, error && styles.controlError, className)} {...props}>
        {children}
      </select>
    </FieldWrap>
  ),
);
Select.displayName = "Select";
