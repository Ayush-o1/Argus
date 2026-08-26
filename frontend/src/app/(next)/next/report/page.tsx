"use client";

import { CustodyRegister } from "@/components/next/report/CustodyRegister";

/**
 * Report mode (ARGUS_PLAN.md's redesign Phase 10): findings and custody,
 * built on the real export/custody shape and, since Phase 12, live-wired to
 * it — see CustodyRegister's module note.
 */
export default function NextReportPage() {
  return <CustodyRegister />;
}
