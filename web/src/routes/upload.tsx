import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { uploadDischarge } from "@/lib/care-api";

export const Route = createFileRoute("/upload")({
  head: () => ({
    meta: [
      { title: "Upload discharge report — CareBridge" },
      { name: "description", content: "Upload a hospital discharge report and let CareBridge build your care plan." },
      { property: "og:title", content: "Upload discharge report — CareBridge" },
      { property: "og:description", content: "Turn your discharge papers into a personalized care plan." },
    ],
  }),
  component: Upload,
});

function Upload() {
  const [file, setFile] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onFile = (selected: File | undefined) => {
    if (!selected || busy) return;
    setError(null);
    setDone(false);
    setFile(selected.name);
    setBusy(true);
    void uploadDischarge(selected)
      .then(() => setDone(true))
      .catch((exc: unknown) => {
        setFile(null);
        setError(exc instanceof Error ? exc.message : "The report could not be read.");
      })
      .finally(() => setBusy(false));
  };

  return (
    <main className="mx-auto max-w-3xl px-6 py-20">
      <h1 className="text-5xl">Upload your <em className="text-primary">discharge report</em></h1>
      <p className="mt-4 text-muted-foreground">PDF, image, or text. CareBridge reads that document and builds the care plan from it.</p>

      <label className="mt-10 flex cursor-pointer flex-col items-center justify-center rounded-3xl border-2 border-dashed bg-card p-14 text-center transition-colors hover:border-primary hover:bg-secondary/30">
        <input
          type="file"
          className="hidden"
          accept=".pdf,image/*,.txt"
          disabled={busy}
          onChange={(e) => {
            const selected = e.target.files?.[0];
            e.target.value = "";
            onFile(selected);
          }}
        />
        <span className="grid h-14 w-14 place-items-center rounded-full bg-secondary text-2xl text-secondary-foreground">↑</span>
        <p className="mt-4 font-semibold">{file ?? "Drop a file or click to browse"}</p>
        <p className="mt-1 text-xs text-muted-foreground">Up to 20 MB</p>
      </label>

      {error && <p className="mt-6 text-sm text-destructive">{error}</p>}

      {busy && (
        <div className="mt-10 rounded-3xl border bg-card p-8 shadow-soft">
          <p className="font-semibold">Reading {file}</p>
          <p className="mt-2 text-sm text-muted-foreground">
            The discharge agent is extracting medications, appointments, and home-care instructions. This usually takes under a minute.
          </p>
        </div>
      )}

      {done && (
        <div className="mt-10 rounded-3xl border bg-card p-8 shadow-soft">
          <p className="font-semibold">Care plan ready</p>
          <p className="mt-2 text-sm text-muted-foreground">Built from {file}. The check-in agent will use this plan.</p>
          <Link to="/plan" className="mt-8 inline-flex rounded-full bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground">View your care plan →</Link>
        </div>
      )}
    </main>
  );
}
