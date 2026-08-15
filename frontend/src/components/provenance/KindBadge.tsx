import { Beaker, Brain, CircleHelp, Eye, PencilLine, Radio, UserCheck } from "lucide-react";
import { cn } from "@/lib/cn";
import { KIND_LABEL, KIND_MEANING, type AttributeKind } from "@/lib/provenance";
import styles from "./provenance.module.css";

/**
 * How ARGUS knows a value.
 *
 * Before this existed, an observation, a source's claim, an algorithm's
 * derivation and an analyst's judgement all rendered as identical text, and
 * nothing on screen distinguished them. This badge is the distinction, and it
 * appears wherever a value does.
 *
 * `unattributed` is styled as an absence — dashed, uncoloured — rather than
 * given a neutral tone that would let it pass as one more category. A value
 * nothing accounts for should look like one.
 */
const ICONS: Record<AttributeKind, typeof Eye> = {
  observed: Eye,
  reported: Radio,
  inferred: Brain,
  assessed: UserCheck,
  modified: PencilLine,
  unattributed: CircleHelp,
};

const CLASSES: Record<AttributeKind, string> = {
  observed: styles.kindObserved,
  reported: styles.kindReported,
  inferred: styles.kindInferred,
  assessed: styles.kindAssessed,
  modified: styles.kindModified,
  unattributed: styles.kindUnattributed,
};

export function KindBadge({ kind, className }: { kind: AttributeKind; className?: string }) {
  const Icon = ICONS[kind];
  return (
    <span className={cn(styles.kind, CLASSES[kind], className)} title={KIND_MEANING[kind]}>
      <Icon size={11} />
      {KIND_LABEL[kind]}
    </span>
  );
}

/**
 * Marks data that came from a source which fabricates its content.
 *
 * Driven by the source registry rather than hardcoded, so it appears wherever
 * synthetic data does and disappears on its own the moment a real source
 * replaces it. This is the structural answer to the audit's finding that
 * generated ground truth was indistinguishable from discovered intelligence.
 */
export function SyntheticBadge({ className }: { className?: string }) {
  return (
    <span
      className={cn(styles.syntheticFlag, className)}
      title={
        "This value came from a source that fabricates its content. It is not a report " +
        "about anything that happened, and nothing derived from it is evidence about the " +
        "real world."
      }
    >
      <Beaker size={11} />
      Synthetic
    </span>
  );
}
