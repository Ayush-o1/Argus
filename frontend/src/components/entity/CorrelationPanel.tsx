"use client";

import { Network, Share2 } from "lucide-react";
import Link from "next/link";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { CardHeader } from "@/components/ui/CardHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { useSubjectCorrelation } from "@/hooks/useCorrelation";
import {
  FAMILY_LABEL,
  TIER_LABEL,
  TIER_TONE,
  dimensionState,
  formatCoverage,
  formatStrength,
} from "@/lib/correlation";
import styles from "./CorrelationPanel.module.css";

/**
 * What else ARGUS connects this subject to, and why.
 *
 * The panel renders three things a "related entities" list normally does not:
 *
 *   - the **reason** for every link, naming the measured quantity that produced
 *     it, rather than a similarity score with nothing behind it;
 *   - the **dimensions that could not be evaluated**, so a thin link is
 *     visibly thin rather than merely short;
 *   - **nothing at all** when nothing was found, said plainly. An empty result
 *     is a finding, and filling the space with the nearest few entities would
 *     manufacture connections to avoid an empty panel.
 */
export function CorrelationPanel({ subjectRef }: { subjectRef: string }) {
  const { data, isLoading, error } = useSubjectCorrelation(subjectRef);

  if (isLoading) {
    return (
      <Card>
        <CardHeader title="Connections" />
        <Skeleton height={120} />
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader title="Connections" />
        <p className={styles.note}>
          Correlations could not be loaded. This is a failure to read them, not a finding that
          there are none.
        </p>
      </Card>
    );
  }

  const links = data?.links ?? [];
  const clusters = data?.clusters ?? [];

  if (links.length === 0 && clusters.length === 0) {
    return (
      <Card>
        <CardHeader title="Connections" />
        <p className={styles.note}>
          <Network size={13} /> ARGUS found no correlation between this subject and any other
          finding. That is either because nothing connects them, or because no correlation run has
          covered this subject yet — the run status is on the correlation page.
        </p>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader
        title="Connections"
        subtitle={`${links.length} link${links.length === 1 ? "" : "s"} ARGUS derived from evidence`}
      />
      {clusters.map((cluster) => (
        <div key={cluster.cluster_id} className={styles.cluster}>
          <div className={styles.clusterHead}>
            <Badge tone="neutral">Group of {cluster.size}</Badge>
            <span className={styles.clusterFamilies}>
              {cluster.families.map((f) => FAMILY_LABEL[f] ?? f).join(" · ")}
            </span>
          </div>
          <p className={styles.clusterBasis}>{cluster.basis}</p>
        </div>
      ))}

      <ul className={styles.links}>
        {links.map((link) => {
          const other = link.ref_a === subjectRef ? link.ref_b : link.ref_a;
          const fired = link.dimensions.filter((d) => dimensionState(d) === "fired");
          const blind = link.dimensions.filter((d) => dimensionState(d) === "blind");
          return (
            <li key={link.link_id} className={styles.link}>
              <div className={styles.head}>
                <Badge tone={TIER_TONE[link.tier]} title={link.tier_meaning}>
                  {TIER_LABEL[link.tier]}
                </Badge>
                <Share2 size={12} className={styles.icon} />
                <Link href={`/entities/${encodeURIComponent(other)}`} className={styles.ref}>
                  {other}
                </Link>
                <span className={styles.strength}>
                  {formatStrength(link.strength)}
                  <span className={styles.coverage}>
                    {" "}
                    on {formatCoverage(link.coverage)} of dimensions
                  </span>
                </span>
              </div>
              {fired.map((dimension) => (
                <p key={dimension.dimension_id} className={styles.reason}>
                  {dimension.summary}
                </p>
              ))}
              {blind.length > 0 ? (
                <p className={styles.blind}>
                  {blind.length} dimension{blind.length === 1 ? "" : "s"} could not be evaluated,
                  so this is what was visible, not all there is.
                </p>
              ) : null}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
