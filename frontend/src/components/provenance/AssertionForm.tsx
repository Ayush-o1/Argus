"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { useCreateAssertion } from "@/hooks/useProvenance";
import { ApiError } from "@/lib/api";
import {
  CREDIBILITY_MEANING,
  RELIABILITY_MEANING,
  type CredibilityCode,
  type ReliabilityCode,
} from "@/lib/provenance";
import styles from "./provenance.module.css";

/**
 * Record a judgement under your own name.
 *
 * Two constraints in the UI mirror two in the API, so the boundary is legible
 * rather than only enforced:
 *
 *   - Only `assessed` and `reported` are offered. A person cannot mark their
 *     own entry as `observed` — a system of record observed it, not the person
 *     typing — nor as `inferred`, which means an algorithm derived it and names
 *     the method. Offering the strongest-looking labels for hand application is
 *     how over-claiming gets designed in.
 *   - Both rating axes are required, and every option states its meaning in
 *     words. "Cannot be judged" is a first-class choice, not a fallback: an
 *     analyst who does not know should be able to say so without having to pick
 *     a middle value that implies a judgement they have not made.
 */
const RELIABILITIES: ReliabilityCode[] = ["A", "B", "C", "D", "E", "F"];
const CREDIBILITIES: CredibilityCode[] = ["1", "2", "3", "4", "5", "6"];

export function AssertionForm({
  subjectRef,
  predicate: initialPredicate,
  onDone,
}: {
  subjectRef: string;
  predicate?: string;
  onDone?: () => void;
}) {
  const [predicate, setPredicate] = useState(initialPredicate ?? "");
  const [value, setValue] = useState("");
  const [kind, setKind] = useState<"assessed" | "reported">("assessed");
  const [reliability, setReliability] = useState<ReliabilityCode>("F");
  const [credibility, setCredibility] = useState<CredibilityCode>("6");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const create = useCreateAssertion(subjectRef);

  const submit = async () => {
    setError(null);
    if (!predicate.trim() || !value.trim()) {
      setError("An assertion needs both a field and a value.");
      return;
    }
    try {
      await create.mutateAsync({
        subject_ref: subjectRef,
        predicate: predicate.trim(),
        object_value: value.trim(),
        epistemic_kind: kind,
        reliability,
        credibility,
        note: note.trim() || null,
      });
      setValue("");
      setNote("");
      onDone?.();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.isForbidden
            ? "Your role cannot record assertions."
            : (caught.detail ?? "Could not record the assertion.")
          : "Could not record the assertion.",
      );
    }
  };

  return (
    <div className={styles.form}>
      <div className={styles.formRow}>
        <label className={styles.formField}>
          <span className={styles.formLabel}>Field</span>
          <input
            className={styles.input}
            value={predicate}
            onChange={(e) => setPredicate(e.target.value)}
            placeholder="e.g. country"
            maxLength={120}
          />
        </label>
        <label className={styles.formField}>
          <span className={styles.formLabel}>Value</span>
          <input
            className={styles.input}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="e.g. Mexico"
          />
        </label>
      </div>

      <div className={styles.formRow}>
        <label className={styles.formField}>
          <span className={styles.formLabel}>Kind of claim</span>
          <select
            className={styles.select}
            value={kind}
            onChange={(e) => setKind(e.target.value as "assessed" | "reported")}
          >
            <option value="assessed">Assessed — my own judgement</option>
            <option value="reported">Reported — what a source claims</option>
          </select>
          <span className={styles.formHint}>
            &ldquo;Observed&rdquo; belongs to a system of record and &ldquo;inferred&rdquo; to an
            algorithm that names its method, so neither can be claimed by hand.
          </span>
        </label>
      </div>

      <div className={styles.formRow}>
        <label className={styles.formField}>
          <span className={styles.formLabel}>Source reliability</span>
          <select
            className={styles.select}
            value={reliability}
            onChange={(e) => setReliability(e.target.value as ReliabilityCode)}
          >
            {RELIABILITIES.map((code) => (
              <option key={code} value={code}>
                {code} — {RELIABILITY_MEANING[code]}
              </option>
            ))}
          </select>
        </label>
        <label className={styles.formField}>
          <span className={styles.formLabel}>Information credibility</span>
          <select
            className={styles.select}
            value={credibility}
            onChange={(e) => setCredibility(e.target.value as CredibilityCode)}
          >
            {CREDIBILITIES.map((code) => (
              <option key={code} value={code}>
                {code} — {CREDIBILITY_MEANING[code]}
              </option>
            ))}
          </select>
        </label>
      </div>
      <span className={styles.formHint}>
        These stay separate everywhere. Reliability describes the source, credibility describes
        this specific claim, and ARGUS never combines them into a single confidence figure.
      </span>

      <label className={styles.formField}>
        <span className={styles.formLabel}>Basis (optional)</span>
        <textarea
          className={styles.textarea}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Why you believe this. Whoever reads it next will weigh the reasoning, not the rating."
          maxLength={5000}
        />
      </label>

      {error ? <span className={styles.formError}>{error}</span> : null}

      <div className={styles.formActions}>
        <Button size="sm" onClick={submit} disabled={create.isPending}>
          {create.isPending ? "Recording…" : "Record assertion"}
        </Button>
        <span className={styles.formHint}>
          Attributed to you, permanently, and auditable.
        </span>
      </div>
    </div>
  );
}
