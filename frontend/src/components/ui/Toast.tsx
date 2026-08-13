"use client";

import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import styles from "./Toast.module.css";

type ToastTone = "info" | "success" | "error";

interface ToastItem {
  id: string;
  message: string;
  tone: ToastTone;
}

interface ToastContextValue {
  showToast: (message: string, tone?: ToastTone) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const TOAST_TTL_MS = 5000;

const TONE_ICON: Record<ToastTone, typeof Info> = {
  info: Info,
  success: CheckCircle2,
  error: AlertCircle,
};

function subscribeNoop() {
  return () => {};
}

/** Portals render nothing during SSR; reporting "not mounted yet" for the
 * server snapshot (and the client's very first synchronous render) keeps
 * that first render identical to the server's, so hydration never has to
 * reconcile a mismatch — the standard useSyncExternalStore idiom for
 * client-only rendering, without the cascading re-render an effect-driven
 * setState would cause. */
function useMounted(): boolean {
  return useSyncExternalStore(
    subscribeNoop,
    () => true,
    () => false,
  );
}

/** App-wide toast notifications. Mounted once in Providers; call
 * `useToast().showToast(...)` from anywhere instead of each page building
 * its own inline confirmation banner. */
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const mounted = useMounted();
  const idRef = useRef(0);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showToast = useCallback(
    (message: string, tone: ToastTone = "info") => {
      const id = `toast-${++idRef.current}`;
      setToasts((prev) => [...prev, { id, message, tone }]);
      window.setTimeout(() => dismiss(id), TOAST_TTL_MS);
    },
    [dismiss],
  );

  const value = useMemo(() => ({ showToast }), [showToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      {mounted
        ? createPortal(
            <div className={styles.viewport} role="status" aria-live="polite">
              {toasts.map((t) => {
                const Icon = TONE_ICON[t.tone];
                return (
                  <div key={t.id} className={styles.toast} data-tone={t.tone}>
                    <Icon size={16} className={styles.icon} />
                    <span className={styles.message}>{t.message}</span>
                    <button type="button" className={styles.dismiss} onClick={() => dismiss(t.id)} aria-label="Dismiss">
                      <X size={14} />
                    </button>
                  </div>
                );
              })}
            </div>,
            document.body,
          )
        : null}
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
