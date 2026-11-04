import type { Medication } from "@/lib/care-api";

/** Homepage illustration only. A real plan comes from an uploaded discharge report. */

export const exampleMeds: Medication[] = [
  {
    name: "Amoxicillin-Clavulanate",
    dose: "875 mg tablet",
    purpose: "Antibiotic",
    times: ["08:00", "20:00"],
    until: "Nov 4",
  },
  {
    name: "Metoprolol",
    dose: "25 mg tablet",
    purpose: "Heart rate",
    times: ["08:00"],
    until: "Ongoing",
  },
  {
    name: "Paracetamol",
    dose: "500 mg, as needed",
    purpose: "Fever or discomfort",
    times: ["Up to 4×/day"],
    until: "As needed",
  },
];

export const exampleFlags = [
  {
    level: "confirm" as const,
    title: "Metoprolol duration not stated",
    detail: "Ask your doctor before stopping.",
  },
  {
    level: "confirm" as const,
    title: "Conflicting antibiotic dose",
    detail: "Two pages list different doses.",
  },
];
