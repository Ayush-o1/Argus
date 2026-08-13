import {
  Building2,
  CreditCard,
  FileText,
  Landmark,
  Package,
  ShieldHalf,
  Smartphone,
  User,
  Car as VehicleIcon,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

export const ENTITY_TYPE_COLOR: Record<string, string> = {
  Person: "var(--entity-person)",
  Organization: "var(--entity-organization)",
  Location: "var(--entity-location)",
  Vehicle: "var(--entity-vehicle)",
  Device: "var(--entity-device)",
  Account: "var(--entity-account)",
  Event: "var(--entity-event)",
  Document: "var(--entity-document)",
  Shipment: "var(--entity-shipment)",
  Case: "var(--accent-primary)",
  Incident: "var(--risk-high)",
};

const ICONS: Record<string, LucideIcon> = {
  Person: User,
  // Account had a colour but no icon, so it fell through to the Person
  // fallback — every account in search results, alerts and evidence lists was
  // drawn as a human being.
  Account: CreditCard,
  Organization: Building2,
  Location: Landmark,
  Vehicle: VehicleIcon,
  Device: Smartphone,
  Document: FileText,
  Shipment: Package,
  Case: ShieldHalf,
  Incident: ShieldHalf,
};

export function EntityTypeIcon({ label, size = 16 }: { label: string; size?: number }) {
  const Icon = ICONS[label] ?? User;
  const color = ENTITY_TYPE_COLOR[label] ?? "var(--text-tertiary)";
  return <Icon size={size} color={color} strokeWidth={1.75} />;
}
