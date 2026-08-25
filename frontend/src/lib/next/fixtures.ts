/**
 * Fixture data for the `/next` experience — Phase 2 of the redesign
 * (see ARGUS_PLAN.md, "Production experience redesign").
 *
 * This is an interim adapter, not a second data model. Every field here is
 * typed against the *real* API response shapes already used by the shipping
 * app — `DashboardSummary`, `RegionRollup`, `GraphNode`/`NodeAssessment`,
 * `DayBucket`, `Incident`, `SubjectAssessment`/`SignalOutcome` — imported
 * from their real definitions, not redeclared, so this file cannot silently
 * drift from what the backend actually returns. Where the Claude Design
 * prototype invented fields with no backend counterpart (correlation
 * "grounds"/"independent", fabricated custody metadata), those are left out
 * here rather than carried forward — see ARGUS_PLAN.md's capability-to-IA
 * mapping for what was verified against `correlation.py` instead.
 *
 * Swapping this out for live data (Phase 12) means replacing each
 * `nextFixture*` export with the corresponding real hook
 * (`useDashboardSummary`, `useMapRegions`, `useBrowseEntities`,
 * `useGlobalTimeline`, `useTemporalPatterns`, `fetchSubjectAssessment`) —
 * the consuming components are written against these same types either way.
 */

import type { AssessmentBand, SignalOutcome, SubjectAssessment } from "@/lib/assessment";
import type { Corridor, CountryRollup, RegionRollup, ShipmentRoute } from "@/hooks/useMap";
import type { DayBucket, GlobalTimeline } from "@/hooks/useTimeline";
import type { CaseSummary, DashboardSummary, GraphEdge, GraphNode, Incident } from "@/lib/types";
import type { Assertion, Conflict, Observation, Source, SubjectProvenance } from "@/lib/provenance";
import type { Alert, AlertState, PriorityBand } from "@/lib/alerts";
import type { Confidence, InvestigationState, InvestigationSummary, Outcome } from "@/lib/investigations";

// ---------------------------------------------------------------------------
// Deterministic PRNG — fixture data must be stable across renders and across
// reloads (mulberry32), the same reason the real generator is seeded rather
// than random: a fixture that reshuffles itself on every hot-reload makes
// visual QA (Phase 17) impossible to trust.
// ---------------------------------------------------------------------------
function mulberry32(seed: number) {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rand = mulberry32(42);
const pick = <T,>(arr: readonly T[]): T => arr[Math.floor(rand() * arr.length)];
const range = (n: number) => Array.from({ length: n }, (_, i) => i);

// India-weighted geography, matching generator/geography.py's real city set
// (Mumbai, Delhi, Bengaluru, Chennai, Hyderabad, Kolkata, Pune, Ahmedabad,
// Kochi, Mundra, plus the regional neighbours Karachi/Colombo/Dhaka/
// Chattogram) — region *names* here are placeholders pending verification
// against a live `GET /api/map/regions` call in Phase 12; the field shape is
// what's verified now, not this exact label set.
const CITIES = [
  { city: "Mumbai", country: "India", region: "South Asia", lat: 19.076, lng: 72.8777 },
  { city: "Delhi", country: "India", region: "South Asia", lat: 28.7041, lng: 77.1025 },
  { city: "Bengaluru", country: "India", region: "South Asia", lat: 12.9716, lng: 77.5946 },
  { city: "Chennai", country: "India", region: "South Asia", lat: 13.0827, lng: 80.2707 },
  { city: "Hyderabad", country: "India", region: "South Asia", lat: 17.385, lng: 78.4867 },
  { city: "Kolkata", country: "India", region: "South Asia", lat: 22.5726, lng: 88.3639 },
  { city: "Karachi", country: "Pakistan", region: "South Asia", lat: 24.8607, lng: 67.0011 },
  { city: "Colombo", country: "Sri Lanka", region: "South Asia", lat: 6.9271, lng: 79.8612 },
  { city: "Dhaka", country: "Bangladesh", region: "South Asia", lat: 23.8103, lng: 90.4125 },
  { city: "Dubai", country: "United Arab Emirates", region: "Middle East", lat: 25.2048, lng: 55.2708 },
  { city: "Doha", country: "Qatar", region: "Middle East", lat: 25.2854, lng: 51.531 },
  { city: "Ho Chi Minh City", country: "Vietnam", region: "Southeast Asia", lat: 10.8231, lng: 106.6297 },
  { city: "Tallinn", country: "Estonia", region: "Europe", lat: 59.437, lng: 24.7536 },
] as const;

const REGION_NAMES = Array.from(new Set(CITIES.map((c) => c.region)));

const PERSON_FIRST = ["Anwar", "Farida", "Lakshmi", "Thanh", "Ayesha", "Ravi", "Meera", "Suresh", "Zainab", "Vikram"];
const PERSON_LAST = ["Siddiqui", "Qureshi", "Venkatesh", "Minh Bùi", "Rehman", "Kumar", "Sharma", "Nair", "Iyer", "Rao"];
const ORG_NAME = [
  "Meridian Coastal Freight Pvt Ltd",
  "Sundara Holdings FZE",
  "Dhruva Agri Exports LLP",
  "Baltic Rim Logistics OÜ",
  "Kalinga Bulk Carriers Ltd",
  "Northgate Trading Co",
  "Vermillion Shipping Agency",
];

const BANDS: AssessmentBand[] = ["elevated", "notable", "routine", "insufficient_evidence"];

function makeAssessment(band: AssessmentBand) {
  const score = band === "insufficient_evidence" ? null : Math.round(rand() * 40 + (band === "elevated" ? 60 : band === "notable" ? 35 : 5));
  return {
    band,
    score,
    coverage: Math.round((0.35 + rand() * 0.6) * 100) / 100,
    model: "argus-assess-2026.3",
    assessed_at: "2026-08-24T10:00:00Z",
  };
}

const SIGNAL_TITLES = [
  { title: "Counterparty concentration", summary: "Over 70% of outbound value moves to a single, recently-registered counterparty." },
  { title: "Round-trip transaction pattern", summary: "Funds return to an originating account within 48 hours through two intermediaries." },
  { title: "Unregistered shipment corridor", summary: "Three shipments route through a corridor with no prior activity for this entity." },
  { title: "Rapid account formation", summary: "Four linked accounts opened within a nine-day window shortly before the flagged activity." },
  { title: "Sanctioned-adjacent contact", summary: "One communication record links to a number two hops from a watchlisted number." },
];

const N_SUBJECTS = 34;

export const nextFixtureSubjects: GraphNode[] = range(N_SUBJECTS).map((i) => {
  const isOrg = i % 3 === 0;
  const loc = pick(CITIES);
  const band = i < 9 ? "elevated" : i < 16 ? "notable" : i < 30 ? "routine" : "insufficient_evidence";
  const name = isOrg ? pick(ORG_NAME) + (rand() < 0.4 ? ` ${i}` : "") : `${pick(PERSON_FIRST)} ${pick(PERSON_LAST)}`;
  return {
    id: `${isOrg ? "ORG" : "PRS"}-${String(1000 + i).padStart(7, "0")}`,
    uuid: `uuid-${i}`,
    label: isOrg ? "Organization" : "Person",
    name,
    assessment: makeAssessment(band),
    properties: { region: loc.region, city: loc.city, country: loc.country, lat: loc.lat, lng: loc.lng },
    degree: Math.round(rand() * 12) + 1,
    connections: { Transaction: Math.round(rand() * 40), Communication: Math.round(rand() * 15), Account: Math.round(rand() * 3) },
  };
});

export const nextFixtureSignals: Record<string, SignalOutcome[]> = Object.fromEntries(
  nextFixtureSubjects
    .filter((s) => s.assessment?.band === "elevated" || s.assessment?.band === "notable")
    .map((s, idx) => {
      const n = 2 + (idx % 3);
      const signals: SignalOutcome[] = range(n).map((j) => {
        const src = SIGNAL_TITLES[(idx + j) % SIGNAL_TITLES.length];
        const magnitude = Math.round((0.3 + rand() * 0.65) * 100) / 100;
        return {
          signal_id: `sig-${s.id}-${j}`,
          family: ["financial", "network", "geographic", "temporal"][j % 4],
          weight: 1,
          evaluable: true,
          magnitude,
          contribution: Math.round(magnitude * 22),
          summary: src.summary,
          detail: { title: src.title },
        };
      });
      // One not-evaluable signal per subject, matching the real coverage<100% story.
      signals.push({
        signal_id: `sig-${s.id}-ne`,
        family: "financial",
        weight: 1,
        evaluable: false,
        magnitude: null,
        contribution: 0,
        summary: "Cross-border wire confirmation — no correspondent-bank record available in this dataset.",
        detail: {},
      });
      return [s.id, signals];
    }),
);

export const nextFixtureRegions: RegionRollup[] = REGION_NAMES.map((region) => {
  const inRegion = nextFixtureSubjects.filter((s) => s.properties.region === region);
  const elevated = inRegion.filter((s) => s.assessment?.band === "elevated").length;
  const assessed = inRegion.filter((s) => s.assessment?.band !== "insufficient_evidence").length;
  const cities = CITIES.filter((c) => c.region === region);
  return {
    region,
    entity_count: 400 + Math.round(rand() * 3000),
    org_count: 60 + Math.round(rand() * 400),
    country_count: new Set(cities.map((c) => c.country)).size,
    elevated_count: elevated,
    assessed_count: assessed,
    flagged_routes: Math.round(rand() * 6),
    lat: cities[0]?.lat ?? 0,
    lng: cities[0]?.lng ?? 0,
    zoom: 4,
  };
});

const DAY_COUNT = 90;
const DAY_MS = 86_400_000;
const LATEST = Date.parse("2026-08-24T00:00:00Z");
const BURST_DAYS = new Set([22, 55, 71, 72]);

function isoDay(offsetFromLatest: number): string {
  return new Date(LATEST - offsetFromLatest * DAY_MS).toISOString().slice(0, 10);
}

export const nextFixtureActivityDays: DayBucket[] = range(DAY_COUNT).map((i) => {
  const offset = DAY_COUNT - 1 - i; // oldest first
  const burst = BURST_DAYS.has(i);
  const base = 40 + Math.round(rand() * 25);
  const total = burst ? base + 90 + Math.round(rand() * 40) : base;
  const sourceReported = burst ? Math.round(total * 0.35) : Math.round(total * (0.05 + rand() * 0.08));
  return {
    day: isoDay(offset),
    total,
    source_reported: sourceReported,
    transactions: Math.round(total * 0.55),
    communications: Math.round(total * 0.3),
    events: Math.round(total * 0.1),
    incidents: total - Math.round(total * 0.55) - Math.round(total * 0.3) - Math.round(total * 0.1),
    transactions_source_reported: Math.round(sourceReported * 0.6),
    communications_source_reported: Math.round(sourceReported * 0.25),
    events_source_reported: Math.round(sourceReported * 0.1),
    incidents_source_reported: Math.round(sourceReported * 0.05),
  };
});

/** Mirrors the `day -> direction` map the real Timeline page builds from
 * `useTemporalPatterns()` — a two-sided Poisson test result, not a bare
 * threshold. See `frontend/src/app/(app)/timeline/page.tsx`. */
export const nextFixtureUnusualDays = new Map<string, "high" | "low">(
  range(DAY_COUNT)
    .filter((i) => BURST_DAYS.has(i))
    .map((i) => [isoDay(DAY_COUNT - 1 - i), "high" as const]),
);

/** Shaped exactly like the real `/api/timeline/events` response
 * (`GlobalTimeline`) so `analyseDays` (`timelineModel.ts`) runs unmodified
 * against it. `totals` is a real sum over `nextFixtureActivityDays`, not a
 * separate invented figure. `detail` is left with zero record previews
 * (`NotableMoments`'s per-record scatter isn't wired into the Timeline lens
 * yet) rather than fabricating individual transaction/communication records
 * with no backend counterpart to verify them against. */
const activityTotals = nextFixtureActivityDays.reduce(
  (acc, b) => ({
    total: acc.total + b.total,
    sourceReported: acc.sourceReported + b.source_reported,
    transactions: acc.transactions + b.transactions,
    communications: acc.communications + b.communications,
    events: acc.events + b.events,
    incidents: acc.incidents + b.incidents,
  }),
  { total: 0, sourceReported: 0, transactions: 0, communications: 0, events: 0, incidents: 0 },
);

const emptyPreview = {
  records: [],
  coverage: {
    value: 0,
    basis: "complete" as const,
    population: 0,
    examined: 0,
    method: "fixture — record-level detail not populated",
    computed_at: "2026-08-24T10:00:00Z",
  },
};

export const nextFixtureGlobalTimeline: GlobalTimeline = {
  buckets: nextFixtureActivityDays,
  day_count: DAY_COUNT,
  totals: {
    records: { ...emptyPreview.coverage, value: activityTotals.total, population: activityTotals.total, examined: activityTotals.total },
    source_reported: {
      ...emptyPreview.coverage,
      value: activityTotals.sourceReported,
      population: activityTotals.total,
      examined: activityTotals.sourceReported,
    },
    by_lane: {
      transactions: activityTotals.transactions,
      communications: activityTotals.communications,
      events: activityTotals.events,
      incidents: activityTotals.incidents,
    },
  },
  detail: {
    transactions: emptyPreview,
    communications: emptyPreview,
    events: emptyPreview,
    incidents: emptyPreview,
  },
};

const INCIDENT_TYPES = ["Transaction burst", "Manifest discrepancy cluster", "Cross-border circularity", "Flagged corridor concentration", "Circular funds path"];
const RULE_IDS = ["tempo.burst.v4", "logistics.manifest_delta.v3", "funds.circularity.v2", "geo.corridor.v1"];

export const nextFixtureIncidents: Incident[] = range(12).map((i) => {
  const subject = pick(nextFixtureSubjects.filter((s) => s.assessment?.band !== "routine" && s.assessment?.band !== "insufficient_evidence"));
  const daysAgo = Math.round(rand() * 6) + 1;
  return {
    incident_id: `INC-2026-${String(400 + i).padStart(4, "0")}`,
    type: pick(INCIDENT_TYPES),
    severity: pick(["Medium", "High", "Critical"] as const),
    timestamp: new Date(LATEST - daysAgo * DAY_MS).toISOString(),
    description: `${pick(RULE_IDS)} fired ×${Math.round(rand() * 6) + 1} against this subject's recent activity.`,
    status: rand() < 0.5 ? "open" : "unreviewed",
    storyline_id: null,
    involved_entity_ids: subject ? [subject.id] : [],
  };
});

export const nextFixtureDashboard: DashboardSummary = {
  total_persons: 4000,
  total_organizations: 400,
  total_transactions: 40_000,
  elevated_entities: nextFixtureSubjects.filter((s) => s.assessment?.band === "elevated").length,
  open_investigations: 3,
  investigations_by_state: { open: 3, concluded: 11 },
  investigation_outcomes: { substantiated: 4, unsubstantiated: 5, inconclusive: 2 },
  source_reported_cases: 26,
  open_alerts: nextFixtureIncidents.filter((i) => i.status === "open" || i.status === "unreviewed").length,
  high_priority_open_alerts: nextFixtureIncidents.filter((i) => i.severity === "Critical").length,
  incidents_in_window: nextFixtureIncidents.length,
  critical_incidents_in_window: nextFixtureIncidents.filter((i) => i.severity === "Critical").length,
  window_days: 14,
  assessment_distribution: BANDS.map((band) => ({
    band,
    count: nextFixtureSubjects.filter((s) => s.assessment?.band === band).length,
  })),
  assessed_persons: nextFixtureSubjects.filter((s) => s.label === "Person" && s.assessment?.band !== "insufficient_evidence").length,
  recent_incidents: nextFixtureIncidents,
  recent_source_reported_cases: [],
};

/** Matches `SubjectAssessment` exactly — the dossier panel reads this type
 * whether the data comes from here or from `fetchSubjectAssessment()`. */
export function nextFixtureSubjectAssessment(subject: GraphNode): SubjectAssessment | null {
  if (!subject.assessment) return null;
  const signals = nextFixtureSignals[subject.id] ?? [];
  return {
    subject_ref: subject.id,
    subject_type: subject.label,
    band: subject.assessment.band,
    band_meaning:
      subject.assessment.band === "elevated"
        ? "Multiple independent signals fired at high magnitude."
        : subject.assessment.band === "notable"
          ? "Some signals fired; below the threshold for elevated review."
          : subject.assessment.band === "routine"
            ? "Evaluated; nothing notable found."
            : "Too little evidence exists to evaluate this subject.",
    score: subject.assessment.score,
    evidence_coverage: subject.assessment.coverage ?? 0,
    evaluable_weight: signals.filter((s) => s.evaluable).length,
    total_weight: signals.length,
    families_fired: Array.from(new Set(signals.filter((s) => s.evaluable && (s.magnitude ?? 0) > 0).map((s) => s.family))),
    model_version: "argus-assess-2026.3",
    model_fingerprint: "fp9f3c1ab7",
    computed_at: subject.assessment.assessed_at ?? "2026-08-24T10:00:00Z",
    signals,
  };
}

/** Matches the shape `correlation.py`'s `/model` endpoint and `assessment.py`'s
 * evaluation record actually return (`model_version`/`model_fingerprint` pairs,
 * a synthetic-only precision/recall evaluation) — see `EvaluationRecord` in
 * `lib/assessment.ts`. Real wiring in Phase 12 reads `fetchLatestEvaluation()`. */
export const nextFixtureModel = {
  version: "argus-assess-2026.3",
  fingerprint: "fp9f3c1ab7",
  world_seed: 42,
  last_run_at: "2026-08-24T16:00:00Z",
  precision_elevated: 0.93,
  recall_elevated: 0.8,
};

/** An analyst's own recorded judgement about a subject — from
 * `assessment:dissent`. Only some elevated/notable subjects have one, which
 * is itself real behavior the UI must show (see `NextLeadDossier`'s
 * "unreviewed by analyst" state). */
export interface NextAnalystJudgement {
  score: number;
  band: AssessmentBand;
  by: string;
  at: string;
  note: string;
}

const ANALYSTS = ["s.iyer", "r.mehta", "k.fernandes"];

export const nextFixtureAnalystJudgements: Record<string, NextAnalystJudgement> = Object.fromEntries(
  nextFixtureSubjects
    .filter((s) => (s.assessment?.band === "elevated" || s.assessment?.band === "notable") && rand() < 0.55)
    .map((s) => {
      const argusScore = s.assessment?.score ?? 50;
      const divergent = rand() < 0.4;
      const score = Math.max(0, Math.min(100, Math.round(argusScore + (divergent ? (rand() < 0.5 ? -1 : 1) * (18 + rand() * 20) : (rand() - 0.5) * 10))));
      return [
        s.id,
        {
          score,
          band: score >= 70 ? "elevated" : score >= 40 ? "notable" : "routine",
          by: pick(ANALYSTS),
          at: "2026-08-23",
          note: divergent
            ? "Reviewed the underlying transactions directly — the counterparty is a documented regional distributor, not a shell. Weighting this lower than the model does."
            : "Corroborates the model's read after independent review of the linked accounts.",
        } satisfies NextAnalystJudgement,
      ];
    }),
);

// ---------------------------------------------------------------------------
// Provenance — Evidence mode.
//
// The three sources below are copied from `BUILTIN_SOURCES` in
// `backend/app/services/provenance.py` verbatim (id, name, rating,
// description, reliability_basis) rather than invented: this system rates
// every one of its own sources F, including its own analyst workbench and
// its own derived-algorithm output, by deliberate design — there is no
// "trusted" source here to fabricate. Per-subject observations/assertions
// mirror `backfill_graph_provenance`'s real shape (one generator observation
// per subject, content_type `graph.node.{label}`; an INFERRED `risk_score`
// assertion rated F/6 with the exact real method id and note wording), and
// reuse `nextFixtureAnalystJudgements` above for the analyst side rather than
// inventing a second, disconnected judgement — a divergent judgement there
// becomes a genuine `Conflict` here, on the same predicate, exactly as the
// real provenance store would surface it.
// ---------------------------------------------------------------------------

const GENERATOR_SOURCE_ID = "argus.scenario-generator";
const ANALYST_SOURCE_ID = "argus.analyst";
const DERIVED_SOURCE_ID = "argus.derived";
const GENERATOR_RISK_METHOD = "generator.risk_scorer@v1";

export const nextFixtureSources: Source[] = [
  {
    source_id: GENERATOR_SOURCE_ID,
    name: "ARGUS Scenario Generator",
    source_type: "synthetic",
    description:
      "Fabricates a synthetic world — people, organisations, accounts, movements and planted storylines — for demonstration and testing. It is not a report about anything that happened.",
    reliability: "F",
    reliability_basis:
      "Reliability cannot be judged, because there is nothing to judge it against: this source invents its content rather than reporting on the world. The rating is F and the synthetic flag is set, so no assessment built on this data can inherit confidence it has not earned.",
    is_synthetic: true,
    independence_group: GENERATOR_SOURCE_ID,
    staleness_hours: null,
    is_active: true,
    registered_at: "2026-01-01T00:00:00Z",
  },
  {
    source_id: ANALYST_SOURCE_ID,
    name: "ARGUS Analyst Workbench",
    source_type: "human",
    description: "Judgements entered by named analysts through ARGUS. Each assertion is attributed to the individual who made it.",
    reliability: "F",
    reliability_basis:
      "ARGUS does not rate individual analysts, and assigning the workbench a flattering blanket rating would launder every judgement made through it. Source-level reliability is therefore left unjudged; what carries weight is the named analyst on the assertion and the credibility they state for the specific claim.",
    is_synthetic: false,
    independence_group: ANALYST_SOURCE_ID,
    staleness_hours: null,
    is_active: true,
    registered_at: "2026-01-01T00:00:00Z",
  },
  {
    source_id: DERIVED_SOURCE_ID,
    name: "ARGUS Derived",
    source_type: "system",
    description: "Output of ARGUS's own algorithms — scoring, correlation, anomaly detection. Every assertion names the method and version that produced it.",
    reliability: "F",
    reliability_basis:
      "The reliability of a derivation is a property of the method and its calibration. ARGUS has no calibration report for any of its algorithms yet, so there is no basis for a rating and F is the honest answer.",
    is_synthetic: false,
    independence_group: DERIVED_SOURCE_ID,
    staleness_hours: null,
    is_active: true,
    registered_at: "2026-01-01T00:00:00Z",
  },
];

function hex(n: number): string {
  let s = "";
  for (let i = 0; i < n; i++) s += Math.floor(rand() * 16).toString(16);
  return s;
}

export const nextFixtureProvenance: Record<string, SubjectProvenance> = Object.fromEntries(
  nextFixtureSubjects.map((subject) => {
    const observationId = `obs-${hex(12)}`;
    const observation: Observation = {
      observation_id: observationId,
      source_id: GENERATOR_SOURCE_ID,
      source_name: "ARGUS Scenario Generator",
      source_reliability: "F",
      source_is_synthetic: true,
      content_type: `graph.node.${subject.label}`,
      payload: subject.properties,
      content_hash: hex(64),
      occurred_at: null,
      collected_at: null,
      recorded_at: "2026-08-01T00:00:00Z",
      supersedes: null,
      provenance_note:
        "Reconstructed from the graph by the provenance backfill. The graph predates the provenance layer, so this record was not captured at ingest: recorded_at is when the backfill ran, and collection and occurrence times are null because the source never recorded them.",
      subjects: [subject.id],
    };

    const assertions: Assertion[] = [];
    const conflicts: Conflict[] = [];

    if (subject.assessment && subject.assessment.score !== null) {
      const generatorAssertion: Assertion = {
        assertion_id: `ast-${hex(12)}`,
        subject_ref: subject.id,
        subject_type: subject.label,
        predicate: "risk_score",
        object_value: subject.assessment.score,
        epistemic_kind: "inferred",
        rating: { reliability: "F", credibility: "6" },
        method: GENERATOR_RISK_METHOD,
        asserted_by: `source:${GENERATOR_SOURCE_ID}`,
        asserted_by_display: "ARGUS Scenario Generator",
        asserted_at: "2026-08-01T00:00:00Z",
        valid_from: "2026-08-01T00:00:00Z",
        valid_until: null,
        superseded_by: null,
        superseded_at: null,
        retracted_at: null,
        retracted_by: null,
        retracted_by_display: null,
        retraction_reason: null,
        note: "Assigned by the scenario generator from storyline membership, not derived from evidence about the world.",
        evidence: [
          {
            observation_id: observationId,
            stance: "supports",
            source_id: GENERATOR_SOURCE_ID,
            source_name: "ARGUS Scenario Generator",
            source_reliability: "F",
            source_is_synthetic: true,
            recorded_at: observation.recorded_at,
            occurred_at: null,
            collected_at: null,
          },
        ],
        corroboration: {
          independent_sources: 1,
          supporting_observations: 1,
          contradicting_observations: 0,
          source_groups: [GENERATOR_SOURCE_ID],
          contradicting_groups: [],
        },
      };
      assertions.push(generatorAssertion);

      const judgement = nextFixtureAnalystJudgements[subject.id];
      if (judgement) {
        const analystAssertion: Assertion = {
          assertion_id: `ast-${hex(12)}`,
          subject_ref: subject.id,
          subject_type: subject.label,
          predicate: "risk_score",
          object_value: judgement.score,
          epistemic_kind: "assessed",
          rating: { reliability: "F", credibility: Math.abs(judgement.score - subject.assessment.score) > 15 ? "3" : "2" },
          method: "analyst.manual_review",
          asserted_by: `user:${judgement.by}`,
          asserted_by_display: judgement.by,
          asserted_at: `${judgement.at}T00:00:00Z`,
          valid_from: `${judgement.at}T00:00:00Z`,
          valid_until: null,
          superseded_by: null,
          superseded_at: null,
          retracted_at: null,
          retracted_by: null,
          retracted_by_display: null,
          retraction_reason: null,
          note: judgement.note,
          evidence: [],
          corroboration: null,
        };
        assertions.push(analystAssertion);
        conflicts.push({ subject_ref: subject.id, predicate: "risk_score", assertions: [generatorAssertion, analystAssertion] });
      }
    }

    const provenance: SubjectProvenance = {
      subject_ref: subject.id,
      as_of: null,
      observations: [observation],
      observation_total: 1,
      assertions,
      conflicts,
      sources: nextFixtureSources,
    };

    return [subject.id, provenance];
  }),
);

// ---------------------------------------------------------------------------
// Triage — Alerts, the investigation queue, and Cases, kept as three
// distinct records rather than one undifferentiated "queue" list.
//
// `rule_id` values are the real four from `RULE_LABEL` (`lib/alerts.ts`);
// `Alert`/`InvestigationSummary`/`CaseSummary` are the real API shapes, not
// redeclared. Cases here are deliberately NOT investigations: the real
// `/cases` page's own provenance note (every case record is written by the
// scenario generator from a storyline it just planted, down to an invented
// analyst name) is carried into the Triage page verbatim, and no case here
// is linked into `nextFixtureInvestigations` as if one had grown out of it.
// ---------------------------------------------------------------------------

const RULE_IDS_ALERT = ["assessment.elevated", "assessment.escalated", "correlation.established_pair", "convergence.assessed_cluster"] as const;

const ALERT_SUBJECTS = nextFixtureSubjects.filter((s) => s.assessment?.band === "elevated" || s.assessment?.band === "notable");

function alertFor(subject: GraphNode, ruleId: (typeof RULE_IDS_ALERT)[number], state: AlertState, idx: number): Alert {
  const priority = Math.round((0.5 + rand() * 0.45) * 100) / 100;
  const band: PriorityBand = priority >= 0.75 ? "high" : priority >= 0.5 ? "medium" : "low";
  const summaries: Record<(typeof RULE_IDS_ALERT)[number], string> = {
    "assessment.elevated": `${subject.name} was assessed elevated by the current model.`,
    "assessment.escalated": `${subject.name} moved up a band since the last assessment run.`,
    "correlation.established_pair": `${subject.name} forms an established-tier correlation pair with another subject in scope.`,
    "convergence.assessed_cluster": `Two independent methods concur on ${subject.name} within the same cluster.`,
  };
  return {
    alert_key: `ALT-2026-${String(1000 + idx).padStart(5, "0")}`,
    rule_id: ruleId,
    rule_version: 1,
    scope: [subject.id],
    group_key: null,
    title: `${subject.label} in scope — ${ruleId}`,
    summary: summaries[ruleId],
    priority,
    priority_band: band,
    priority_factors: {
      priority,
      band,
      factors: {
        corroboration: Math.round(rand() * 100) / 100,
        confidence: Math.round(rand() * 100) / 100,
        magnitude: Math.round(rand() * 100) / 100,
        recency: Math.round(rand() * 100) / 100,
      },
      independent_methods: ruleId === "convergence.assessed_cluster" ? 2 : 1,
      evidence_age_days: Math.round(rand() * 20),
      asset_criticality: null,
      asset_criticality_note: "Asset criticality is not modelled in this build.",
    },
    evidence: {},
    state,
    assigned_to: state === "investigating" || state === "resolved" ? pick(ANALYSTS) : null,
    closed_at: state === "resolved" ? "2026-08-22T00:00:00Z" : null,
    dismissal_reason: null,
    suppressed: false,
    suppressed_by: null,
    occurrence_count: 1 + Math.round(rand() * 3),
    first_seen_at: "2026-08-15T00:00:00Z",
    last_seen_at: "2026-08-24T00:00:00Z",
  };
}

const ALERT_STATES: AlertState[] = ["open", "open", "acknowledged", "investigating", "investigating", "resolved"];

export const nextFixtureAlerts: Alert[] = ALERT_STATES.map((state, i) =>
  alertFor(ALERT_SUBJECTS[i % ALERT_SUBJECTS.length], RULE_IDS_ALERT[i % RULE_IDS_ALERT.length], state, i),
);

const INVESTIGATION_DEFS: { state: InvestigationState; confidence: Confidence; outcome: Outcome | null }[] = [
  { state: "open", confidence: "low", outcome: null },
  { state: "active", confidence: "moderate", outcome: null },
  { state: "closed", confidence: "high", outcome: "confirmed" },
  { state: "closed", confidence: "moderate", outcome: "inconclusive" },
];

export const nextFixtureInvestigations: InvestigationSummary[] = INVESTIGATION_DEFS.map((def, i) => {
  const subject = ALERT_SUBJECTS[i % ALERT_SUBJECTS.length];
  return {
    investigation_id: `inv-${hex(12)}`,
    inv_ref: `INV-2026-${String(100 + i).padStart(4, "0")}`,
    title: `${subject.name} — ${def.state === "closed" ? "review of elevated assessment" : "elevated assessment under review"}`,
    state: def.state,
    confidence: def.confidence,
    assigned_to: pick(ANALYSTS),
    opened_by: pick(ANALYSTS),
    opened_at: "2026-08-16T00:00:00Z",
    outcome: def.outcome,
    closed_at: def.state === "closed" ? "2026-08-23T00:00:00Z" : null,
    review_count: def.state === "closed" ? 1 : 0,
    dissenting_reviews: def.outcome === "inconclusive" ? 1 : 0,
    last_reviewed_at: def.state === "closed" ? "2026-08-23T00:00:00Z" : null,
    alert_count: 1,
    entity_count: 1,
    finding_count: def.state === "closed" ? 2 : def.state === "active" ? 1 : 0,
    open_action_count: def.state === "active" ? 1 : 0,
  };
});

const CASE_TITLES = ["Freight manifest discrepancy — Q3 shipment cluster", "Rapid account formation near flagged corridor", "Cross-border payment loop, three-hop"];

export const nextFixtureCases: CaseSummary[] = CASE_TITLES.map((title, i) => ({
  case_id: `CASE-2026-${String(200 + i).padStart(4, "0")}`,
  title,
  status: (["Open", "UnderReview", "Closed"] as const)[i % 3],
  priority: (["High", "Medium", "Critical"] as const)[i % 3],
  opened_at: "2026-08-10T00:00:00Z",
  closed_at: i % 3 === 2 ? "2026-08-20T00:00:00Z" : null,
}));

// ---------------------------------------------------------------------------
// Correlation — Investigate's Graph lens (Phase 6/7).
//
// Field names and tier/family values are taken directly from
// `backend/app/correlation/model.py` and `dimensions.py` (TIER_ESTABLISHED/
// PROBABLE/POSSIBLE = "established"/"probable"/"possible"; FAMILY_FINANCIAL
// etc. = "financial"/"social"/"logistical"/"spatial"/"temporal"), and the
// link/cluster field lists match `_link_payload`/`_cluster_payload` in
// `correlation.py` exactly — not the Claude Design prototype's invented
// "grounds"/"independent" shape, which has no backend counterpart.
// ---------------------------------------------------------------------------

export interface NextCorrelationLink {
  link_id: string;
  ref_a: string;
  ref_b: string;
  type_a: string;
  type_b: string;
  strength: number;
  tier: "established" | "probable" | "possible";
  tier_meaning: string;
  coverage: number;
  evaluable_dimensions: number;
  applicable_dimensions: number;
  corroborating_families: string[];
  model_version: string;
  model_fingerprint: string;
  computed_at: string;
}

export interface NextCorrelationCluster {
  cluster_id: string;
  cluster_key: string;
  size: number;
  families: string[];
  mean_strength: number;
  min_strength: number;
  weakest_bridge: string;
  bridge_count: number;
  over_merged: boolean;
  basis: string;
  members: string[];
}

const TIER_MEANING: Record<NextCorrelationLink["tier"], string> = {
  established: "Multiple independent families corroborate this pair.",
  probable: "One strong family, or several weaker ones, connect this pair.",
  possible: "A single weak or shared-source signal — published so it can be dismissed with its reason visible.",
};

// Three small clusters among the elevated subjects, matching the shape a real
// `/api/correlation/clusters` response would take. Elevated subjects are
// indices 0-8 in `nextFixtureSubjects` (see the generator above).
const CLUSTER_MEMBERSHIP: string[][] = [
  [nextFixtureSubjects[0].id, nextFixtureSubjects[1].id, nextFixtureSubjects[3].id],
  [nextFixtureSubjects[2].id, nextFixtureSubjects[5].id],
  [nextFixtureSubjects[4].id, nextFixtureSubjects[6].id, nextFixtureSubjects[7].id, nextFixtureSubjects[8].id],
];

function pairLink(refA: string, refB: string, idx: number): NextCorrelationLink {
  const strength = Math.round((0.4 + rand() * 0.55) * 100) / 100;
  const tier: NextCorrelationLink["tier"] = strength >= 0.75 ? "established" : strength >= 0.5 ? "probable" : "possible";
  const families = ["financial", "social", "logistical", "spatial", "temporal"];
  const corroborating = families.filter(() => rand() < (tier === "established" ? 0.55 : 0.25));
  const a = nextFixtureSubjects.find((s) => s.id === refA);
  const b = nextFixtureSubjects.find((s) => s.id === refB);
  return {
    link_id: `LNK-${String(idx).padStart(5, "0")}`,
    ref_a: refA,
    ref_b: refB,
    type_a: a?.label ?? "Person",
    type_b: b?.label ?? "Person",
    strength,
    tier,
    tier_meaning: TIER_MEANING[tier],
    coverage: Math.round((0.4 + rand() * 0.5) * 100) / 100,
    evaluable_dimensions: 3 + Math.round(rand() * 3),
    applicable_dimensions: 6,
    corroborating_families: corroborating.length ? corroborating : [families[0]],
    model_version: "argus-correlate-2026.1",
    model_fingerprint: "cfp7a21e9",
    computed_at: "2026-08-24T10:00:00Z",
  };
}

let linkCounter = 0;
export const nextFixtureCorrelationClusters: NextCorrelationCluster[] = CLUSTER_MEMBERSHIP.map((members, i) => {
  const links: NextCorrelationLink[] = [];
  for (let a = 0; a < members.length; a++) {
    for (let b = a + 1; b < members.length; b++) {
      links.push(pairLink(members[a], members[b], ++linkCounter));
    }
  }
  const strengths = links.map((l) => l.strength);
  const weakest = links.reduce((min, l) => (l.strength < min.strength ? l : min), links[0]);
  return {
    cluster_id: `CL-${String(i + 1).padStart(2, "0")}`,
    cluster_key: `cluster-${i + 1}`,
    size: members.length,
    families: Array.from(new Set(links.flatMap((l) => l.corroborating_families))),
    mean_strength: Math.round((strengths.reduce((a, b) => a + b, 0) / strengths.length) * 100) / 100,
    min_strength: Math.min(...strengths),
    weakest_bridge: `${weakest.ref_a} ↔ ${weakest.ref_b}`,
    bridge_count: links.length,
    over_merged: members.length > 3 && Math.min(...strengths) < 0.35,
    basis: links.some((l) => l.corroborating_families.length > 1) ? "multi-family corroboration" : "single-family match",
    members,
  };
});

export const nextFixtureCorrelationLinks: NextCorrelationLink[] = nextFixtureCorrelationClusters.flatMap((c) => {
  const members = c.members;
  const links: NextCorrelationLink[] = [];
  for (let a = 0; a < members.length; a++) {
    for (let b = a + 1; b < members.length; b++) {
      links.push(pairLink(members[a], members[b], ++linkCounter));
    }
  }
  return links;
});

/** The Graph lens's edges — one per correlation link, converted to the plain
 * `GraphEdge` shape `GraphCanvas` already renders (`lib/types.ts`). */
export const nextFixtureGraphEdges: GraphEdge[] = nextFixtureCorrelationLinks.map((l) => ({
  id: l.link_id,
  source: l.ref_a,
  target: l.ref_b,
  type: l.tier,
  properties: { strength: l.strength, corroborating_families: l.corroborating_families },
}));

export function clusterForSubject(id: string): NextCorrelationCluster | null {
  return nextFixtureCorrelationClusters.find((c) => c.members.includes(id)) ?? null;
}

// ---------------------------------------------------------------------------
// Map lens (Phase 6) — shipments/countries/corridors, matching
// `ShipmentRoute`/`CountryRollup`/`Corridor` from `hooks/useMap.ts` exactly.
// ---------------------------------------------------------------------------

export const nextFixtureCountries: CountryRollup[] = Array.from(
  new Map(CITIES.map((c) => [c.country, c])).values(),
).map((c) => {
  const inCountry = nextFixtureSubjects.filter((s) => s.properties.country === c.country);
  return {
    country: c.country,
    country_code: c.country.slice(0, 2).toUpperCase(),
    region: c.region,
    entity_count: 80 + Math.round(rand() * 900),
    elevated_count: inCountry.filter((s) => s.assessment?.band === "elevated").length,
    assessed_count: inCountry.filter((s) => s.assessment?.band !== "insufficient_evidence").length,
    lat: c.lat,
    lng: c.lng,
  };
});

const CARRIERS = ["Meridian Coastal Freight", "Northgate Trading Co", "Baltic Rim Logistics", "Vermillion Shipping Agency"];

export const nextFixtureShipments: ShipmentRoute[] = range(24).map((i) => {
  const origin = pick(CITIES);
  let dest = pick(CITIES);
  while (dest.city === origin.city) dest = pick(CITIES);
  const band = rand() < 0.15 ? "elevated" : rand() < 0.35 ? "notable" : rand() < 0.7 ? "routine" : "insufficient_evidence";
  const circuitous = rand() < 0.2;
  const via = circuitous ? pick(CITIES.filter((c) => c.city !== origin.city && c.city !== dest.city)) : null;
  return {
    shipment_id: `SHP-2026-${String(1000 + i).padStart(5, "0")}`,
    carrier: pick(CARRIERS),
    status: "delivered",
    argus_band: band,
    argus_score: band === "insufficient_evidence" ? null : Math.round(rand() * 40 + (band === "elevated" ? 60 : band === "notable" ? 35 : 5)),
    argus_coverage: Math.round((0.4 + rand() * 0.5) * 100) / 100,
    lane: `${origin.region} → ${dest.region}`,
    origin_region: origin.region,
    destination_region: dest.region,
    distance_km: Math.round(800 + rand() * 6000),
    detour_ratio: circuitous ? Math.round((1.15 + rand() * 0.6) * 100) / 100 : null,
    departure: "2026-08-10T00:00:00Z",
    arrival: "2026-08-18T00:00:00Z",
    manifest: null,
    origin_name: origin.city,
    origin_city: origin.city,
    origin_country: origin.country,
    origin_lat: origin.lat,
    origin_lng: origin.lng,
    dest_name: dest.city,
    dest_city: dest.city,
    dest_country: dest.country,
    dest_lat: dest.lat,
    dest_lng: dest.lng,
    via_name: via?.city ?? null,
    via_city: via?.city ?? null,
    via_country: via?.country ?? null,
    via_lat: via?.lat ?? null,
    via_lng: via?.lng ?? null,
  };
});

export const nextFixtureCorridors: Corridor[] = (() => {
  const seen = new Map<string, Corridor>();
  for (const s of nextFixtureShipments) {
    if (!s.origin_region || !s.destination_region || s.origin_region === s.destination_region) continue;
    const key = [s.origin_region, s.destination_region].sort().join("::");
    const existing = seen.get(key);
    const anomalous = s.argus_band === "elevated" || s.argus_band === "notable";
    if (existing) {
      existing.shipment_count += 1;
      if (anomalous) existing.anomalous_count += 1;
      existing.anomaly_rate = existing.anomalous_count / existing.shipment_count;
    } else {
      const originCity = CITIES.find((c) => c.region === s.origin_region);
      const destCity = CITIES.find((c) => c.region === s.destination_region);
      seen.set(key, {
        from_region: s.origin_region,
        to_region: s.destination_region,
        shipment_count: 1,
        anomalous_count: anomalous ? 1 : 0,
        anomaly_rate: anomalous ? 1 : 0,
        from_lat: originCity?.lat ?? s.origin_lat,
        from_lng: originCity?.lng ?? s.origin_lng,
        to_lat: destCity?.lat ?? s.dest_lat,
        to_lng: destCity?.lng ?? s.dest_lng,
      });
    }
  }
  return Array.from(seen.values());
})();
