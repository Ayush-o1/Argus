import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

export interface TimelineTransaction {
  id: string;
  timestamp: string;
  amount: number;
  subtype: string;
  flagged: boolean;
  storyline_id: string | null;
}

export interface TimelineCommunication {
  id: string;
  timestamp: string;
  duration_seconds: number;
  subtype: string;
  flagged: boolean;
  storyline_id: string | null;
}

export interface TimelineEvent {
  id: string;
  timestamp: string;
  subtype: string;
  flagged: boolean;
  storyline_id: string | null;
}

export interface TimelineIncident {
  id: string;
  timestamp: string;
  subtype: string;
  severity: "Low" | "Medium" | "High" | "Critical";
  description: string;
}

export interface GlobalTimeline {
  transactions: TimelineTransaction[];
  communications: TimelineCommunication[];
  events: TimelineEvent[];
  incidents: TimelineIncident[];
}

export function useGlobalTimeline() {
  return useQuery({
    queryKey: ["timeline", "global"],
    queryFn: async () => (await apiFetch<GlobalTimeline>("/api/timeline/events")).data,
  });
}
