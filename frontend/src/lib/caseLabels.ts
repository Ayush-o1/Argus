import type { CaseSummary } from "@/lib/types";

/**
 * Display labels and tones for case status and priority.
 *
 * Centralised because the raw `UnderReview` enum leaked to the UI in three
 * separate places — the dashboard panel, the case list, and the case detail
 * header — each fixed independently or not at all. Rendered as "UNDERREVIEW"
 * next to a "Under review" filter chip, it reads as a different status rather
 * than a formatting slip.
 */

export const CASE_STATUS_LABEL: Record<CaseSummary["status"], string> = {
  Draft: "Draft",
  Open: "Open",
  UnderReview: "Under review",
  Closed: "Closed",
};

export const CASE_STATUS_TONE: Record<CaseSummary["status"], "neutral" | "accent" | "high" | "low" | "ok"> = {
  Draft: "neutral",
  Open: "accent",
  UnderReview: "high",
  Closed: "low",
};

export const CASE_PRIORITY_TONE: Record<CaseSummary["priority"], "critical" | "high" | "medium" | "low"> = {
  Critical: "critical",
  High: "high",
  Medium: "medium",
  Low: "low",
};

/** Ordered for pickers, so every surface offers the same sequence. */
export const CASE_STATUSES: CaseSummary["status"][] = ["Draft", "Open", "UnderReview", "Closed"];
export const CASE_PRIORITIES: CaseSummary["priority"][] = ["Low", "Medium", "High", "Critical"];
