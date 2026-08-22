"use client";

import { AlertTriangle, EyeOff, Layers, Play, ShieldQuestion } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { PageShell } from "@/components/layout/PageShell";
import { AlertDetail } from "@/components/alerts/AlertDetail";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { CardHeader } from "@/components/ui/CardHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Skeleton } from "@/components/ui/Skeleton";
import { useSession } from "@/hooks/useAuth";
import {
  useAlertGroups,
  useAlertModel,
  useAlertSummary,
  useAlerts,
  useSuppressions,
} from "@/hooks/useAlerts";
import { apiFetch } from "@/lib/api";
import {
  PRIORITY_TONE,
  RULE_LABEL,
  SCOPE_PREVIEW,
  STATE_LABEL,
  STATE_TONE,
  formatPriority,
  type Alert,
} from "@/lib/alerts";
import { formatTimestamp } from "@/lib/provenance";
import styles from "./page.module.css";

type View = "queue" | "groups" | "suppressed" | "rules";

/**
 * The alert queue.
 *
 * What this page replaced is worth stating, because the change is not cosmetic.
 * It used to list `Incident` nodes of High or Critical severity. Those are
 * written by the scenario generator — one per storyline, describing the
 * storyline it had just planted — so the queue was the answer key, re-read and
 * presented as ARGUS's findings. Nothing generated an alert, nothing
 * deduplicated, and "review" was an unvalidated status write that left no
 * record of who had done it.
 *
 * Every row here is now something a named, versioned rule concluded from
 * ARGUS's own assessments and correlations, and the row says which rule, on
 * what evidence, and how many times it has fired.
 */
export default function AlertsPage() {
  const [view, setView] = useState<View>("queue");
  const [selected, setSelected] = useState<string | null>(null);
  const [groupFilter, setGroupFilter] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const { data: session } = useSession();
  const { data: summary } = useAlertSummary();
  const { data: model } = useAlertModel();
  const { data: groups, isLoading: groupsLoading } = useAlertGroups();
  const { data: suppressions } = useSuppressions(true);
  const { data: queue, isLoading } = useAlerts(
    view === "suppressed"
      ? { suppressed: true }
      : groupFilter
        ? { groupKey: groupFilter }
        : {},
  );

  const canRun = session?.permissions?.includes("alert:run") ?? false;
  const alerts = queue?.data ?? [];
  const counts = useMemo(() => summary?.counts ?? {}, [summary]);

  const segments = useMemo(
    () => [
      { value: "queue" as const, label: "Queue", count: counts.open ?? 0 },
      // The real total, not the number of rows this page received — a tab
      // labelled with its own page size is a preview presented as a count.
      { value: "groups" as const, label: "Groups", count: counts.groups ?? 0 },
      { value: "suppressed" as const, label: "Suppressed", count: counts.suppressed ?? 0 },
      { value: "rules" as const, label: "Rules", count: model?.rules.length ?? 0 },
    ],
    [counts, model],
  );

  async function runRules() {
    setRunning(true);
    try {
      await apiFetch("/api/alerts/run", { method: "POST", body: JSON.stringify({}) });
    } finally {
      setRunning(false);
    }
  }

  return (
    <PageShell
      title="Alerts"
      subtitle="Raised by ARGUS's own rules from its own findings — not from anything the data arrived labelled with."
      actions={
        canRun ? (
          <Button onClick={runRules} disabled={running} size="sm">
            <Play size={14} /> {running ? "Queued…" : "Run rules"}
          </Button>
        ) : null
      }
    >
      <div className={styles.stats}>
        <Stat label="Open" value={counts.open ?? 0} />
        <Stat label="Investigating" value={counts.investigating ?? 0} />
        <Stat label="Resolved" value={counts.resolved ?? 0} />
        <Stat label="Dismissed" value={counts.dismissed ?? 0} />
        <Stat label="Suppressed" value={counts.suppressed ?? 0} muted />
      </div>

      {(counts.suppressed ?? 0) > 0 ? (
        <p className={styles.suppressedNote}>
          <EyeOff size={13} /> {summary?.suppressed_note}
        </p>
      ) : null}

      <SegmentedControl
        segments={segments}
        value={view}
        onChange={(next) => {
          setView(next);
          if (next !== "queue") setGroupFilter(null);
        }}
        ariaLabel="Alert view"
        className={styles.tabs}
      />

      {groupFilter && view === "queue" ? (
        <p className={styles.filterNote}>
          Showing one group.{" "}
          <button className={styles.clearFilter} onClick={() => setGroupFilter(null)}>
            Show the whole queue
          </button>
        </p>
      ) : null}

      {view === "rules" ? (
        <RuleList model={model} />
      ) : view === "groups" ? (
        <GroupList
          groups={groups}
          loading={groupsLoading}
          onOpen={(key) => {
            setGroupFilter(key);
            setView("queue");
          }}
        />
      ) : (
        <QueueList
          alerts={alerts}
          loading={isLoading}
          suppressedView={view === "suppressed"}
          onSelect={setSelected}
        />
      )}

      {view === "suppressed" && suppressions && suppressions.length > 0 ? (
        <Card className={styles.suppressionCard}>
          <CardHeader
            title="Active suppressions"
            subtitle="Every one names who set it, why, and when it expires. None can be indefinite."
          />
          <ul className={styles.suppressionList}>
            {suppressions.map((s) => (
              <li key={s.suppression_id}>
                <strong>{s.rule_id ?? "any rule"}</strong>
                {s.subject_ref ? ` on ${s.subject_ref}` : ""} — {s.reason_code}, set by{" "}
                {s.created_by}, expires {formatTimestamp(s.expires_at)}
                <span className={styles.suppressionNote}>{s.note}</span>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      {selected ? (
        <AlertDetail alertKey={selected} onClose={() => setSelected(null)} />
      ) : null}
    </PageShell>
  );
}

function Stat({ label, value, muted }: { label: string; value: number; muted?: boolean }) {
  return (
    <div className={muted ? `${styles.stat} ${styles.statMuted}` : styles.stat}>
      <span className={styles.statValue}>{value}</span>
      <span className={styles.statLabel}>{label}</span>
    </div>
  );
}

function QueueList({
  alerts,
  loading,
  suppressedView,
  onSelect,
}: {
  alerts: Alert[];
  loading: boolean;
  suppressedView: boolean;
  onSelect: (key: string) => void;
}) {
  if (loading) return <Skeleton height={280} />;

  if (alerts.length === 0) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title={suppressedView ? "Nothing is suppressed" : "No open alerts"}
        description={
          suppressedView
            ? "No active suppression is hiding anything from the queue."
            : "Either no rule has fired, or no run has happened yet. Running the rules is the way to tell the difference — an empty queue is a finding, not a blank page."
        }
      />
    );
  }

  return (
    <ul className={styles.queue}>
      {alerts.map((alert) => (
        <li key={alert.alert_key}>
          <button className={styles.row} onClick={() => onSelect(alert.alert_key)}>
            <div className={styles.rowHead}>
              <Badge tone={PRIORITY_TONE[alert.priority_band]}>
                {alert.priority_band} · {formatPriority(alert.priority)}
              </Badge>
              <Badge tone={STATE_TONE[alert.state]}>{STATE_LABEL[alert.state]}</Badge>
              <span className={styles.rule}>
                {RULE_LABEL[alert.rule_id] ?? alert.rule_id}
              </span>
              {alert.occurrence_count > 1 ? (
                <span className={styles.occurrences} title="Times this rule has fired on this scope. A repeat increments this rather than creating a new alert.">
                  seen {alert.occurrence_count}×
                </span>
              ) : null}
              {alert.suppressed ? (
                <span className={styles.suppressedTag}>
                  <EyeOff size={11} /> suppressed
                </span>
              ) : null}
            </div>
            <p className={styles.title}>{alert.title}</p>
            <p className={styles.summary}>{alert.summary}</p>
            <div className={styles.scope}>
              {alert.scope.slice(0, SCOPE_PREVIEW).map((ref) => (
                <span key={ref} className={styles.ref}>
                  {ref}
                </span>
              ))}
              {alert.scope.length > SCOPE_PREVIEW ? (
                <span className={styles.more}>
                  +{alert.scope.length - SCOPE_PREVIEW} more of {alert.scope.length}
                </span>
              ) : null}
              <span className={styles.seen}>last seen {formatTimestamp(alert.last_seen_at)}</span>
            </div>
          </button>
        </li>
      ))}
    </ul>
  );
}

function GroupList({
  groups,
  loading,
  onOpen,
}: {
  groups: ReturnType<typeof useAlertGroups>["data"];
  loading: boolean;
  onOpen: (key: string) => void;
}) {
  if (loading) return <Skeleton height={240} />;
  if (!groups || groups.length === 0) {
    return (
      <EmptyState
        icon={Layers}
        title="No groups yet"
        description="Groups appear once the rules have run. A group is a correlated cluster ARGUS already published — not a similarity heuristic invented for this screen."
      />
    );
  }

  return (
    <ul className={styles.groups}>
      {groups.map((group) => (
        <li key={group.group_key} className={styles.group}>
          <button className={styles.groupOpen} onClick={() => onOpen(group.group_key)}>
            {group.alert_count === 1 ? "Open this alert" : `Open these ${group.alert_count} alerts`} →
          </button>
          <div className={styles.groupHead}>
            <Badge tone="accent">
              {group.alert_count} {group.alert_count === 1 ? "alert" : "alerts"}
            </Badge>
            {group.open_count > 0 ? <Badge tone="high">{group.open_count} open</Badge> : null}
            {group.top_priority !== null ? (
              <span className={styles.groupPriority}>
                top priority {formatPriority(group.top_priority)}
              </span>
            ) : null}
          </div>
          <p className={styles.groupSummary}>{group.summary}</p>
          <div className={styles.scope}>
            {group.subjects.slice(0, SCOPE_PREVIEW).map((ref) => (
              <Link key={ref} href={`/entities/${encodeURIComponent(ref)}`} className={styles.ref}>
                {ref}
              </Link>
            ))}
            {group.subjects.length > SCOPE_PREVIEW ? (
              <span className={styles.more}>
                +{group.subjects.length - SCOPE_PREVIEW} more of {group.subjects.length}
              </span>
            ) : null}
          </div>
          <div className={styles.groupRules}>
            {group.rule_ids.map((r) => (
              <span key={r} className={styles.rulePill}>
                {RULE_LABEL[r] ?? r}
              </span>
            ))}
          </div>
        </li>
      ))}
    </ul>
  );
}

function RuleList({ model }: { model: ReturnType<typeof useAlertModel>["data"] }) {
  if (!model) return <Skeleton height={240} />;
  return (
    <div className={styles.rules}>
      <p className={styles.priorityNote}>
        <ShieldQuestion size={13} /> {model.priority_note}
      </p>
      {model.rules.map((rule) => (
        <Card key={`${rule.rule_id}@${rule.version}`} className={styles.ruleCard}>
          <CardHeader
            title={rule.title}
            subtitle={`${rule.rule_id} · v${rule.version} · ${rule.independent_methods} independent method${rule.independent_methods === 1 ? "" : "s"}`}
          />
          <p className={styles.ruleMeans}>{rule.means}</p>
          <p className={styles.ruleWrong}>
            <strong>Would be wrong if:</strong> {rule.would_be_wrong_if}
          </p>
          <details className={styles.reads}>
            <summary>Reads {rule.reads.length} inputs</summary>
            <ul>
              {rule.reads.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </details>
        </Card>
      ))}
      <p className={styles.fingerprint}>Rule set fingerprint: {model.rules_fingerprint.slice(0, 16)}…</p>
    </div>
  );
}
