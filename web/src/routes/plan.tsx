import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { loadActivePlan, type CarePlan } from "@/lib/care-api";

export const Route = createFileRoute("/plan")({
  head: () => ({
    meta: [
      { title: "Your care plan — CareBridge" },
      { name: "description", content: "Medication schedule, appointments, daily checklist and items to confirm with your doctor." },
      { property: "og:title", content: "Your care plan — CareBridge" },
      { property: "og:description", content: "A personalized post-discharge care plan." },
    ],
  }),
  component: Plan,
});

const card = "rounded-3xl border bg-card p-7";

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
  const [done, setDone] = useState<Set<number>>(new Set());
  const toggle = (i: number) => setDone((d) => { const n = new Set(d); n.has(i) ? n.delete(i) : n.add(i); return n; });

  if (status === "loading") {
    return <main className="mx-auto max-w-6xl px-6 py-14"><p className="text-muted-foreground">Loading the care plan from your latest discharge report…</p></main>;
  }
  if (status === "error") {
    return <main className="mx-auto max-w-6xl px-6 py-14"><p className="text-destructive">{loadError}</p></main>;
  }
  if (!plan) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-20">
        <h1 className="text-5xl">No care plan yet</h1>
        <p className="mt-4 text-muted-foreground">Upload a discharge report. The plan and the check-in agent are built from that document.</p>
        <Link to="/upload" className="mt-8 inline-flex rounded-full bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground">Upload a discharge report</Link>
      </main>
    );
  }

  const { patient, meds, appointments, checklist, flags, warnings } = plan;
  const pct = checklist.length === 0 ? 0 : Math.round((done.size / checklist.length) * 100);

  return (
    <main className="mx-auto max-w-6xl px-6 py-14">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <p className="text-xs uppercase tracking-wider text-muted-foreground">Care plan · {patient.hospital}</p>
          <h1 className="mt-2 text-5xl">{patient.name}</h1>
          <p className="mt-1 text-muted-foreground">Discharged {patient.discharged} · {patient.diagnosis}</p>
        </div>
        <div className="rounded-full bg-secondary px-4 py-2 text-sm text-secondary-foreground">{flags.length === 0 ? "Nothing to confirm" : `${flags.length} items need confirmation`}</div>
      </div>

      <section className="mt-10 rounded-3xl bg-ink p-8 text-ink-foreground">
        <p className="text-xs uppercase tracking-wider opacity-60">In plain words</p>
        <p className="mt-3 max-w-3xl font-display text-2xl leading-snug">{patient.plain}</p>
      </section>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <section className={`${card} lg:col-span-2`}>
          <h2 className="text-3xl">Medications</h2>
          <div className="mt-5 divide-y">
            {meds.map((m) => (
              <div key={m.name} className="grid gap-2 py-4 sm:grid-cols-[1fr_auto] sm:items-center">
                <div>
                  <p className="font-semibold">{m.name} <span className="font-normal text-muted-foreground">· {m.dose}</span></p>
                  <p className="text-sm text-muted-foreground">{m.purpose}{m.note && <span className="text-accent"> · {m.note}</span>}</p>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {m.times.map((t) => <span key={t} className="rounded-full bg-muted px-3 py-1 font-mono text-xs">{t}</span>)}
                  <span className="rounded-full border px-3 py-1 text-xs text-muted-foreground">until {m.until}</span>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className={card}>
          <h2 className="text-3xl">Appointments</h2>
          {appointments.length === 0 && <p className="mt-5 text-sm text-muted-foreground">No follow-up was written in this report.</p>}
          <ul className="mt-5 space-y-4">
            {appointments.map((a) => (
              <li key={a.title} className="flex gap-4">
                <div className="grid h-14 w-14 shrink-0 place-items-center rounded-2xl bg-secondary text-center text-secondary-foreground">
                  <div><p className="text-[10px] uppercase">{a.day || "Visit"}</p><p className="text-[11px] font-bold leading-tight">{a.date}</p></div>
                </div>
                <div>
                  <p className="font-semibold">{a.title}</p>
                  <p className="text-sm text-muted-foreground">{a.who} · {a.time}</p>
                </div>
              </li>
            ))}
          </ul>
        </section>

        <section className={card}>
          <div className="flex items-baseline justify-between">
            <h2 className="text-3xl">Today</h2>
            <span className="font-mono text-sm text-primary">{checklist.length === 0 ? "0 tasks" : `${done.size} of ${checklist.length}`}</span>
          </div>
          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted"><div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} /></div>
          {checklist.length === 0 && <p className="mt-5 text-sm text-muted-foreground">No daily tasks were written in this report.</p>}
          <ul className="mt-5 space-y-2">
            {checklist.map((c, i) => (
              <li key={c}>
                <button onClick={() => toggle(i)} className="flex w-full items-start gap-3 rounded-xl p-2 text-left text-sm hover:bg-muted">
                  <span className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-md border text-xs ${done.has(i) ? "border-primary bg-primary text-primary-foreground" : ""}`}>{done.has(i) && "✓"}</span>
                  <span className={done.has(i) ? "text-muted-foreground line-through" : ""}>{c}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className={`${card} lg:col-span-2`}>
          <h2 className="text-3xl">Ask your care team</h2>
          <p className="mt-1 text-sm text-muted-foreground">{flags.length === 0 ? "Nothing in this report was marked unclear or missing." : "Information in the report that is unclear, conflicting, or missing."}</p>
          <div className="mt-5 grid gap-3 sm:grid-cols-3">
            {flags.map((f) => (
              <div key={f.title} className="rounded-2xl bg-warning p-5 text-warning-foreground">
                <p className="text-[10px] font-bold uppercase tracking-wider">{f.level === "missing" ? "Missing" : "Confirm"}</p>
                <p className="mt-1 font-semibold">{f.title}</p>
                <p className="mt-2 text-sm opacity-80">{f.detail}</p>
              </div>
            ))}
          </div>
          <div className="mt-6 rounded-2xl border border-destructive/30 p-5">
            <p className="text-sm font-semibold text-destructive">Seek urgent care if you notice:</p>
            {warnings.length === 0 ? (
              <p className="mt-2 text-sm">This report does not list urgent warning signs. Ask your clinician what should send you back to care.</p>
            ) : (
              <ul className="mt-2 grid gap-1 text-sm sm:grid-cols-2">
                {warnings.map((w) => <li key={w}>— {w}</li>)}
              </ul>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
