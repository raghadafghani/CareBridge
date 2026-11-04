import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { loadActivePlan, postCheckIn, type CarePlan } from "@/lib/care-api";

export const Route = createFileRoute("/check-in")({
  head: () => ({
    meta: [
      { title: "Health check-in agent — CareBridge" },
      {
        name: "description",
        content:
          "Report changes in your condition by text or voice. CareBridge compares them with your discharge instructions.",
      },
      { property: "og:title", content: "Health check-in agent — CareBridge" },
      {
        property: "og:description",
        content: "An AI follow-up agent that knows your discharge instructions.",
      },
    ],
  }),
  component: CheckIn,
});

type Outcome = "monitor" | "review" | "emergency";
type Msg = {
  from: "you" | "agent";
  text: string;
  questions?: string[];
  outcome?: Outcome;
  summary?: string;
};

const examples = [
  "My temperature is 38.5°C. It was 37°C yesterday. Is this normal?",
  "I have more pain than yesterday.",
  "I forgot to take my medication.",
  "The area around my wound looks red.",
  "I feel dizzy after taking my medication.",
];

const outcomeMeta: Record<Outcome, { label: string; tone: string; desc: string }> = {
  monitor: {
    label: "No concerning signs identified",
    tone: "bg-secondary text-secondary-foreground",
    desc: "Explains what your instructions say and reminds you to keep monitoring.",
  },
  review: {
    label: "Needs medical review",
    tone: "bg-warning text-warning-foreground",
    desc: "Recommends contacting your care team and prepares a symptom summary.",
  },
  emergency: {
    label: "Potential emergency",
    tone: "bg-destructive text-destructive-foreground",
    desc: "Directs you to urgent care immediately, with no further questions.",
  },
};

function greeting(plan: CarePlan) {
  return `Hello ${plan.patient.name.split(" ")[0]}. I'm your CareBridge follow-up agent. Tell me how you're feeling today, or report any change since yesterday.`;
}

function CheckIn() {
  const [plan, setPlan] = useState<CarePlan | null>(null);
  const [status, setStatus] = useState<"loading" | "empty" | "ready" | "error">("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  useEffect(() => {
    let cancelled = false;
    loadActivePlan()
      .then((loaded) => {
        if (cancelled) return;
        setPlan(loaded);
        setStatus(loaded ? "ready" : "empty");
        if (loaded) setMsgs([{ from: "agent", text: greeting(loaded) }]);
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
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const [listening, setListening] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [msgs, typing]);

  const pending = msgs[msgs.length - 1]?.questions !== undefined;
  const latest = [...msgs].reverse().find((m) => m.outcome)?.outcome;
  const summary = [...msgs].reverse().find((m) => m.summary)?.summary;
  const reported = msgs.filter((m) => m.from === "you").map((m) => m.text);

  const send = (text: string) => {
    const t = text.trim();
    if (!t || typing) return;
    if (!plan) return;
    setMsgs((m) => [...m, { from: "you", text: t }]);
    setInput("");
    setTyping(true);
    postCheckIn(plan.id, t)
      .then((reply) => {
        const next: Msg = { from: "agent", text: reply.text };
        if (reply.outcome) next.outcome = reply.outcome;
        if (reply.questions && reply.questions.length > 0) next.questions = reply.questions;
        if (reply.summary) next.summary = reply.summary;
        setMsgs((m) => [...m, next]);
      })
      .catch((exc: unknown) => {
        setMsgs((m) => [
          ...m,
          {
            from: "agent",
            text: exc instanceof Error ? exc.message : "The check-in agent could not be reached.",
          },
        ]);
      })
      .finally(() => {
        setTyping(false);
        inputRef.current?.focus();
      });
  };

  const voice = () => {
    type SpeechResultEvent = { results: ArrayLike<ArrayLike<{ transcript: string }>> };
    type SpeechRecognizer = {
      lang: string;
      onresult: ((event: SpeechResultEvent) => void) | null;
      onend: (() => void) | null;
      start: () => void;
    };
    type SpeechWindow = {
      SpeechRecognition?: new () => SpeechRecognizer;
      webkitSpeechRecognition?: new () => SpeechRecognizer;
    };
    const W = window as unknown as SpeechWindow;
    const SR = W.SpeechRecognition || W.webkitSpeechRecognition;
    if (!SR) {
      alert("Voice input isn't supported in this browser.");
      return;
    }
    const r = new SR();
    r.lang = "en-US";
    r.onresult = (e: SpeechResultEvent) => setInput(e.results[0][0].transcript);
    r.onend = () => setListening(false);
    setListening(true);
    r.start();
  };

  if (status === "loading") {
    return (
      <main className="mx-auto max-w-6xl px-6 py-14">
        <p className="text-muted-foreground">Loading your discharge plan for the check-in agent…</p>
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
        <h1 className="text-5xl">Upload a report first</h1>
        <p className="mt-4 text-muted-foreground">
          The check-in agent answers from the discharge report you upload. It does not use a
          built-in patient.
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

  return (
    <main className="mx-auto max-w-6xl px-6 py-14">
      <p className="text-xs uppercase tracking-wider text-muted-foreground">
        Follow-up agent · {plan.patient.diagnosis}
      </p>
      <h1 className="mt-2 text-5xl">How are you feeling today?</h1>
      <p className="mt-2 max-w-2xl text-muted-foreground">
        Report any change in your condition by text or voice. CareBridge compares it with your
        discharge instructions and tells you what to do next.
      </p>

      <div className="mt-10 grid gap-6 lg:grid-cols-[1fr_340px]">
        <section className="flex h-[640px] flex-col overflow-hidden rounded-3xl border bg-card shadow-soft">
          <div className="flex items-center gap-3 border-b px-6 py-4">
            <span className="grid h-10 w-10 place-items-center rounded-full bg-primary text-primary-foreground">
              <svg
                viewBox="0 0 24 24"
                className="h-5 w-5"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path d="M3 12h4l2-5 4 10 2-5h6" />
              </svg>
            </span>
            <div className="flex-1">
              <p className="font-semibold">CareBridge Agent</p>
              <p className="text-xs text-muted-foreground">
                Reads your discharge plan from {plan.patient.hospital}
              </p>
            </div>
            <span className="flex items-center gap-1.5 text-xs text-success">
              <span className="h-2 w-2 rounded-full bg-success" />
              Online
            </span>
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto px-6 py-6">
            {msgs.map((m, i) => (
              <div key={i} className={m.from === "you" ? "flex justify-end" : ""}>
                {m.from === "you" ? (
                  <p className="max-w-[80%] rounded-2xl rounded-br-md bg-ink px-4 py-3 text-sm text-ink-foreground">
                    {m.text}
                  </p>
                ) : (
                  <div className="max-w-[85%] text-sm leading-relaxed">
                    {m.outcome && (
                      <span
                        className={`mb-2 inline-block rounded-full px-3 py-1 text-[11px] font-bold uppercase tracking-wider ${outcomeMeta[m.outcome].tone}`}
                      >
                        {outcomeMeta[m.outcome].label}
                      </span>
                    )}
                    <p>{m.text}</p>
                    {m.questions && (
                      <ol className="mt-3 space-y-1.5">
                        {m.questions.map((q, j) => (
                          <li key={q} className="flex gap-3 rounded-xl bg-muted px-3 py-2">
                            <span className="font-mono text-xs text-primary">{j + 1}</span>
                            {q}
                          </li>
                        ))}
                      </ol>
                    )}
                    {m.outcome === "emergency" && (
                      <a
                        href="tel:112"
                        className="mt-3 inline-flex rounded-full bg-destructive px-5 py-2 text-sm font-semibold text-destructive-foreground"
                      >
                        Call emergency services
                      </a>
                    )}
                  </div>
                )}
              </div>
            ))}
            {typing && (
              <div className="flex gap-1 py-2">
                {[0, 1, 2].map((d) => (
                  <span
                    key={d}
                    className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground/50"
                    style={{ animationDelay: `${d * 120}ms` }}
                  />
                ))}
              </div>
            )}
            <div ref={endRef} />
          </div>

          {msgs.length === 1 && (
            <div className="flex flex-wrap gap-2 px-6 pb-3">
              {examples.map((e) => (
                <button
                  key={e}
                  onClick={() => send(e)}
                  className="rounded-full border px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
                >
                  {e}
                </button>
              ))}
            </div>
          )}

          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
            className="border-t p-4"
          >
            <div className="flex items-end gap-2 rounded-2xl border bg-background p-2 focus-within:ring-2 focus-within:ring-ring">
              <textarea
                ref={inputRef}
                autoFocus
                rows={1}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send(input);
                  }
                }}
                placeholder={pending ? "Answer the questions above…" : "Describe how you feel…"}
                className="max-h-32 flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none"
              />
              <button
                type="button"
                onClick={voice}
                aria-label="Speak"
                className={`grid h-10 w-10 place-items-center rounded-full ${listening ? "bg-accent text-accent-foreground animate-pulse" : "bg-muted text-foreground hover:bg-secondary"}`}
              >
                <svg
                  viewBox="0 0 24 24"
                  className="h-4 w-4"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <rect x="9" y="3" width="6" height="11" rx="3" />
                  <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
                </svg>
              </button>
              <button
                type="submit"
                aria-label="Send"
                disabled={!input.trim() || typing}
                className="grid h-10 w-10 place-items-center rounded-full bg-primary text-primary-foreground disabled:opacity-40"
              >
                <svg
                  viewBox="0 0 24 24"
                  className="h-4 w-4"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <path d="M5 12h14M13 6l6 6-6 6" />
                </svg>
              </button>
            </div>
            <p className="mt-2 text-center text-[11px] text-muted-foreground">
              Connected to the CareBridge agent. Not a medical assessment. In an emergency, call
              your local emergency number.
            </p>
          </form>
        </section>

        <aside className="space-y-6">
          <div className="rounded-3xl border bg-card p-6">
            <h2 className="text-2xl">Possible outcomes</h2>
            <ul className="mt-4 space-y-3">
              {(Object.keys(outcomeMeta) as Outcome[]).map((k, i) => (
                <li
                  key={k}
                  className={`rounded-2xl p-4 transition ${latest === k ? `${outcomeMeta[k].tone} ring-2 ring-ring` : "bg-muted"}`}
                >
                  <p className="text-sm font-semibold">
                    <span className="mr-2 font-mono opacity-60">{i + 1}</span>
                    {outcomeMeta[k].label}
                  </p>
                  <p className="mt-1 text-xs opacity-80">{outcomeMeta[k].desc}</p>
                </li>
              ))}
            </ul>
          </div>

          {latest === "review" && (
            <div className="rounded-3xl bg-ink p-6 text-ink-foreground">
              <p className="text-xs uppercase tracking-wider opacity-60">Summary for care team</p>
              {summary ? (
                <p className="mt-2 whitespace-pre-wrap text-sm">{summary}</p>
              ) : (
                <>
                  <p className="mt-2 text-sm">
                    {plan.patient.name} · discharged {plan.patient.discharged} ·{" "}
                    {plan.patient.diagnosis}
                  </p>
                  <ul className="mt-3 space-y-1 text-sm">
                    {reported.map((r) => (
                      <li key={r}>— {r}</li>
                    ))}
                  </ul>
                  <p className="mt-3 text-xs opacity-60">
                    Current meds: {plan.meds.map((m) => m.name).join(", ")}
                  </p>
                </>
              )}
              <button
                onClick={() => navigator.clipboard?.writeText(summary || reported.join("\n"))}
                className="mt-4 rounded-full bg-ink-foreground px-4 py-2 text-xs font-semibold text-ink"
              >
                Copy summary
              </button>
            </div>
          )}

          <div className="rounded-3xl border border-destructive/30 p-6">
            <p className="text-sm font-semibold text-destructive">Safety rules</p>
            <ul className="mt-2 space-y-1.5 text-xs text-muted-foreground">
              <li>— The agent never diagnoses or declares a symptom normal.</li>
              <li>— It never changes medication doses.</li>
              <li>— Escalation rules are set by clinicians, not by the AI.</li>
            </ul>
            <p className="mt-4 text-xs font-semibold">Go to urgent care for:</p>
            <ul className="mt-1 space-y-1 text-xs text-muted-foreground">
              {plan.warnings.map((w) => (
                <li key={w}>— {w}</li>
              ))}
            </ul>
          </div>
        </aside>
      </div>
    </main>
  );
}
