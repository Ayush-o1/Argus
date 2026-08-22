"use client";

import { Clock, GitBranch, Globe2, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { SelectControl } from "@/components/ui/SelectControl";
import { Skeleton } from "@/components/ui/Skeleton";
import { useAlert, useAlertModel, useTransitionAlert } from "@/hooks/useAlerts";
import { ApiError } from "@/lib/api";
import {
  PRIORITY_TONE,
  RULE_LABEL,
  STATE_LABEL,
  STATE_TONE,
  formatPriority,
  type AlertState,
} from "@/lib/alerts";
import { formatTimestamp } from "@/lib/provenance";
import styles from "./AlertDetail.module.css";

/**
 * One alert, everything that produced it, and everything anyone did to it.
 *
 * Three things are shown here that the previous alert panel could not show,
 * because the data did not exist:
 *
 *   - **the priority factors**, so a position in the queue is arguable rather
 *     than asserted — including the factor deliberately not computed;
 *   - **the occurrence history**, so "seen 5 times" resolves to which runs and
 *     when, rather than being a number to trust;
 *   - **the transition history**, which answers "who moved this, when, and from
 *     what" — the question the audit found structurally unanswerable.
 *
 * The state control offers only transitions that are legal from where the alert
 * currently is, because the server enforces the same graph and a control that
 * offers an illegal move is a control that produces an error.
 */
export function AlertDetail({ alertKey, onClose }: { alertKey: string; onClose: () => void }) {
  const { data: alert, isLoading } = useAlert(alertKey);
  const { data: model } = useAlertModel();
  const transition = useTransitionAlert();

  const [target, setTarget] = useState<AlertState | "">("");
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const allowed = alert && model ? (model.transitions[alert.state] ?? []) : [];
  const needsReason = target === "dismissed";

  async function submit() {
    if (!target) return;
    setError(null);
    try {
      await transition.mutateAsync({
        alertKey,
        to_state: target,
        reason_code: needsReason ? reason || null : null,
        note: note || null,
      });
      setTarget("");
      setReason("");
      setNote("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The change could not be saved.");
    }
  }

  const factors =
    alert && "factors" in (alert.priority_factors ?? {})
      ? (alert.priority_factors as Exclude<typeof alert.priority_factors, Record<string, never>>)
      : null;

  return (
    <Modal open onClose={onClose} title={alert?.title ?? "Alert"}>
      {isLoading || !alert ? (
        <Skeleton height={280} />
      ) : (
        <div className={styles.body}>
          <div className={styles.head}>
            <Badge tone={PRIORITY_TONE[alert.priority_band]}>
              {alert.priority_band} · {formatPriority(alert.priority)}
            </Badge>
            <Badge tone={STATE_TONE[alert.state]}>{STATE_LABEL[alert.state]}</Badge>
            <span className={styles.rule}>
              {RULE_LABEL[alert.rule_id] ?? alert.rule_id} v{alert.rule_version}
            </span>
          </div>

          <p className={styles.summary}>{alert.summary}</p>

          {alert.spread && alert.spread.country_count > 0 ? (
            <section className={styles.section}>
              <h3>
                <Globe2 size={13} /> Spread
              </h3>
              <p className={styles.spread}>
                {alert.spread.country_count === 1
                  ? alert.spread.countries[0]
                  : `${alert.spread.country_count} countries — ${alert.spread.countries.join(", ")}`}
                {alert.spread.region_count > 1
                  ? ` · crosses ${alert.spread.region_count} regions`
                  : null}
              </p>
              {/* The basis is stated because a missing country means "not
                  recorded", not "not abroad". */}
              {alert.spread.basis === "partial" ? (
                <p className={styles.partial}>
                  Computed over the {alert.spread.subjects_located} of{" "}
                  {alert.spread.subjects_total} subjects with a recorded location.
                </p>
              ) : null}
            </section>
          ) : null}

          <section className={styles.section}>
            {/* The heading counts every subject, and the list shows every one.
                The old panel counted a five-row preview and printed the preview
                length as the total (audit B-04). */}
            <h3>Subjects ({alert.scope.length})</h3>
            {alert.subjects && alert.subjects.length > 0 ? (
              <ul className={styles.subjects}>
                {alert.subjects.map((s) => (
                  <li key={s.subject_ref}>
                    <Link
                      href={`/entities/${encodeURIComponent(s.subject_ref)}`}
                      className={styles.ref}
                    >
                      {s.subject_ref}
                    </Link>
                    <span className={styles.subjectMeta}>
                      {s.subject_type ?? "unknown type"}
                      {s.band ? ` · ${s.band.replace(/_/g, " ")}` : " · not assessed"}
                      {s.country ? ` · ${s.country}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <div className={styles.scope}>
                {alert.scope.map((ref) => (
                  <Link key={ref} href={`/entities/${encodeURIComponent(ref)}`} className={styles.ref}>
                    {ref}
                  </Link>
                ))}
              </div>
            )}
          </section>

          {factors ? (
            <section className={styles.section}>
              <h3>Why it sits here in the queue</h3>
              <dl className={styles.factors}>
                <div><dt>Corroboration</dt><dd>{factors.factors.corroboration.toFixed(2)} ({factors.independent_methods} method{factors.independent_methods === 1 ? "" : "s"})</dd></div>
                <div><dt>Confidence</dt><dd>{factors.factors.confidence.toFixed(2)}</dd></div>
                <div><dt>Magnitude</dt><dd>{factors.factors.magnitude.toFixed(2)}</dd></div>
                <div><dt>Recency</dt><dd>{factors.factors.recency.toFixed(2)} ({Math.round(factors.evidence_age_days)}d old)</dd></div>
              </dl>
              <p className={styles.absent}>
                <ShieldAlert size={12} /> Asset criticality: {factors.asset_criticality_note}
              </p>
            </section>
          ) : null}

          {alert.occurrences && alert.occurrences.length > 0 ? (
            <section className={styles.section}>
              <h3>
                <Clock size={13} /> Seen {alert.occurrence_count}× — first{" "}
                {formatTimestamp(alert.first_seen_at)}
              </h3>
              <ul className={styles.occurrences}>
                {alert.occurrences.slice(0, 8).map((o) => (
                  <li key={o.occurrence_id}>
                    run {o.run_id} · priority {formatPriority(o.priority)} ·{" "}
                    {formatTimestamp(o.observed_at)}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {alert.transitions && alert.transitions.length > 0 ? (
            <section className={styles.section}>
              <h3>
                <GitBranch size={13} /> History
              </h3>
              <ul className={styles.history}>
                {alert.transitions.map((t) => (
                  <li key={t.transition_id}>
                    <span className={styles.move}>
                      {t.from_state ? `${STATE_LABEL[t.from_state]} → ` : ""}
                      {STATE_LABEL[t.to_state]}
                    </span>
                    <span className={styles.actor}>
                      {t.actor_username} ({t.actor_role}) · {formatTimestamp(t.occurred_at)}
                    </span>
                    {t.reason_code ? <span className={styles.reason}>{t.reason_code}</span> : null}
                    {t.note ? <span className={styles.note}>{t.note}</span> : null}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {allowed.length > 0 ? (
            <section className={styles.section}>
              <h3>Move this alert</h3>
              <div className={styles.controls}>
                <SelectControl
                  value={target}
                  onChange={(e) => setTarget(e.target.value as AlertState | "")}
                  options={[
                    { value: "", label: "Choose a state…" },
                    ...allowed.map((s) => ({ value: s, label: STATE_LABEL[s as AlertState] })),
                  ]}
                  aria-label="New state"
                />
                {needsReason ? (
                  <SelectControl
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    options={[
                      { value: "", label: "Reason (required)…" },
                      ...(model?.dismissal_reasons ?? []).map((r) => ({
                        value: r.code,
                        label: r.label,
                      })),
                    ]}
                    aria-label="Dismissal reason"
                  />
                ) : null}
                <input
                  className={styles.noteInput}
                  placeholder="Note (optional)"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  maxLength={2000}
                />
                <Button
                  size="sm"
                  onClick={submit}
                  disabled={!target || (needsReason && !reason) || transition.isPending}
                >
                  {transition.isPending ? "Saving…" : "Apply"}
                </Button>
              </div>
              {needsReason && model ? (
                <p className={styles.reasonHelp}>
                  {model.dismissal_reasons.find((r) => r.code === reason)?.means ??
                    "A dismissal needs a reason from the vocabulary, so dismissals can be counted and the rule tuned."}
                </p>
              ) : null}
              {error ? <p className={styles.error}>{error}</p> : null}
            </section>
          ) : null}
        </div>
      )}
    </Modal>
  );
}
