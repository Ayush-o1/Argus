"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";
import { useAssessmentModel, useLatestEvaluation } from "@/hooks/useAssessment";
import { useSession } from "@/hooks/useAuth";
import { useDashboardSummary } from "@/hooks/useDashboard";
import { NEXT_MODE_PATH, useNextMode } from "@/lib/next/modeRouting";
import { useNextScopeStore, type NextMode } from "@/stores/nextScopeStore";
import { CommandBar } from "./CommandBar";
import { LeadsIncidentsPanel } from "./LeadsIncidentsPanel";
import { WorkingSetRail } from "./WorkingSetRail";
import styles from "./NextShell.module.css";

const MODES: { key: NextMode; label: string; hint: string }[] = [
  { key: "command", label: "COMMAND", hint: "Operational entry point" },
  { key: "investigate", label: "INVESTIGATE", hint: "Graph, map and timeline over one context" },
  { key: "evidence", label: "EVIDENCE", hint: "Provenance, reliability, contradiction" },
  { key: "triage", label: "TRIAGE", hint: "Alerts and investigations as queues" },
  { key: "report", label: "REPORT", hint: "Findings, custody, export" },
];

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts[parts.length - 1]?.[0] ?? "")).toUpperCase() || "?";
}

/**
 * The application shell — Phase 1/3. Renders `children` as-is: which mode
 * is "active" is a routing fact (`useNextMode`), not something this
 * component decides, so refresh/deep-link/back-forward all work for free.
 */
export function NextShell({ children }: { children: ReactNode }) {
  const mode = useNextMode();
  const setPaletteOpen = useNextScopeStore((s) => s.setPaletteOpen);
  const { data: session } = useSession();
  const [openSheet, setOpenSheet] = useState<"rail" | "panel" | null>(null);

  const { data: assessmentModel } = useAssessmentModel();
  const { data: evaluation } = useLatestEvaluation();

  const { data: summary } = useDashboardSummary();
  // Undefined either while the query is in flight, or permanently, when the
  // role lacks entity:read (the query is disabled, not failing) — either way
  // the header shows nothing rather than a fixture number standing in.
  const worldStat = summary ? (summary.total_persons + summary.total_organizations).toLocaleString("en-US") : null;

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <Link href={NEXT_MODE_PATH.command} className={styles.brand}>
          <span className={styles.brandDot} />
          <span className={styles.brandName}>ARGUS</span>
        </Link>

        <nav className={styles.modes} aria-label="Analytical modes">
          {MODES.map((m) => (
            <Link
              key={m.key}
              href={NEXT_MODE_PATH[m.key]}
              className={styles.modeButton}
              data-active={mode === m.key}
              aria-current={mode === m.key ? "page" : undefined}
              title={m.hint}
            >
              <span className={styles.modeDot} />
              {m.label}
            </Link>
          ))}
        </nav>

        <div className={styles.spacer} />

        <div className={styles.sheetToggles}>
          <button
            type="button"
            className={styles.sheetToggle}
            aria-expanded={openSheet === "rail"}
            aria-controls="next-working-set-sheet"
            onClick={() => setOpenSheet((s) => (s === "rail" ? null : "rail"))}
          >
            CONTEXT
          </button>
          <button
            type="button"
            className={styles.sheetToggle}
            aria-expanded={openSheet === "panel"}
            aria-controls="next-leads-sheet"
            onClick={() => setOpenSheet((s) => (s === "panel" ? null : "panel"))}
          >
            LEADS
          </button>
        </div>

        <button
          type="button"
          className={styles.commandTrigger}
          aria-haspopup="dialog"
          onClick={() => setPaletteOpen(true)}
        >
          <span className={styles.commandPrompt}>&gt;</span>
          <span className={styles.commandLabel}>Command — find, isolate, filter, explain</span>
          <span className={styles.kbd}>⌘K</span>
        </button>

        {worldStat ? <span className={styles.worldStat}>{worldStat} entities</span> : null}

        <span
          className={styles.syntheticBadge}
          title="Every entity, relationship and event in this instance is procedurally generated. No real individual or organization is represented."
        >
          <span className={styles.syntheticDot} />
          SYNTHETIC
        </span>

        {session ? <span className={styles.avatar}>{initials(session.user.display_name)}</span> : null}
      </header>

      <div className={styles.body}>
        <aside id="next-working-set-sheet" className={styles.sheet} data-open={openSheet === "rail"} aria-label="Working set">
          <WorkingSetRail />
        </aside>

        <main className={styles.main} data-screen-label={mode}>
          {children}
        </main>

        <aside id="next-leads-sheet" className={`${styles.sheet} ${styles.panelSheet}`} data-open={openSheet === "panel"} aria-label="Elevated leads">
          <LeadsIncidentsPanel />
        </aside>
      </div>

      <footer className={styles.footer}>
        {assessmentModel ? (
          <span>
            MODEL {assessmentModel.version} · fp {assessmentModel.short_fingerprint}
          </span>
        ) : null}
        {evaluation ? (
          <span>LAST EVALUATION {new Date(evaluation.generated_at).toISOString().slice(11, 16)} UTC</span>
        ) : null}
        {evaluation ? (
          <span>
            ELEVATED P {evaluation.report.elevated.precision?.toFixed(2) ?? "—"} / R {evaluation.report.elevated.recall?.toFixed(2) ?? "—"} vs
            ground truth it never read
          </span>
        ) : null}
        <span className={styles.spacer} />
        <span className={styles.footerRight}>SYNTHETIC INTELLIGENCE ENVIRONMENT</span>
      </footer>

      <CommandBar />
    </div>
  );
}
