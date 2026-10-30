import { createFileRoute, Link } from "@tanstack/react-router";
import { exampleFlags, exampleMeds } from "@/lib/example-plan";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "CareBridge — From discharge papers to a clear recovery plan" },
      { name: "description", content: "AI that turns hospital discharge reports into medication schedules, calendars, checklists and flags what needs a doctor's confirmation." },
      { property: "og:title", content: "CareBridge — AI Post-Discharge Care Assistant" },
      { property: "og:description", content: "Understand, organize, and follow your post-discharge care instructions." },
    ],
  }),
  component: Index,
});

const features = [
  ["01", "Plain-language explanations", "Medical jargon rewritten into sentences patients and caregivers actually understand."],
  ["02", "Medication schedules", "Every dose, timing and duration organized into a daily routine with reminders."],
  ["03", "Recovery calendar", "Follow-ups, tests and medication end-dates on one structured timeline."],
  ["04", "Home-care checklists", "Daily tasks and recovery instructions you can tick off as you go."],
  ["05", "Gap detection", "Unclear, conflicting or missing information flagged for a healthcare professional."],
];

function Index() {
  return (
    <main>
      <section className="relative overflow-hidden bg-hero">
        <div className="absolute inset-0 grid-lines opacity-40 [mask-image:radial-gradient(ellipse_at_center,black,transparent_70%)]" />
        <div className="relative mx-auto grid max-w-6xl gap-14 px-6 py-20 lg:grid-cols-[1.1fr_1fr] lg:py-28">
          <div>
            <span className="inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-xs text-muted-foreground">
              <span className="h-1.5 w-1.5 rounded-full bg-success" /> AI-powered post-discharge care
            </span>
            <h1 className="mt-6 text-5xl leading-[1.02] sm:text-7xl">
              Going home should feel <em className="text-primary">clear</em>, not confusing.
            </h1>
            <p className="mt-6 max-w-lg text-lg text-muted-foreground">
              CareBridge reads your hospital discharge report and builds a personalized care plan — medications, appointments, daily tasks, and what to double-check with your doctor.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/upload" className="rounded-full bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground shadow-soft hover:opacity-90">Upload a discharge report</Link>
              <Link to="/plan" className="rounded-full border bg-card px-6 py-3 text-sm font-semibold hover:bg-muted">Open your care plan →</Link>
            </div>
          </div>

          <div className="relative">
            <div className="rotate-[-2deg] rounded-3xl border bg-card p-6 shadow-soft">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>EXAMPLE LAYOUT</span><span className="rounded-full bg-secondary px-2 py-0.5 text-secondary-foreground">Not a patient record</span>
              </div>
              <svg viewBox="0 0 300 60" className="mt-4 h-14 w-full text-primary" fill="none" stroke="currentColor" strokeWidth="2">
                <path className="pulse-line" d="M0 30h90l10-20 15 40 15-30 10 10h160" />
              </svg>
              <ul className="mt-2 divide-y">
                {exampleMeds.map((m) => (
                  <li key={m.name} className="flex items-center justify-between py-3">
                    <div>
                      <p className="text-sm font-semibold">{m.name}</p>
                      <p className="text-xs text-muted-foreground">{m.dose}</p>
                    </div>
                    <span className="rounded-full bg-muted px-3 py-1 font-mono text-xs">{m.times[0]}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="absolute -bottom-6 -left-4 max-w-[260px] rotate-[3deg] rounded-2xl bg-warning p-4 text-warning-foreground shadow-soft">
              <p className="text-xs font-bold uppercase tracking-wider">Needs confirmation</p>
              <p className="mt-1 text-sm">{exampleFlags[1]?.title}</p>
            </div>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-6 py-24">
        <div className="grid gap-10 lg:grid-cols-[1fr_2fr]">
          <h2 className="text-4xl sm:text-5xl">One report in.<br /><em className="text-primary">A whole plan out.</em></h2>
          <div className="grid gap-px overflow-hidden rounded-3xl border bg-border sm:grid-cols-2">
            {features.map(([n, t, d]) => (
              <div key={n} className="bg-card p-7 transition-colors hover:bg-secondary/40">
                <span className="font-mono text-xs text-accent">{n}</span>
                <h3 className="mt-3 text-2xl">{t}</h3>
                <p className="mt-2 text-sm text-muted-foreground">{d}</p>
              </div>
            ))}
            <div className="flex flex-col justify-between bg-ink p-7 text-ink-foreground">
              <p className="text-xs uppercase tracking-wider opacity-70">Built with</p>
              <p className="font-display text-2xl">AWS Strands Agents SDK & AWS services</p>
            </div>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-6 pb-24">
        <div className="rounded-3xl bg-primary px-8 py-14 text-primary-foreground sm:px-14">
          <ol className="grid gap-10 sm:grid-cols-3">
            {[["Upload", "Drop in the PDF or photo of your discharge summary."], ["Understand", "Agents extract meds, appointments and instructions."], ["Follow", "Get a daily plan and a list of questions for your doctor."]].map(([t, d], i) => (
              <li key={t}>
                <span className="font-display text-6xl opacity-40">{i + 1}</span>
                <h3 className="mt-2 text-3xl">{t}</h3>
                <p className="mt-2 text-sm opacity-80">{d}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>
    </main>
  );
}
