/**
 * Mirrors backend/app/models/aggregate.py.
 *
 * A number arrives from the API with the population it describes and how it was
 * derived, so a surface cannot render a partial figure as though it were a
 * complete one. See the backend module for why this exists.
 */

export type AggregateBasis = "complete" | "sampled" | "truncated";

export interface Aggregate<T> {
  value: T;
  basis: AggregateBasis;
  population: number | null;
  examined: number | null;
  method: string;
  computed_at: string;
}

export function isPartial(agg: Aggregate<unknown>): boolean {
  return agg.basis !== "complete";
}

/** Fraction of the population examined, or null when unknowable. */
export function coverage(agg: Aggregate<unknown>): number | null {
  if (agg.population === null || agg.examined === null || agg.population === 0) return null;
  return Math.min(1, agg.examined / agg.population);
}

/**
 * Plain-language description of what the figure covers, for a tooltip or
 * caption. Returns null when the value is complete and the population is known,
 * because in that case the number needs no qualification.
 */
export function coverageNote(agg: Aggregate<unknown>): string | null {
  if (agg.basis === "complete") return null;

  const examined = agg.examined?.toLocaleString() ?? "some";
  const population = agg.population?.toLocaleString() ?? "an unknown number of";

  return agg.basis === "sampled"
    ? `Estimated from a random sample of ${examined} of ${population} records — figures will vary between refreshes.`
    : `Showing the first ${examined} of ${population} records, ordered by relevance — not a random sample.`;
}

/** Short suffix for inline display, e.g. "5 of 30". Null when complete. */
export function coverageLabel(agg: Aggregate<unknown>): string | null {
  if (agg.basis === "complete" || agg.examined === null || agg.population === null) return null;
  if (agg.examined >= agg.population) return null;
  return `${agg.examined.toLocaleString()} of ${agg.population.toLocaleString()}`;
}
