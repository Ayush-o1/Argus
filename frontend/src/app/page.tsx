import { CapabilityGrid } from "@/components/marketing/CapabilityGrid";
import { FinalCTA } from "@/components/marketing/FinalCTA";
import { GraphMotif } from "@/components/marketing/GraphMotif";
import { Hero } from "@/components/marketing/Hero";
import { MapMotif } from "@/components/marketing/MapMotif";
import { MarketingFooter } from "@/components/marketing/MarketingFooter";
import { MarketingNav } from "@/components/marketing/MarketingNav";
import { SpotlightSection } from "@/components/marketing/SpotlightSection";
import { TechCredibility } from "@/components/marketing/TechCredibility";
import { TriageMotif } from "@/components/marketing/TriageMotif";
import { WorkflowSection } from "@/components/marketing/WorkflowSection";

export default function LandingPage() {
  return (
    <>
      <MarketingNav />
      <main>
        <Hero />
        <CapabilityGrid />
        <SpotlightSection
          id="intelligence"
          eyebrow="Graph intelligence"
          title="Risk first. Everything else on demand."
          desc="The Graph Explorer opens on the highest-risk entities and their immediate context — not every node the database has ever seen. Selecting an entity focuses its neighborhood; everything else recedes."
          points={[
            "Default view is risk-led, not a dump of the entire graph",
            "Zoom-aware labels — only what matters at the current scale",
            "Focus mode isolates a neighborhood and explains every edge",
            "Search jumps straight to an entity and centers the graph on it",
          ]}
          visual={<GraphMotif />}
        />
        <SpotlightSection
          eyebrow="Geospatial intelligence"
          title="See the pattern, not the tangle."
          desc="Thousands of shipment routes rendered at once is noise. ARGUS clusters entities by density, mutes routine traffic, and lets anomalous routes hold the analyst's attention."
          points={[
            "Entities cluster at low zoom, resolve to points as you zoom in",
            "Anomalous routes stay bright; routine traffic recedes into texture",
            "Hover for instant context, click for the full relationship detail",
            "Filter by entity type, risk threshold, or route status",
          ]}
          visual={<MapMotif />}
          reversed
        />
        <SpotlightSection
          eyebrow="Risk & triage"
          title="A queue, not a wall of data."
          desc="Risk is encoded so severity always wins your attention — a quiet baseline, loud escalation. The command center opens on what changed and what to look at next, and the alert queue is ordered by severity before recency so a critical finding never sits below newer noise."
          points={[
            "Priority queue ranks the highest-risk entities on arrival",
            "Alerts sort by severity first, with one-click pivot into the graph",
            "Isolation Forest flags transaction outliers with no ground-truth labels",
            "Every severity band is a filtered entry point, not just a statistic",
          ]}
          visual={<TriageMotif />}
        />
        <WorkflowSection />
        <TechCredibility />
        <FinalCTA />
      </main>
      <MarketingFooter />
    </>
  );
}
