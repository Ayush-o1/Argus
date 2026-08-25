"use client";

import { TriageQueues } from "@/components/next/triage/TriageQueues";

/**
 * Triage mode (ARGUS_PLAN.md's redesign Phase 9): Alerts and the
 * investigation queue as working queues, with Cases kept visibly separate.
 */
export default function NextTriagePage() {
  return <TriageQueues />;
}
