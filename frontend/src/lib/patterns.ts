/**
 * Types for the temporal and spatial statistics.
 *
 * Every result carries the window and baseline it was measured against, and
 * every one can decline to answer. Both are load-bearing: the statistic this
 * replaced — "N days above 2σ of flagged volume" — was uncheckable precisely
 * because it never said what it compared against, and it never declined.
 */

export interface RateChange {
  recent: { count: number; days: number; rate_per_day: number | null; from: string | null; to: string | null };
  baseline: { count: number; days: number; rate_per_day: number | null; from: string | null; to: string | null };
  rate_ratio: number | null;
  confidence_interval: { low: number | null; high: number | null; level: number };
  p_value: number | null;
  alpha: number;
  evaluable: boolean;
  significant: boolean;
  direction: "increase" | "decrease" | "unchanged" | "unknown";
  test: string;
  summary: string;
}

export interface TrendResult {
  points: number;
  statistic: number | null;
  z_score: number | null;
  p_value: number | null;
  slope_per_day: number | null;
  slope_per_week: number | null;
  evaluable: boolean;
  significant: boolean;
  direction: "rising" | "falling" | "flat";
  test: string;
  summary: string;
}

export interface ChangepointResult {
  index: number | null;
  p_value: number | null;
  before_mean: number | null;
  after_mean: number | null;
  evaluable: boolean;
  significant: boolean;
  test: string;
  note: string;
  reason: string | null;
}

export interface SeasonalityResult {
  p_value: number | null;
  statistic: number | null;
  busiest_day: string | null;
  quietest_day: string | null;
  per_day: Record<string, number>;
  evaluable: boolean;
  significant: boolean;
  test: string;
  summary: string;
}

export interface DailyPoint {
  day: string;
  count: number;
  elevated: number;
  in_window: boolean;
  unusual: boolean;
  unusual_direction: "high" | "low" | null;
  expected: number | null;
  p_value: number | null;
}

export interface SeriesAnalysis {
  lane: string;
  change: RateChange;
  trend: TrendResult;
  changepoint: ChangepointResult;
  seasonality: SeasonalityResult;
  daily: DailyPoint[];
  unusual_days: number;
  unusual_note: string;
}

export interface TemporalAnalysis {
  evaluable: boolean;
  reason?: string;
  window: { days: number; from: string; to: string };
  baseline: { days: number; from: string; to: string };
  anchored_to: string;
  anchor_note: string;
  series: SeriesAnalysis[];
  computed_at: string;
}

export interface SpatialCluster {
  cluster_id: number;
  size: number;
  lat: number;
  lng: number;
  radius_km: number;
  mean_distance_km: number;
  density_per_1000km2: number;
  countries: string[];
  crosses_border: boolean;
  elevated: number;
  assessed: number;
  members: string[];
  members_total: number;
}

export interface HotspotLocation {
  key: string;
  lat: number;
  lng: number;
  value: number;
  neighbours: number;
  z_score: number;
  p_value: number;
  significant_raw: boolean;
  significant: boolean;
  kind: "hot" | "cold" | "none";
  region: string | null;
  entity_count: number | null;
  elevated_count: number | null;
  assessed_count: number | null;
}

export interface SpatialAnalysis {
  clusters: {
    found: SpatialCluster[];
    count: number;
    noise: number;
    located_total: number;
    eps_km: number;
    min_samples: number;
    note: string;
    method: string;
  };
  hotspots: {
    evaluable: boolean;
    reason: string | null;
    band_km: number;
    alpha: number;
    locations_tested: number;
    hot: HotspotLocation[];
    cold: HotspotLocation[];
    all: HotspotLocation[];
    significant_before_correction: number;
    significant_after_correction: number;
    test: string;
    caveat: string;
  };
  value_measured: string;
  computed_at: string;
  postgis_note: string;
}

export interface PatternModel {
  alpha: number;
  tests: {
    question: string;
    test: string;
    returns: string;
    why: string;
    declines_when: string;
    caveat?: string;
  }[];
  not_implemented: { item: string; reason: string }[];
}

export const LANE_LABEL: Record<string, string> = {
  transactions: "Transactions",
  communications: "Communications",
  events: "Events",
};

/** Formats a p-value without pretending to precision it does not have. */
export function formatP(p: number | null): string {
  if (p === null) return "—";
  if (p < 0.001) return "p < 0.001";
  return `p = ${p.toFixed(3)}`;
}

export function formatRatio(r: number | null): string {
  if (r === null) return "—";
  if (!Number.isFinite(r)) return "∞";
  return r.toFixed(2);
}
