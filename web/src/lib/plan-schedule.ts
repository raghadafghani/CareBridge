import type { CarePlan, Medication } from "@/lib/care-api";

export function stated(value: string | undefined) {
  const text = (value ?? "").trim();
  return text.length > 0 && !/^not stated$/i.test(text);
}

export function doseInstruction(med: Medication) {
  const food = (med.note ?? "")
    .replace(/^take\s+/i, "")
    .replace(/\.$/, "")
    .trim();
  let line = `Take ${med.dose.trim()}`;
  if (stated(food)) line += `, ${food.charAt(0).toLowerCase()}${food.slice(1)}`;
  line += ".";
  if (stated(med.until)) {
    const until = med.until.replace(/\.$/, "");
    line += /^(as needed|continue|ongoing)/i.test(until)
      ? ` ${until}.`
      : ` Continue through ${until}.`;
  }
  return line;
}

export type Visit = { date: Date; time: string; title: string; who: string };

export function datedVisits(appointments: CarePlan["appointments"]): Visit[] {
  const visits: Visit[] = [];
  for (const visit of appointments) {
    const parsed = Date.parse(visit.date);
    if (Number.isNaN(parsed)) continue;
    const value = new Date(parsed);
    visits.push({
      date: new Date(value.getFullYear(), value.getMonth(), value.getDate()),
      time: stated(visit.time) ? visit.time : "All day",
      title: visit.title,
      who: stated(visit.who) ? visit.who : "",
    });
  }
  return visits;
}

export function sameDay(left: Date, right: Date) {
  return (
    left.getFullYear() === right.getFullYear() &&
    left.getMonth() === right.getMonth() &&
    left.getDate() === right.getDate()
  );
}

export type MealStop = { label: string; band: "morning" | "evening"; order: number };

const MEAL_WORDS: [RegExp, MealStop][] = [
  [/\bbefore breakfast\b/i, { label: "Before breakfast", band: "morning", order: 0 }],
  [
    /\bafter breakfast\b|\bbreakfast\b|\bmorning\b/i,
    { label: "After breakfast", band: "morning", order: 1 },
  ],
  [/\bbefore lunch\b/i, { label: "Before lunch", band: "morning", order: 2 }],
  [
    /\bafter lunch\b|\blunch\b|\bafternoon\b|\bnoon\b|\bmidday\b/i,
    { label: "After lunch", band: "morning", order: 3 },
  ],
  [/\bbefore dinner\b/i, { label: "Before dinner", band: "evening", order: 4 }],
  [
    /\bafter dinner\b|\bdinner\b|\bsupper\b|\bevening\b/i,
    { label: "After dinner", band: "evening", order: 5 },
  ],
  [/\bbefore bed\b|\bbedtime\b|\bnight\b/i, { label: "Before bed", band: "evening", order: 6 }],
];

export function clockStops(text: string): MealStop[] {
  const stops: MealStop[] = [];
  for (const match of text.matchAll(/\b(\d{1,2}):(\d{2})\b/g)) {
    const minutes = Number(match[1]) * 60 + Number(match[2]);
    if (minutes < 10 * 60) stops.push({ label: "After breakfast", band: "morning", order: 1 });
    else if (minutes < 12 * 60) stops.push({ label: "Before lunch", band: "morning", order: 2 });
    else if (minutes < 16 * 60) stops.push({ label: "After lunch", band: "morning", order: 3 });
    else if (minutes < 18 * 60) stops.push({ label: "Before dinner", band: "evening", order: 4 });
    else if (minutes < 21 * 60) stops.push({ label: "After dinner", band: "evening", order: 5 });
    else stops.push({ label: "Before bed", band: "evening", order: 6 });
  }
  return stops;
}

export function doseStops(times: string[]): MealStop[] {
  const text = times.join(" ");
  if (
    /\bas needed\b|\bprn\b|\bup to\b/i.test(text) &&
    !/\b\d{1,2}:\d{2}\b/.test(text) &&
    !/\b(breakfast|lunch|dinner|evening|morning)\b/i.test(text)
  ) {
    return [];
  }
  const fromClocks = clockStops(text);
  if (fromClocks.length > 0) return fromClocks;
  const named: MealStop[] = [];
  let rest = text;
  for (const [pattern, stop] of MEAL_WORDS) {
    if (!pattern.test(rest)) continue;
    named.push(stop);
    rest = rest.replace(pattern, " ");
  }
  if (named.length > 0) return named;
  if (/\b(?:four times|4 times|qid)\b/i.test(text)) {
    return [
      { label: "After breakfast", band: "morning", order: 1 },
      { label: "After lunch", band: "morning", order: 3 },
      { label: "After dinner", band: "evening", order: 5 },
      { label: "Before bed", band: "evening", order: 6 },
    ];
  }
  if (/\b(?:three times|3 times|tid)\b/i.test(text)) {
    return [
      { label: "After breakfast", band: "morning", order: 1 },
      { label: "After lunch", band: "morning", order: 3 },
      { label: "After dinner", band: "evening", order: 5 },
    ];
  }
  if (/\b(?:twice|two times|2 times|bid)\b/i.test(text)) {
    return [
      { label: "After breakfast", band: "morning", order: 1 },
      { label: "After dinner", band: "evening", order: 5 },
    ];
  }
  if (/\b(?:once|one time|daily|every day)\b/i.test(text)) {
    return [{ label: "After breakfast", band: "morning", order: 1 }];
  }
  return [];
}

export function daySchedule(meds: Medication[]) {
  const placed: { stop: MealStop; med: Medication }[] = [];
  const untimed: Medication[] = [];
  for (const med of meds) {
    const stops = doseStops(med.times);
    if (stops.length === 0) {
      untimed.push(med);
      continue;
    }
    const seen = new Set<string>();
    for (const stop of stops) {
      if (seen.has(stop.label)) continue;
      seen.add(stop.label);
      placed.push({ stop, med });
    }
  }
  const line = (band: "morning" | "evening") => {
    const labels = [
      ...new Set(placed.filter((item) => item.stop.band === band).map((item) => item.stop.label)),
    ];
    return labels
      .sort((a, b) => {
        const left = placed.find((item) => item.stop.label === a)?.stop.order ?? 0;
        const right = placed.find((item) => item.stop.label === b)?.stop.order ?? 0;
        return left - right;
      })
      .map((label) => ({
        label,
        meds: placed.filter((item) => item.stop.label === label).map((item) => item.med),
      }));
  };
  return { morning: line("morning"), evening: line("evening"), untimed };
}
