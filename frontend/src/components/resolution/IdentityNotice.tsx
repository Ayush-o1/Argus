"use client";

import { GitMerge, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useEntityResolution } from "@/hooks/useResolution";
import styles from "./IdentityNotice.module.css";

/**
 * Says, on the entity page, whether ARGUS believes this record is one of
 * several describing the same thing.
 *
 * It belongs here rather than only in the review queue because of what the
 * rest of the page shows: connection counts, timelines, related cases. If two
 * records have been merged, every one of those numbers describes a fraction of
 * what ARGUS knows about the entity — and an analyst reading "3 accounts" has
 * no way to tell that a second record holds four more. The count is not wrong;
 * it is answering a narrower question than the reader thinks they asked.
 *
 * A **contested** identity is worse and is styled as a warning: it means merges
 * have joined these records while other decisions say some of them are
 * different, and ARGUS has refused to pick a side. Anything aggregated across
 * the cluster is unsettled until a person resolves it.
 *
 * Renders nothing when the record stands alone, which is the common case.
 */
export function IdentityNotice({ entityRef }: { entityRef: string }) {
  const { data } = useEntityResolution(entityRef);
  const cluster = data?.cluster;
  if (!cluster) return null;

  const others = cluster.members.filter((member) => member !== entityRef);
  if (others.length === 0) return null;

  return (
    <div className={cluster.contested ? styles.contested : styles.notice}>
      {cluster.contested ? <TriangleAlert size={15} /> : <GitMerge size={15} />}
      <div className={styles.body}>
        {cluster.contested ? (
          <>
            <strong>This identity is contested.</strong>{" "}
            <span>
              {cluster.contested_reason} Counts, connections and timelines on this page describe
              this record alone, and cannot safely be combined with the others until that is
              settled.
            </span>
          </>
        ) : (
          <>
            <strong>
              ARGUS believes this is the same entity as {others.length} other{" "}
              {others.length === 1 ? "record" : "records"}.
            </strong>{" "}
            <span>
              Everything on this page — connections, activity, related cases — describes{" "}
              <em>this record only</em>.
            </span>
          </>
        )}
        <div className={styles.members}>
          {others.map((member) => (
            <Link key={member} href={`/entities/${member}`} className={styles.member}>
              {member}
            </Link>
          ))}
        </div>
        <div className={styles.canonical}>
          Representative record: <code>{cluster.canonical_ref}</code> —{" "}
          {/* "Canonical" is a choice, not a discovery, so how it was made is
              shown rather than presented as a property of the entity. */}
          {cluster.canonical_basis}.{" "}
          <Link href="/resolution" className={styles.link}>
            Review these decisions
          </Link>
        </div>
      </div>
    </div>
  );
}
