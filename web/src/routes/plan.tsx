import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { AppointmentCalendar } from "@/components/appointment-calendar";
import {
  calendarConnectUrl,
  calendarStatus,
  disconnectCalendar,
  loadActivePlan,
  pushAppointments,
  type CalendarStatus,
  type CarePlan,
} from "@/lib/care-api";
import { daySchedule, doseInstruction, stated } from "@/lib/plan-schedule";

export const Route = createFileRoute("/plan")({
  head: () => ({
    meta: [
      { title: "Your care plan — CareBridge" },
      {
        name: "description",
        content:
          "Medication schedule, appointments, daily checklist and items to confirm with your doctor.",
      },
      { property: "og:title", content: "Your care plan — CareBridge" },
      { property: "og:description", content: "A personalized post-discharge care plan." },
    ],
  }),
  component: Plan,
});

const label = "text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground";

function Plan() {
  const [plan, setPlan] = useState<CarePlan | null>(null);
  const [status, setStatus] = useState<"loading" | "empty" | "ready" | "error">("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    loadActivePlan()
      .then((loaded) => {
        if (cancelled) return;
        setPlan(loaded);
        setStatus(loaded ? "ready" : "empty");
      })
      .catch((exc: unknown) => {
        if (cancelled) return;
        setLoadError(exc instanceof Error ? exc.message : "The care plan could not be loaded.");
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);
  const [calendar, setCalendar] = useState<(CalendarStatus & { note: string }) | null>(null);
  const [syncing, setSyncing] = useState(false);
  useEffect(() => {
    let cancelled = false;
    calendarStatus()
      .then((loaded) => {
        if (cancelled) return;
        const flag = new URLSearchParams(window.location.search).get("calendar");
        const notes: Record<string, string> = {
          setup: "Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET, then connect again.",
          denied: "Google sign-in was cancelled.",
          error: "Google sign-in did not finish. Try connecting again.",
          connected: "Google Calendar is connected. Send the visits when you are ready.",
        };
        setCalendar({ ...loaded, note: flag ? (notes[flag] ?? "") : "" });
      })
      .catch(() => {
        if (!cancelled) setCalendar({ configured: false, connected: false, note: "" });
      });
    return () => {
      cancelled = true;
    };
  }, []);
  const connectGoogle = () => {
    if (!calendar?.configured) {
      setCalendar({
        configured: false,
        connected: false,
        note: "Create a Google Cloud OAuth client and set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET. Redirect URI: http://127.0.0.1:8787/v1/calendar/callback.",
      });
      return;
    }
    window.location.href = calendarConnectUrl();
  };
  const sendVisits = async () => {
    if (!plan) return;
    setSyncing(true);
    try {
      const result = await pushAppointments(plan.id);
      const count = result.added + result.updated;
      setCalendar(
        (current) =>
          current && {
            ...current,
            note: `Sent ${count} visit${count === 1 ? "" : "s"} to Google Calendar.`,
          },
      );
    } catch (exc: unknown) {
      const message = exc instanceof Error ? exc.message : "The visits could not be sent.";
      setCalendar((current) => current && { ...current, note: message });
    } finally {
      setSyncing(false);
    }
  };
  const disconnectGoogle = async () => {
    try {
      await disconnectCalendar();
      setCalendar((current) => ({
        configured: current?.configured ?? false,
        connected: false,
        note: "Google Calendar disconnected.",
      }));
    } catch (exc: unknown) {
      const message = exc instanceof Error ? exc.message : "Could not disconnect Google Calendar.";
      setCalendar((current) => current && { ...current, note: message });
    }
  };
  const [done, setDone] = useState<Set<number>>(new Set());
  const toggle = (i: number) =>
    setDone((current) => {
      const next = new Set(current);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });

  if (status === "loading") {
    return (
      <main className="mx-auto max-w-6xl px-6 py-14">
        <p className="text-muted-foreground">
          Loading the care plan from your latest discharge report…
        </p>
      </main>
    );
  }
  if (status === "error") {
    return (
      <main className="mx-auto max-w-6xl px-6 py-14">
        <p className="text-destructive">{loadError}</p>
      </main>
    );
  }
  if (!plan) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-20">
        <h1 className="text-5xl">No care plan yet</h1>
        <p className="mt-4 text-muted-foreground">
          Upload a discharge report. The plan and the check-in agent are built from that document.
        </p>
        <Link
          to="/upload"
          className="mt-8 inline-flex rounded-full bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground"
        >
          Upload a discharge report
        </Link>
      </main>
    );
  }

  const { patient, meds, appointments, checklist, flags, warnings } = plan;
  const schedule = daySchedule(meds);
  const pct = checklist.length === 0 ? 0 : Math.round((done.size / checklist.length) * 100);
  const confirm = flags.filter((flag) => flag.level === "confirm");
  const missing = flags.filter((flag) => flag.level === "missing");

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b pb-6">
        <div>
          <p className={label}>{patient.hospital}</p>
          <h1 className="mt-1 text-4xl leading-tight">{patient.name}</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Discharged {patient.discharged} · {patient.diagnosis}
          </p>
        </div>
        <Link
          to="/check-in"
          className="rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground"
        >
          Check in
        </Link>
      </header>

      <div className="mt-6 space-y-6">
        <p className="max-w-3xl border-l-2 border-primary pl-4 text-lg leading-relaxed">
          {patient.plain}
        </p>

        <div className="grid items-stretch gap-6 lg:grid-cols-2">
          <section className="rounded-2xl border bg-card p-5">
            <h2 className="font-display text-2xl">Today's medicines</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Each line is a time of day. Take the medicines named beside that meal.
            </p>
            <div className="mt-5 grid gap-6">
              {(
                [
                  ["Morning", schedule.morning, false],
                  ["Evening", schedule.evening, true],
                ] as const
              ).map(([name, stops, dashed]) => (
                <div key={name}>
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">
                    {name}
                  </p>
                  {stops.length === 0 ? (
                    <p className="mt-3 text-sm text-muted-foreground">Nothing scheduled.</p>
                  ) : (
                    <ol
                      className={`mt-4 border-l-2 border-primary/35 pl-5 ${dashed ? "border-dashed" : ""}`}
                    >
                      {stops.map((stop) => (
                        <li key={stop.label} className="relative pb-4 last:pb-0">
                          <span className="absolute -left-[1.45rem] top-1.5 h-2.5 w-2.5 rounded-full bg-primary ring-4 ring-card" />
                          <p className="text-base font-semibold text-primary">{stop.label}</p>
                          <ul className="mt-2 space-y-3">
                            {stop.meds.map((med) => (
                              <li key={med.name}>
                                <p className="font-semibold">{med.name}</p>
                                <p className="text-sm text-muted-foreground">
                                  {doseInstruction(med)}
                                </p>
                              </li>
                            ))}
                          </ul>
                        </li>
                      ))}
                    </ol>
                  )}
                </div>
              ))}
            </div>
            {schedule.untimed.length > 0 && (
              <div className="mt-6 border-t pt-5">
                <p className={label}>As needed</p>
                <ul className="mt-3 grid gap-3 sm:grid-cols-2">
                  {schedule.untimed.map((med) => (
                    <li key={med.name}>
                      <p className="font-semibold">{med.name}</p>
                      <p className="text-sm text-muted-foreground">
                        {med.dose}{" "}
                        {med.purpose.trim().replace(/^./, (letter) => letter.toLowerCase())}.
                        {stated(med.until) ? ` ${med.until.replace(/\.$/, "")}.` : ""}
                        {stated(med.note) ? ` ${med.note}` : ""}
                      </p>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          <section className="rounded-2xl border bg-card p-5">
            <div className="flex items-baseline justify-between gap-4">
              <h2 className="font-display text-2xl">Today's tasks</h2>
              <span className="font-mono text-xs text-primary">
                {checklist.length === 0 ? "0 tasks" : `${done.size} of ${checklist.length}`}
              </span>
            </div>
            <div className="mt-3 h-1 overflow-hidden rounded-full bg-muted">
              <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
            </div>
            {checklist.length === 0 && (
              <p className="mt-4 text-sm text-muted-foreground">
                No daily tasks were written in this report.
              </p>
            )}
            <ul className="mt-4 grid gap-1">
              {checklist.map((item, index) => (
                <li key={item}>
                  <button
                    onClick={() => toggle(index)}
                    className="flex w-full items-start gap-3 rounded-lg px-1 py-1.5 text-left text-sm hover:bg-muted"
                  >
                    <span
                      className={`mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded border text-[10px] ${done.has(index) ? "border-primary bg-primary text-primary-foreground" : ""}`}
                    >
                      {done.has(index) ? "✓" : ""}
                    </span>
                    <span className={done.has(index) ? "text-muted-foreground line-through" : ""}>
                      {item}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        </div>

        <div className="grid items-start gap-6 lg:grid-cols-2">
          <AppointmentCalendar
            appointments={appointments}
            calendar={calendar}
            syncing={syncing}
            onConnect={connectGoogle}
            onDisconnect={() => {
              void disconnectGoogle();
            }}
            onSync={() => {
              void sendVisits();
            }}
          />

          {(confirm.length > 0 || missing.length > 0) && (
            <section className="rounded-2xl border bg-card p-5">
              <h2 className="font-display text-2xl">Questions for your care team</h2>
              <ul className="mt-4 divide-y">
                {[...confirm, ...missing].map((flag) => (
                  <li key={flag.title} className="grid gap-2 py-4 sm:grid-cols-[7rem_1fr] sm:gap-6">
                    <p
                      className={`text-[11px] font-semibold uppercase tracking-wider ${flag.level === "missing" ? "text-muted-foreground" : "text-warning-foreground"}`}
                    >
                      {flag.level === "missing" ? "Missing" : "Confirm"}
                    </p>
                    <div>
                      <p className="font-semibold">{flag.title}</p>
                      <p className="mt-1 text-sm text-muted-foreground">{flag.detail}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>

        <section className="rounded-2xl bg-destructive px-6 py-5 text-destructive-foreground">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em]">
            Seek urgent care if you notice
          </p>
          {warnings.length === 0 ? (
            <p className="mt-2 text-sm">
              This report does not list urgent warning signs. Ask your clinician what should send
              you back to care.
            </p>
          ) : (
            <ul className="mt-3 grid gap-1 text-sm sm:grid-cols-2">
              {warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </main>
  );
}
