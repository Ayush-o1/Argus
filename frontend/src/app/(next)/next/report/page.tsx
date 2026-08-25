"use client";

import { CustodyRegister } from "@/components/next/report/CustodyRegister";

/**
 * Report mode (ARGUS_PLAN.md's redesign Phase 10): findings and custody,
 * built on the real export/custody shape. See CustodyRegister's module note
 * for why "Produce an export" and "Verify" are shown but not wired here.
 */
export default function NextReportPage() {
  return <CustodyRegister />;
}
