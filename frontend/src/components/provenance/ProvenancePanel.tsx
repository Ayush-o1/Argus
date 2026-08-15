"use client";

import { Beaker, Clock, Database, FileText, Plus, Undo2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { useSession } from "@/hooks/useAuth";
import { useRetractAssertion, useSubjectProvenance } from "@/hooks/useProvenance";
import { cn } from "@/lib/cn";
import { describeValue, formatTimestamp, type Assertion } from "@/lib/provenance";
import { AssertionForm } from "./AssertionForm";
import { ConflictPanel } from "./ConflictPanel";
import { KindBadge, SyntheticBadge } from "./KindBadge";
import { RatingBadge, SourceReliabilityBadge } from "./RatingBadge";
import styles from "./provenance.module.css";

/**
 * Everything ARGUS can say about why it believes what it believes about one
 * entity — including at a past instant.
 *
 * The as-of control is the answer to "what did we know at the time", which is
 * the question a post-incident review starts with and which was previously
 * unanswerable: the graph held only the current value, so the record showed the
 * conclusion eventually reached and never the information actually available to
 * the person deciding.
 */
export function ProvenancePanel({ subjectRef }: { subjectRef: string }) {
  const [asOf, setAsOf] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  const { data: session } = useSession();
  const canAssert = session?.permissions.includes("assertion:write") ?? false;
  const canRetract = session?.permissions.includes("assertion:retract") ?? false;

  // Historical views are read-only. Offering a write control beside a
  // reconstruction of a past belief would invite recording a judgement against
  // a moment that has already passed.
  const historical = asOf !== null;
  const { data, isLoading } = useSubjectProvenance(subjectRef, asOf, !historical);
  const retract = useRetractAssertion(subjectRef);

  return (
    <div>
      <div className={styles.asOfBar}>
        <Clock size={15} color="var(--text-tertiary)" />
        <span className={styles.asOfLabel}>What ARGUS believed on</span>
        <input
          type="datetime-local"
          className={styles.asOfInput}
          value={asOf ?? ""}
          onChange={(e) => setAsOf(e.target.value || null)}
          aria-label="Reconstruct belief as at this date and time"
        />
        {historical ? (
          <>
            <Button variant="secondary" size="sm" onClick={() => setAsOf(null)}>
              Back to now
            </Button>
            <span className={styles.asOfActive}>
              Historical view — showing belief as at {formatTimestamp(asOf)}
            </span>
          </>
        ) : (
          <span className={styles.asOfActive} style={{ color: "var(--text-tertiary)" }}>
            Showing current belief
          </span>
        )}
      </div>

      {isLoading ? <Card>Loading provenance…</Card> : null}

      {data ? (
        <>
          {data.conflicts.length > 0 ? (
            <div className={styles.panelSection}>
              <div className={styles.panelTitle}>Conflicting claims</div>
              <ConflictPanel conflicts={data.conflicts} />
            </div>
          ) : null}

          <div className={styles.panelSection}>
            <div className={styles.panelTitle}>
              <FileText size={13} />
              Assertions ({data.assertions.length})
              {canAssert && !historical ? (
                <Button
                  variant="secondary"
                  size="sm"
                  style={{ marginLeft: "auto" }}
                  onClick={() => setShowForm((previous) => !previous)}
                >
                  <Plus size={13} /> {showForm ? "Cancel" : "Record an assessment"}
                </Button>
              ) : null}
            </div>

            {showForm && !historical ? (
              <Card style={{ marginBottom: "var(--space-4)" }}>
                <AssertionForm subjectRef={subjectRef} onDone={() => setShowForm(false)} />
              </Card>
            ) : null}

            {data.assertions.length === 0 ? (
              <EmptyState
                icon={FileText}
                title={historical ? "Nothing was believed at that moment" : "No assertions"}
                description={
                  historical
                    ? "ARGUS held no recorded belief about this entity at the instant you selected. That is the honest answer, not a gap in the display."
                    : "Nothing has been asserted about this entity beyond what its source reported."
                }
              />
            ) : (
              data.assertions.map((assertion) => (
                <AssertionRow
                  key={assertion.assertion_id}
                  assertion={assertion}
                  canRetract={canRetract && !historical}
                  onRetract={(reason) =>
                    retract.mutate({ assertionId: assertion.assertion_id, reason })
                  }
                />
              ))
            )}
          </div>

          <div className={styles.panelSection}>
            {/* Count and denominator together. A list showing 50 of 200 while
                labelled "Observations (50)" is the defect Phase 0 removed from
                the timeline; it does not get to reappear here. */}
            <div className={styles.panelTitle}>
              <Database size={13} />
              Observations ({data.observations.length}
              {data.observation_total > data.observations.length
                ? ` of ${data.observation_total}`
                : ""}
              )
            </div>
            {data.observations.length === 0 ? (
              <EmptyState
                icon={Database}
                title="No observations"
                description="No source has reported anything about this entity."
              />
            ) : (
              data.observations.map((observation) => (
                <div key={observation.observation_id} className={styles.assertionRow}>
                  <div className={styles.assertionTop}>
                    <span className={styles.assertionValue}>{observation.source_name}</span>
                    <SourceReliabilityBadge reliability={observation.source_reliability} />
                    {observation.source_is_synthetic ? <SyntheticBadge /> : null}
                    <span className={styles.assertionPredicate}>{observation.content_type}</span>
                  </div>
                  <div className={styles.assertionMeta}>
                    ARGUS learned this {formatTimestamp(observation.recorded_at)} · collected{" "}
                    {formatTimestamp(observation.collected_at)} · occurred{" "}
                    {formatTimestamp(observation.occurred_at)}
                    <br />
                    <span className={styles.mono}>
                      {Object.keys(observation.payload).length} field
                      {Object.keys(observation.payload).length === 1 ? "" : "s"} · sha256{" "}
                      {observation.content_hash.slice(0, 16)}…
                    </span>
                  </div>
                  {observation.provenance_note ? (
                    <p className={styles.assertionMeta}>{observation.provenance_note}</p>
                  ) : null}
                </div>
              ))
            )}
          </div>

          <div className={styles.panelSection}>
            <div className={styles.panelTitle}>
              <Beaker size={13} />
              Sources ({data.sources.length})
            </div>
            {data.sources.map((source) => (
              <div key={source.source_id} className={styles.sourceRow}>
                <span className={styles.sourceName}>{source.name}</span>
                <SourceReliabilityBadge reliability={source.reliability} />
                {source.is_synthetic ? <SyntheticBadge /> : null}
                <span className={styles.assertionPredicate}>{source.source_type}</span>
                <span className={styles.sourceBasis}>{source.reliability_basis}</span>
              </div>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}

function AssertionRow({
  assertion,
  canRetract,
  onRetract,
}: {
  assertion: Assertion;
  canRetract: boolean;
  onRetract: (reason: string) => void;
}) {
  const [retracting, setRetracting] = useState(false);
  const [reason, setReason] = useState("");
  const ended = assertion.retracted_at !== null || assertion.superseded_at !== null;

  return (
    <div className={cn(styles.assertionRow, ended && styles.assertionRetracted)}>
      <div className={styles.assertionTop}>
        <span className={styles.assertionPredicate}>{assertion.predicate}</span>
        <span className={styles.assertionValue}>{describeValue(assertion.object_value)}</span>
        <KindBadge kind={assertion.epistemic_kind} />
        <RatingBadge
          reliability={assertion.rating.reliability}
          credibility={assertion.rating.credibility}
        />
        {assertion.evidence.some((e) => e.source_is_synthetic) ? <SyntheticBadge /> : null}
      </div>

      <div className={styles.assertionMeta}>
        {assertion.method} · asserted by {assertion.asserted_by_display} ·{" "}
        {formatTimestamp(assertion.asserted_at)}
        {assertion.corroboration ? (
          <>
            <br />
            {/* "0 independent sources" is accurate but reads as a measurement
                when it is really an absence. An assertion with nothing linked
                to it is unevidenced, and saying so plainly is the point. */}
            {assertion.corroboration.independent_sources === 0 &&
            assertion.corroboration.contradicting_observations === 0 ? (
              "No evidence linked — this rests on the asserter's judgement alone."
            ) : (
              <>
                {assertion.corroboration.independent_sources} independent source
                {assertion.corroboration.independent_sources === 1 ? "" : "s"} supporting
                {assertion.corroboration.supporting_observations !==
                assertion.corroboration.independent_sources
                  ? ` (${assertion.corroboration.supporting_observations} observations, some sharing a source)`
                  : ""}
                {assertion.corroboration.contradicting_observations > 0
                  ? ` · ${assertion.corroboration.contradicting_observations} contradicting`
                  : ""}
              </>
            )}
          </>
        ) : null}
      </div>

      {assertion.note ? <p className={styles.assertionNote}>{assertion.note}</p> : null}

      {/* A withdrawn belief stays on screen, struck back rather than removed.
          An analyst who relied on it needs to be able to discover that they
          should not have — deleting it would take that away silently. */}
      {assertion.retracted_at ? (
        <div className={styles.retractionBanner}>
          <Undo2 size={13} />
          <span>
            Retracted {formatTimestamp(assertion.retracted_at)} by {assertion.retracted_by_display ?? assertion.retracted_by} —{" "}
            {assertion.retraction_reason}
          </span>
        </div>
      ) : null}
      {assertion.superseded_at ? (
        <div className={styles.assertionMeta}>
          Superseded {formatTimestamp(assertion.superseded_at)} by a later assertion.
        </div>
      ) : null}

      {canRetract && !ended ? (
        retracting ? (
          <div className={styles.formRow}>
            <input
              className={styles.input}
              style={{ flex: 1 }}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Why is this no longer believed? Required."
              maxLength={1000}
            />
            <Button
              size="sm"
              variant="secondary"
              disabled={!reason.trim()}
              onClick={() => {
                onRetract(reason.trim());
                setRetracting(false);
                setReason("");
              }}
            >
              Retract
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setRetracting(false)}>
              Cancel
            </Button>
          </div>
        ) : (
          <div>
            <Button size="sm" variant="ghost" onClick={() => setRetracting(true)}>
              <Undo2 size={13} /> Retract
            </Button>
          </div>
        )
      ) : null}
    </div>
  );
}
