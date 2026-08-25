"use client";

import { Beaker, Database, FileText } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ConflictPanel } from "@/components/provenance/ConflictPanel";
import { KindBadge, SyntheticBadge } from "@/components/provenance/KindBadge";
import { RatingBadge, SourceReliabilityBadge } from "@/components/provenance/RatingBadge";
import { describeValue, formatTimestamp, type Assertion, type SubjectProvenance } from "@/lib/provenance";
import styles from "@/components/provenance/provenance.module.css";

/**
 * Everything ARGUS can say about why it believes what it believes about the
 * selected subject — the real provenance vocabulary (observations,
 * assertions, conflicts, Admiralty ratings), fed fixture data typed against
 * `SubjectProvenance` instead of `useSubjectProvenance()`'s live fetch.
 *
 * Deliberately read-only, unlike `ProvenancePanel` (the live version this is
 * modelled on): recording or retracting an assertion is a real, permission-
 * gated write against a real subject in Postgres, and these fixture subject
 * ids have no row to write against. Wiring `AssertionForm`/retraction and the
 * "what did ARGUS believe as of a past instant" reconstruction back in is
 * Phase 12 work, alongside every other fixture-to-live swap.
 */
export function EvidenceLedger({ provenance }: { provenance: SubjectProvenance | null }) {
  if (!provenance) {
    return (
      <EmptyState
        icon={FileText}
        title="No subject selected"
        description="Select a subject from Command or Investigate to see what ARGUS can say about why it believes what it believes."
      />
    );
  }

  return (
    <div>
      {provenance.conflicts.length > 0 ? (
        <div className={styles.panelSection}>
          <div className={styles.panelTitle}>Conflicting claims</div>
          <ConflictPanel conflicts={provenance.conflicts} />
        </div>
      ) : null}

      <div className={styles.panelSection}>
        <div className={styles.panelTitle}>
          <FileText size={13} />
          Assertions ({provenance.assertions.length})
        </div>
        {provenance.assertions.length === 0 ? (
          <EmptyState
            icon={FileText}
            title="No assertions"
            description="Nothing has been asserted about this entity beyond what its source reported."
          />
        ) : (
          provenance.assertions.map((assertion) => <AssertionRow key={assertion.assertion_id} assertion={assertion} />)
        )}
      </div>

      <div className={styles.panelSection}>
        <div className={styles.panelTitle}>
          <Database size={13} />
          Observations ({provenance.observations.length}
          {provenance.observation_total > provenance.observations.length ? ` of ${provenance.observation_total}` : ""})
        </div>
        {provenance.observations.length === 0 ? (
          <EmptyState icon={Database} title="No observations" description="No source has reported anything about this entity." />
        ) : (
          provenance.observations.map((observation) => (
            <div key={observation.observation_id} className={styles.assertionRow}>
              <div className={styles.assertionTop}>
                <span className={styles.assertionValue}>{observation.source_name}</span>
                <SourceReliabilityBadge reliability={observation.source_reliability} />
                {observation.source_is_synthetic ? <SyntheticBadge /> : null}
                <span className={styles.assertionPredicate}>{observation.content_type}</span>
              </div>
              <div className={styles.assertionMeta}>
                ARGUS learned this {formatTimestamp(observation.recorded_at)} · collected {formatTimestamp(observation.collected_at)} ·
                occurred {formatTimestamp(observation.occurred_at)}
                <br />
                <span className={styles.mono}>
                  {Object.keys(observation.payload).length} field{Object.keys(observation.payload).length === 1 ? "" : "s"} · sha256{" "}
                  {observation.content_hash.slice(0, 16)}…
                </span>
              </div>
              {observation.provenance_note ? <p className={styles.assertionMeta}>{observation.provenance_note}</p> : null}
            </div>
          ))
        )}
      </div>

      <div className={styles.panelSection}>
        <div className={styles.panelTitle}>
          <Beaker size={13} />
          Sources ({provenance.sources.length})
        </div>
        {provenance.sources.map((source) => (
          <div key={source.source_id} className={styles.sourceRow}>
            <span className={styles.sourceName}>{source.name}</span>
            <SourceReliabilityBadge reliability={source.reliability} />
            {source.is_synthetic ? <SyntheticBadge /> : null}
            <span className={styles.assertionPredicate}>{source.source_type}</span>
            <span className={styles.sourceBasis}>{source.reliability_basis}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function AssertionRow({ assertion }: { assertion: Assertion }) {
  const ended = assertion.retracted_at !== null || assertion.superseded_at !== null;

  return (
    <Card className={ended ? styles.assertionRetracted : undefined} style={{ marginBottom: "var(--space-2)" }}>
      <div className={styles.assertionTop}>
        <span className={styles.assertionPredicate}>{assertion.predicate}</span>
        <span className={styles.assertionValue}>{describeValue(assertion.object_value)}</span>
        <KindBadge kind={assertion.epistemic_kind} />
        <RatingBadge reliability={assertion.rating.reliability} credibility={assertion.rating.credibility} />
        {assertion.evidence.some((e) => e.source_is_synthetic) ? <SyntheticBadge /> : null}
      </div>

      <div className={styles.assertionMeta}>
        {assertion.method} · asserted by {assertion.asserted_by_display} · {formatTimestamp(assertion.asserted_at)}
        {assertion.corroboration ? (
          <>
            <br />
            {assertion.corroboration.independent_sources === 0 && assertion.corroboration.contradicting_observations === 0 ? (
              "No evidence linked — this rests on the asserter's judgement alone."
            ) : (
              <>
                {assertion.corroboration.independent_sources} independent source{assertion.corroboration.independent_sources === 1 ? "" : "s"}{" "}
                supporting
                {assertion.corroboration.contradicting_observations > 0 ? ` · ${assertion.corroboration.contradicting_observations} contradicting` : ""}
              </>
            )}
          </>
        ) : null}
      </div>

      {assertion.note ? <p className={styles.assertionNote}>{assertion.note}</p> : null}
    </Card>
  );
}
