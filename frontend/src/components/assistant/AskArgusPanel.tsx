"use client";

import { Sparkles, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Spinner } from "@/components/ui/Spinner";
import { useAskAssistant, useAssistantStatus } from "@/hooks/useAssistant";
import styles from "./AskArgusPanel.module.css";

/** ARGUS_PLAN.md Phase 10 — the one optional LLM surface in the whole
 * product. If Ollama isn't reachable, `available` stays false and this
 * component renders nothing at all; every other page is unaffected. */
export function AskArgusPanel() {
  const { data: status } = useAssistantStatus();
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const ask = useAskAssistant();

  useEffect(() => {
    if (!status?.available) return;
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "j") {
        e.preventDefault();
        setOpen((v) => !v);
      }
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [status?.available]);

  if (!status?.available || !open) return null;

  function handleAsk() {
    if (!question.trim()) return;
    ask.mutate(question.trim());
  }

  return (
    <div className={styles.overlay} onClick={() => setOpen(false)}>
      <div className={styles.panel} onClick={(e) => e.stopPropagation()}>
        <div className={styles.header}>
          <div className={styles.headerTitle}>
            <Sparkles size={16} color="var(--accent-primary)" />
            Ask ARGUS
          </div>
          <button type="button" className={styles.closeButton} onClick={() => setOpen(false)} aria-label="Close">
            <X size={16} />
          </button>
        </div>
        <div className={styles.body}>
          <p className={styles.hint}>
            Answers are grounded in current graph statistics via a local model — nothing leaves this machine.
          </p>
          <div className={styles.inputRow}>
            <input
              className={styles.input}
              placeholder="Which community has the most flagged transactions?"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleAsk()}
              autoFocus
            />
          </div>
          {ask.isPending && <Spinner size={20} />}
          {ask.data && <div className={styles.answer}>{ask.data.answer}</div>}
          {ask.isError && <div className={styles.answer}>{(ask.error as Error).message}</div>}
        </div>
      </div>
    </div>
  );
}
