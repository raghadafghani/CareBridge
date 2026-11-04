import { describe, expect, it } from "vitest";
import { datedVisits, daySchedule, doseInstruction, doseStops, stated } from "@/lib/plan-schedule";

describe("plan-schedule helpers", () => {
  it("recognizes stated vs unstated fields", () => {
    expect(stated("November 3, 2026")).toBe(true);
    expect(stated("Not stated")).toBe(false);
    expect(stated("")).toBe(false);
  });

  it("formats dose instructions with food notes and end dates", () => {
    const text = doseInstruction({
      name: "Amoxicillin-Clavulanate",
      dose: "875 mg tablet",
      purpose: "Antibiotic",
      times: ["08:00", "20:00"],
      until: "November 4, 2026",
      note: "Take with food.",
    });
    expect(text).toBe("Take 875 mg tablet, with food. Continue through November 4, 2026.");
  });

  it("maps clock times and meal labels into morning/evening schedule bands", () => {
    expect(doseStops(["08:00", "20:00"]).map((s) => s.label)).toEqual([
      "After breakfast",
      "After dinner",
    ]);
    expect(doseStops(["as needed, up to 4 times a day"])).toEqual([]);

    const schedule = daySchedule([
      {
        name: "Amoxicillin",
        dose: "875 mg",
        purpose: "Antibiotic",
        times: ["08:00", "20:00"],
        until: "Nov 4",
      },
      {
        name: "Paracetamol",
        dose: "500 mg",
        purpose: "Fever",
        times: ["as needed"],
        until: "As needed",
      },
    ]);
    expect(schedule.morning[0]?.label).toBe("After breakfast");
    expect(schedule.evening[0]?.label).toBe("After dinner");
    expect(schedule.untimed.map((m) => m.name)).toEqual(["Paracetamol"]);
  });

  it("parses calendar dates while ignoring relative phrases", () => {
    const visits = datedVisits([
      {
        date: "November 3, 2026",
        day: "Tuesday",
        title: "Primary care",
        who: "Dr. Khoury",
        time: "10:30",
      },
      {
        date: "In 2 to 3 weeks",
        day: "Not stated",
        title: "Follow-up",
        who: "Not stated",
        time: "Not stated",
      },
    ]);
    expect(visits).toHaveLength(1);
    expect(visits[0]?.title).toBe("Primary care");
    expect(visits[0]?.time).toBe("10:30");
  });
});
