// Specimen rows for the /admin/ui table density sample. They are not data: never fetched, stored or
// shown outside the gallery, and the page labels them as specimens (AGENTS.md §2, no fake data).
export interface SpecimenRow {
  name: string;
  priceMinor: number;
  margin: number | null;
  velocity: number;
  saturation: number;
  lastSeen: string;
  stale?: boolean;
}

export const specimenRows: SpecimenRow[] = [
  { name: "Specimen 01", priceMinor: 2499, margin: 42.3, velocity: 12.4, saturation: -3.1, lastSeen: "06:00 UTC" },
  { name: "Specimen 02 with a long name that truncates in narrow columns", priceMinor: 1850, margin: 38.0, velocity: -6.2, saturation: 4.8, lastSeen: "06:00 UTC" },
  { name: "Specimen 03", priceMinor: 12900, margin: 61.7, velocity: 0.02, saturation: 0, lastSeen: "06:00 UTC" },
  { name: "Specimen 04", priceMinor: 999, margin: null, velocity: 48.9, saturation: 11.2, lastSeen: "05:40 UTC" },
  { name: "Specimen 05", priceMinor: 3475, margin: 27.5, velocity: -0.8, saturation: -1.4, lastSeen: "Oct 21", stale: true },
  { name: "Specimen 06", priceMinor: 4200, margin: 51.2, velocity: 3.3, saturation: 2.1, lastSeen: "06:00 UTC" },
  { name: "Specimen 07", priceMinor: 1599, margin: 33.9, velocity: -14.6, saturation: -7.7, lastSeen: "06:00 UTC" },
  { name: "Specimen 08", priceMinor: 8800, margin: 45.0, velocity: 1.9, saturation: 0.6, lastSeen: "06:00 UTC" },
];
