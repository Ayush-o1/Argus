"use client";

import { EntityTypeIcon } from "@/components/entity/EntityTypeIcon";
import { useNextScopeStore } from "@/stores/nextScopeStore";
import { nextFixtureSubjects } from "@/lib/next/fixtures";
import styles from "./WorkingSetRail.module.css";

const DAY_FMT = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" });

function formatWindow(w: { start: number; end: number }): string {
  return `${DAY_FMT.format(w.start)} → ${DAY_FMT.format(w.end)}`;
}

/**
 * The persistent investigation context — Phase 3/4. Carried across Command,
 * Investigate, Evidence and Report by reading/writing `useNextScopeStore`
 * directly, so switching modes never resets what an analyst has scoped.
 */
export function WorkingSetRail() {
  const pins = useNextScopeStore((s) => s.pins);
  const togglePin = useNextScopeStore((s) => s.togglePin);
  const select = useNextScopeStore((s) => s.select);
  const region = useNextScopeStore((s) => s.region);
  const clearRegion = useNextScopeStore((s) => s.clearRegion);
  const timeWindow = useNextScopeStore((s) => s.timeWindow);
  const clearTimeWindow = useNextScopeStore((s) => s.clearTimeWindow);
  const hypothesis = useNextScopeStore((s) => s.hypothesis);
  const setHypothesis = useNextScopeStore((s) => s.setHypothesis);
  const clearWorkingSet = useNextScopeStore((s) => s.clearWorkingSet);

  const pinned = pins.map((id) => nextFixtureSubjects.find((s) => s.id === id)).filter((s): s is NonNullable<typeof s> => !!s);

  return (
    <>
      <div className={styles.head}>
        <span className={styles.title}>WORKING SET</span>
        <button type="button" className={styles.clear} onClick={clearWorkingSet}>
          CLEAR
        </button>
      </div>

      <div className={styles.scroll}>
        <div className={styles.section}>
          <div className={styles.sectionLabel}>SUBJECTS · PINNED</div>
          {pinned.map((s) => (
            <div key={s.id} className={styles.pinRow}>
              <EntityTypeIcon label={s.label} size={13} />
              <button type="button" className={styles.pinName} onClick={() => select(s.id)}>
                {s.name}
              </button>
              <button type="button" className={styles.pinRemove} title="Unpin" onClick={() => togglePin(s.id)}>
                ×
              </button>
            </div>
          ))}
          {pinned.length === 0 ? (
            <p className={styles.empty}>Nothing pinned. Pinning a subject carries it into every lens.</p>
          ) : null}
        </div>

        <div className={styles.section}>
          <div className={styles.sectionLabel}>TIME WINDOW</div>
          <div className={styles.scopeRow}>
            <span className={styles.scopeValue} data-active={!!timeWindow}>
              {timeWindow ? formatWindow(timeWindow) : "Full 90-day span"}
            </span>
            {timeWindow ? (
              <button type="button" className={styles.scopeClear} onClick={clearTimeWindow}>
                ×
              </button>
            ) : null}
          </div>
        </div>

        <div className={styles.section}>
          <div className={styles.sectionLabel}>GEOGRAPHY</div>
          <div className={styles.scopeRow}>
            <span className={styles.scopeValue} data-active={!!region}>
              {region ?? "World — all regions"}
            </span>
            {region ? (
              <button type="button" className={styles.scopeClear} onClick={clearRegion}>
                ×
              </button>
            ) : null}
          </div>
        </div>

        <div className={styles.section}>
          <div className={styles.sectionLabel}>HYPOTHESIS</div>
          <textarea
            className={styles.hypothesis}
            rows={3}
            value={hypothesis}
            onChange={(e) => setHypothesis(e.target.value)}
            placeholder="What do you think is happening, and what would change your mind?"
          />
        </div>

        <div className={styles.section}>
          <div className={styles.sectionLabel}>EVIDENCE COLLECTED</div>
          {/* Deliberately always 0 at this phase: EVIDENCE_LINK (linking a
              specific evidence item into the working set) is built in Phase 8
              alongside Evidence mode. Pinning a subject is not the same act as
              linking evidence, so this must not be derived from `pins` — that
              would show a plausible-looking number with no real basis. */}
          <div className={styles.evidenceCount}>
            <span className={styles.evidenceNumber}>0</span>
            <span className={styles.evidenceLabel}>items · nothing linked yet</span>
          </div>
        </div>
      </div>

      <div className={styles.footnote}>Carried across Command, Investigate, Evidence and Report. Changing lens does not change context.</div>
    </>
  );
}
