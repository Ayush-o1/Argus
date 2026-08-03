"use client";

import { AlertTriangle } from "lucide-react";
import { useEffect } from "react";
import { Button } from "@/components/ui/Button";
import { PageShell } from "@/components/layout/PageShell";

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <PageShell title="Something went wrong" subtitle="This page hit an unexpected error">
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: "var(--space-4)",
          padding: "var(--space-16) 0",
        }}
      >
        <AlertTriangle size={32} color="var(--risk-high)" />
        <p style={{ fontSize: "var(--text-sm)", color: "var(--text-tertiary)", maxWidth: 480, textAlign: "center" }}>
          {error.message || "An unexpected error occurred while rendering this page."}
        </p>
        <Button onClick={reset}>Try again</Button>
      </div>
    </PageShell>
  );
}
