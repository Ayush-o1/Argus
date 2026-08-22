"use client";

import { Activity, Globe2, HelpCircle, MapPin, TrendingUp } from "lucide-react";
import { useState } from "react";
import { PageShell } from "@/components/layout/PageShell";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { CardHeader } from "@/components/ui/CardHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Skeleton } from "@/components/ui/Skeleton";
import {
  usePatternModel,
  useSpatialPatterns,
  useTemporalPatterns,
} from "@/hooks/usePatterns";
import {
  LANE_LABEL,
  formatP,
  formatRatio,
  type SeriesAnalysis,
  type SpatialAnalysis,
} from "@/lib/patterns";
import styles from "./page.module.css";

type View = "temporal" | "spatial" | "method";

/**
 * What changed, and where things are concentrated.
 *
 * Both questions were previously unanswerable. The only statistical claim in
 * the product was the timeline's "N days above 2σ of flagged volume", which had
 * no null hypothesis and a threshold inflated by the very bursts it looked for;
 * and "hotspots" were `GROUP BY region`, which cannot see a concentration that
 * straddles a border and ranks the largest region top for being largest.
 *
 * Every panel here states the test it used, the window it measured, and the
 * conditions under which it declines to answer.
 */
export default function PatternsPage() {
  const [view, setView] = useState<View>("temporal");
  const { data: temporal, isLoading: temporalLoading } = useTemporalPatterns();
  const { data: spatial, isLoading: spatialLoading } = useSpatialPatterns();
  const { data: model } = usePatternModel();

  return (
    <PageShell
      title="Patterns"
      subtitle="What changed over time, and where activity concentrates — each with the test behind it."
    >
      <SegmentedControl
        segments={[
          { value: "temporal" as const, label: "Over time", count: temporal?.series.length ?? 0 },
          { value: "spatial" as const, label: "Across space", count: spatial?.clusters.count ?? 0 },
          { value: "method" as const, label: "Method", count: model?.tests.length ?? 0 },
        ]}
        value={view}
        onChange={setView}
        ariaLabel="Pattern view"
        className={styles.tabs}
      />

      {view === "temporal" ? (
        temporalLoading ? (
          <Skeleton height={340} />
        ) : !temporal?.evaluable ? (
          <EmptyState
            icon={Activity}
            title="Nothing to analyse"
            description={temporal?.reason ?? "The graph holds no timestamped activity."}
          />
        ) : (
          <>
            <p className={styles.windowNote}>
              Window <strong>{temporal.window.from}</strong> to <strong>{temporal.window.to}</strong>{" "}
              ({temporal.window.days} days), against a baseline of{" "}
              <strong>{temporal.baseline.days} days</strong> ending {temporal.baseline.to}.
            </p>
            <p className={styles.anchorNote}>{temporal.anchor_note}</p>
            {temporal.series.map((series) => (
              <SeriesCard key={series.lane} series={series} />
            ))}
          </>
        )
      ) : view === "spatial" ? (
        spatialLoading ? (
          <Skeleton height={340} />
        ) : !spatial ? (
          <EmptyState icon={MapPin} title="No spatial data" description="No entity carries coordinates." />
        ) : (
          <SpatialView data={spatial} />
        )
      ) : (
        <MethodView model={model} />
      )}
    </PageShell>
  );
}

function SeriesCard({ series }: { series: SeriesAnalysis }) {
  const { change, trend, seasonality, changepoint } = series;
  const tone = !change.evaluable
    ? "neutral"
    : change.direction === "increase"
      ? "critical"
      : change.direction === "decrease"
        ? "accent"
        : "neutral";

  return (
    <Card className={styles.card}>
      <CardHeader
        title={LANE_LABEL[series.lane] ?? series.lane}
        subtitle={change.test}
      />

      <div className={styles.headline}>
        <Badge tone={tone}>
          {!change.evaluable ? "not evaluable" : change.direction}
        </Badge>
        {change.evaluable ? (
          <span className={styles.figures}>
            rate ratio <strong>{formatRatio(change.rate_ratio)}</strong>
            {" · "}95% CI {formatRatio(change.confidence_interval.low)}–
            {change.confidence_interval.high === null ? "∞" : formatRatio(change.confidence_interval.high)}
            {" · "}{formatP(change.p_value)}
          </span>
        ) : null}
      </div>
      <p className={styles.summary}>{change.summary}</p>

      <div className={styles.grid}>
        <Finding label="Trend" evaluable={trend.evaluable} significant={trend.significant} text={trend.summary} />
        <Finding
          label="Weekly rhythm"
          evaluable={seasonality.evaluable}
          significant={seasonality.significant}
          text={seasonality.summary}
        />
        <Finding
          label="Change of course"
          evaluable={changepoint.evaluable}
          significant={changepoint.significant}
          text={
            !changepoint.evaluable
              ? changepoint.reason ?? "Not enough data."
              : changepoint.significant
                ? `The series divides at day ${changepoint.index}: ${changepoint.before_mean?.toFixed(1)} per day before, ${changepoint.after_mean?.toFixed(1)} after (${formatP(changepoint.p_value)}). ${changepoint.note}`
                : `No significant division in the series (${formatP(changepoint.p_value)}).`
          }
        />
        <Finding
          label="Unusual days"
          evaluable
          significant={series.unusual_days > 0}
          text={
            series.unusual_days === 0
              ? "No day departs significantly from the rest of the series."
              : `${series.unusual_days} of ${series.daily.length} days depart from the rate the rest of the series implies.`
          }
        />
      </div>

      <Sparkline series={series} />
      <p className={styles.method}>{series.unusual_note}</p>
    </Card>
  );
}

function Finding({
  label,
  evaluable,
  significant,
  text,
}: {
  label: string;
  evaluable: boolean;
  significant: boolean;
  text: string;
}) {
  return (
    <div className={styles.finding}>
      <div className={styles.findingHead}>
        <span className={styles.findingLabel}>{label}</span>
        <Badge tone={!evaluable ? "neutral" : significant ? "high" : "low"}>
          {!evaluable ? "not evaluable" : significant ? "significant" : "no finding"}
        </Badge>
      </div>
      <p className={styles.findingText}>{text}</p>
    </div>
  );
}

/** Daily counts, with the days the server tested as unusual marked. */
function Sparkline({ series }: { series: SeriesAnalysis }) {
  const max = Math.max(1, ...series.daily.map((d) => d.count));
  return (
    <div className={styles.spark} role="img" aria-label={`Daily ${series.lane} volume`}>
      {series.daily.map((d) => (
        <span
          key={d.day}
          className={[
            styles.bar,
            d.in_window ? styles.barWindow : "",
            d.unusual ? (d.unusual_direction === "high" ? styles.barHigh : styles.barLow) : "",
          ]
            .filter(Boolean)
            .join(" ")}
          style={{ height: `${Math.max(2, (d.count / max) * 100)}%` }}
          title={`${d.day}: ${d.count}${
            d.unusual ? ` — unusual (${d.unusual_direction}, expected ${d.expected?.toFixed(1)})` : ""
          }`}
        />
      ))}
    </div>
  );
}

function SpatialView({ data }: { data: SpatialAnalysis }) {
  const { clusters, hotspots } = data;
  return (
    <>
      <Card className={styles.card}>
        <CardHeader
          title="Concentrations"
          subtitle={`${clusters.method} · ${clusters.eps_km} km radius, minimum ${clusters.min_samples} members`}
        />
        <p className={styles.summary}>
          <strong>{clusters.count}</strong> concentrations across{" "}
          <strong>{clusters.located_total.toLocaleString()}</strong> located entities.
        </p>
        <p className={styles.method}>{clusters.note}</p>
        <ul className={styles.clusters}>
          {clusters.found.slice(0, 12).map((c) => (
            <li key={c.cluster_id} className={styles.cluster}>
              <div className={styles.clusterHead}>
                <Badge tone="accent">{c.size} entities</Badge>
                {c.crosses_border ? (
                  <Badge tone="high" title="A concentration that GROUP BY country cannot see">
                    crosses {c.countries.length} borders
                  </Badge>
                ) : null}
                {c.elevated > 0 ? <Badge tone="critical">{c.elevated} elevated</Badge> : null}
              </div>
              <p className={styles.clusterBody}>
                {c.countries.join(", ") || "location unknown"} · centre {c.lat.toFixed(2)},{" "}
                {c.lng.toFixed(2)} · radius {c.radius_km.toFixed(0)} km
              </p>
            </li>
          ))}
        </ul>
      </Card>

      <Card className={styles.card}>
        <CardHeader title="Hotspots" subtitle={hotspots.test} />
        {!hotspots.evaluable ? (
          <p className={styles.summary}>{hotspots.reason}</p>
        ) : (
          <>
            <p className={styles.summary}>
              Tested {hotspots.locations_tested} locations at a {hotspots.band_km} km neighbourhood.{" "}
              <strong>{hotspots.significant_before_correction}</strong> pass on their own p-value;{" "}
              <strong>{hotspots.significant_after_correction}</strong> survive correction for
              testing them all.
            </p>
            {hotspots.hot.length === 0 && hotspots.cold.length === 0 ? (
              <p className={styles.method}>
                No location concentrates more than the map is dense there anyway.
              </p>
            ) : (
              <ul className={styles.hotspots}>
                {[...hotspots.hot, ...hotspots.cold].map((h) => (
                  <li key={h.key} className={styles.hotspot}>
                    <Badge tone={h.kind === "hot" ? "critical" : "accent"}>{h.kind}</Badge>
                    <span className={styles.hotspotKey}>{h.key}</span>
                    <span className={styles.hotspotFigures}>
                      z = {h.z_score.toFixed(2)} · {formatP(h.p_value)} · {h.value.toFixed(0)} of{" "}
                      {h.entity_count?.toLocaleString() ?? "—"} entities
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <p className={styles.caveat}>
              <HelpCircle size={12} /> {hotspots.caveat}
            </p>
          </>
        )}
      </Card>

      <p className={styles.anchorNote}>
        <Globe2 size={12} /> {data.postgis_note}
      </p>
    </>
  );
}

function MethodView({ model }: { model: ReturnType<typeof usePatternModel>["data"] }) {
  if (!model) return <Skeleton height={280} />;
  return (
    <div className={styles.methods}>
      {model.tests.map((t) => (
        <Card key={t.question} className={styles.card}>
          <CardHeader title={t.question} subtitle={t.test} />
          <p className={styles.summary}>{t.why}</p>
          <p className={styles.method}>
            <strong>Returns:</strong> {t.returns}
          </p>
          <p className={styles.method}>
            <strong>Declines when:</strong> {t.declines_when}
          </p>
          {t.caveat ? (
            <p className={styles.caveat}>
              <HelpCircle size={12} /> {t.caveat}
            </p>
          ) : null}
        </Card>
      ))}
      {model.not_implemented.map((n) => (
        <Card key={n.item} className={styles.card}>
          <CardHeader title={`Not implemented: ${n.item}`} subtitle="and the reason why" />
          <p className={styles.summary}>{n.reason}</p>
        </Card>
      ))}
      <p className={styles.anchorNote}>
        <TrendingUp size={12} /> Every test above reports at alpha {model.alpha}, and every one that
        runs over many series or many locations is corrected for that before anything is called
        significant.
      </p>
    </div>
  );
}
