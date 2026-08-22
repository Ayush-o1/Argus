"use client";

import { FlaskConical, Gauge, Search, TrendingUp } from "lucide-react";
import { useState } from "react";
import { PageShell } from "@/components/layout/PageShell";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Skeleton } from "@/components/ui/Skeleton";
import {
  useCalibration,
  useDrift,
  useFalseNegatives,
  useSimulate,
} from "@/hooks/useCalibration";
import { describeProportion, type Proportion } from "@/lib/calibration";
import styles from "./page.module.css";

type View = "rules" | "misses" | "drift" | "simulate";

/**
 * Whether ARGUS's detection is any good, measured from what analysts decided.
 *
 * Every figure on this page is a proportion shown with its counts and an exact
 * interval. That is the whole design: one confirmed investigation out of one is
 * a precision of 100% and an interval of 3%–100%, and a page that printed the
 * first without the second would be the false authority this system has spent
 * ten phases removing.
 */
export default function CalibrationPage() {
  const [view, setView] = useState<View>("rules");
  const { data, isLoading } = useCalibration();
  const { data: misses } = useFalseNegatives();
  const { data: drift } = useDrift();

  return (
    <PageShell
      title="Calibration"
      subtitle="What the feedback says about each rule — with the interval that says how much to believe it."
    >
      <SegmentedControl
        segments={[
          { value: "rules" as const, label: "Per rule", count: data?.rules.length ?? 0 },
          { value: "misses" as const, label: "Missed", count: misses?.total ?? 0 },
          { value: "drift" as const, label: "Drift", count: drift?.comparisons.length ?? 0 },
          { value: "simulate" as const, label: "Simulate" },
        ]}
        value={view}
        onChange={setView}
        ariaLabel="Calibration view"
        className={styles.tabs}
      />

      {view === "rules" ? (
        isLoading ? (
          <Skeleton height={320} />
        ) : !data ? null : (
          <>
            <Card className={styles.summaryCard}>
              <div className={styles.summaryRow}>
                <Figure label="Rule versions" value={String(data.summary.rules)} />
                <Figure
                  label="With any feedback"
                  value={`${data.summary.rules_with_any_feedback} of ${data.summary.rules}`}
                />
              </div>
              {/* Pooled, and labelled as pooled. Whichever rule fires most
                  dominates it, so it answers "how much feedback exists" and not
                  "how good is detection". */}
              <p className={styles.pooled}>
                Pooled outcome precision:{" "}
                <strong>{describeProportion(data.summary.outcome_precision_pooled)}</strong>
              </p>
              <p className={styles.note}>{data.summary.pooling_note}</p>
              <p className={styles.note}>{data.summary.coverage_note}</p>
            </Card>

            <div className={styles.list}>
              {data.rules.map((r) => (
                <Card key={`${r.rule_id}@${r.rule_version}`} className={styles.ruleCard}>
                  <div className={styles.ruleHead}>
                    <span className={styles.ruleId}>{r.rule_id}</span>
                    <Badge tone="neutral">v{r.rule_version}</Badge>
                    <span className={styles.counts}>
                      {r.alerts} alerts · {r.firings} firings · {r.still_open} still open
                    </span>
                    {!r.has_feedback ? (
                      <Badge tone="neutral">unmeasured</Badge>
                    ) : null}
                  </div>

                  <div className={styles.measures}>
                    <Measure
                      title="From investigation outcomes"
                      proportion={r.outcomes.precision}
                      note={r.outcomes.note}
                      extra={`${r.outcomes.confirmed} confirmed · ${r.outcomes.unfounded} unfounded · ${r.outcomes.did_not_settle} did not settle`}
                    />
                    <Measure
                      title="From triage"
                      proportion={r.triage.precision}
                      note={r.triage.note}
                      extra={
                        r.triage.dismissed === 0
                          ? "nothing dismissed"
                          : `${r.triage.dismissed} dismissed · ${r.triage.dismissed_as_wrong} as the rule being wrong`
                      }
                    />
                  </div>
                </Card>
              ))}
            </div>

            <p className={styles.method}>{data.method_note}</p>
          </>
        )
      ) : null}

      {view === "misses" ? (
        !misses ? (
          <Skeleton height={220} />
        ) : misses.total === 0 ? (
          <EmptyState
            icon={Search}
            title="No investigation has been opened without an alert"
            description={misses.note}
          />
        ) : (
          <Card className={styles.summaryCard}>
            <div className={styles.summaryRow}>
              <Figure label="Opened with no alert" value={String(misses.total)} />
              <Figure label="Of those, confirmed" value={String(misses.confirmed)} />
            </div>
            <p className={styles.note}>{misses.note}</p>
            <ul className={styles.missList}>
              {misses.investigations.map((i) => (
                <li key={i.investigation_id}>
                  <span className={styles.ruleId}>{i.inv_ref}</span> {i.title}
                  {i.outcome ? <Badge tone="neutral">{i.outcome}</Badge> : null}
                </li>
              ))}
            </ul>
          </Card>
        )
      ) : null}

      {view === "drift" ? (
        !drift ? (
          <Skeleton height={220} />
        ) : !drift.evaluable ? (
          <EmptyState icon={TrendingUp} title="Not enough runs to compare" description={drift.note} />
        ) : (
          <>
            {drift.comparisons.map((c) => (
              <Card key={`${c.earlier_run_id}-${c.later_run_id}`} className={styles.driftCard}>
                <div className={styles.ruleHead}>
                  <Badge tone={c.shifted ? "high" : "neutral"}>
                    {c.shifted ? "distribution moved" : "no detectable shift"}
                  </Badge>
                  {!c.same_model ? <Badge tone="neutral">different model</Badge> : null}
                </div>
                <p className={styles.describes}>{c.describes}</p>
              </Card>
            ))}
            <p className={styles.method}>{drift.comparisons[0]?.cannot_distinguish}</p>
          </>
        )
      ) : null}

      {view === "simulate" ? <Simulator /> : null}
    </PageShell>
  );
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.figure}>
      <b>{value}</b>
      <span>{label}</span>
    </div>
  );
}

/**
 * A proportion, never rendered as a bare percentage.
 *
 * When the interval is too wide to act on, the figure is greyed and the reason
 * is printed. It is not hidden: concealing a number a reader could compute
 * themselves would be its own dishonesty. It is qualified.
 */
function Measure({
  title,
  proportion,
  note,
  extra,
}: {
  title: string;
  proportion: Proportion;
  note: string;
  extra: string;
}) {
  const none = proportion.trials === 0;
  return (
    <div className={none ? styles.measureEmpty : styles.measure}>
      <span className={styles.measureTitle}>{title}</span>
      <span className={proportion.informative ? styles.value : styles.valueWeak}>
        {none ? "no outcomes yet" : describeProportion(proportion)}
      </span>
      <span className={styles.extra}>{extra}</span>
      {!none && !proportion.informative ? (
        <span className={styles.caveat}>
          Too few outcomes to distinguish a good rule from a bad one.
        </span>
      ) : null}
      <span className={styles.note}>{note}</span>
    </div>
  );
}

function Simulator() {
  const [minAssessed, setMinAssessed] = useState(2);
  const simulate = useSimulate();
  const result = simulate.data;

  return (
    <>
      <Card className={styles.summaryCard}>
        <div className={styles.ruleHead}>
          <FlaskConical size={16} aria-hidden />
          <span className={styles.measureTitle}>
            Replay every rule at a different threshold, against the findings they already ran on
          </span>
        </div>
        <div className={styles.simRow}>
          <label className={styles.simLabel} htmlFor="min-assessed">
            convergence.assessed_cluster — members required
          </label>
          <input
            id="min-assessed"
            type="number"
            min={1}
            max={20}
            value={minAssessed}
            onChange={(e) => setMinAssessed(Number(e.target.value))}
            className={styles.simInput}
          />
          <Button
            size="sm"
            onClick={() => simulate.mutate({ convergence_min_assessed: minAssessed })}
            disabled={simulate.isPending}
          >
            {simulate.isPending ? "Replaying…" : "Replay"}
          </Button>
        </div>
      </Card>

      {result ? (
        <Card className={styles.summaryCard}>
          <div className={styles.summaryRow}>
            <Figure label="Alerts now" value={String(result.current_total)} />
            <Figure label="Under the candidate" value={String(result.candidate_total)} />
            <Figure label="Would appear" value={String(result.added)} />
            <Figure label="Would disappear" value={String(result.removed)} />
          </div>

          {/* The count of removals is not the finding. Which ones are. */}
          {result.removed_with_confirmed_outcome.length > 0 ? (
            <p className={styles.warning}>
              <Gauge size={14} aria-hidden /> This change would remove{" "}
              {result.removed_with_confirmed_outcome.length} alert(s) that an investigation
              confirmed.
            </p>
          ) : result.removed > 0 ? (
            <p className={styles.note}>
              None of the alerts this would remove has a confirmed investigation behind it.
            </p>
          ) : null}

          {Object.keys(result.feedback_on_removed).length > 0 ? (
            <p className={styles.note}>
              Dismissal reasons on the removed alerts:{" "}
              {Object.entries(result.feedback_on_removed)
                .map(([k, v]) => `${v} ${k}`)
                .join(", ")}
            </p>
          ) : null}

          <p className={styles.note}>{result.read_the_removals_first}</p>
          <p className={styles.note}>{result.what_this_does_not_say}</p>
          <p className={styles.method}>{result.activation_note}</p>
        </Card>
      ) : null}
    </>
  );
}
