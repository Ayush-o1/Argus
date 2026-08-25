"use client";

import { usePathname } from "next/navigation";
import type { NextMode } from "@/stores/nextScopeStore";

/**
 * Mode lives in the URL, not in client state — Phase 18's acceptance
 * criteria explicitly test refresh, deep link and browser back/forward, none
 * of which work if "which mode am I in" is only a Zustand field. Everything
 * else about the working set (selection, pins, window, region, hypothesis)
 * stays in `useNextScopeStore`, because that context should survive a mode
 * switch — but the mode switch itself is real navigation.
 */
export const NEXT_MODE_PATH: Record<NextMode, string> = {
  command: "/next",
  investigate: "/next/investigate",
  evidence: "/next/evidence",
  triage: "/next/triage",
  report: "/next/report",
};

const PATH_MODE: Record<string, NextMode> = {
  "/next": "command",
  "/next/investigate": "investigate",
  "/next/evidence": "evidence",
  "/next/triage": "triage",
  "/next/report": "report",
};

export function useNextMode(): NextMode {
  const pathname = usePathname();
  return PATH_MODE[pathname] ?? "command";
}
