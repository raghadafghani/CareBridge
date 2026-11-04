import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { uploadDischarge } from "@/lib/care-api";

export const Route = createFileRoute("/upload")({
  head: () => ({
    meta: [
      { title: "Upload discharge report — CareBridge" },
      {
        name: "description",
        content: "Upload a hospital discharge report and let CareBridge build your care plan.",
      },
      { property: "og:title", content: "Upload discharge report — CareBridge" },
      {
        property: "og:description",
        content: "Turn your discharge papers into a personalized care plan.",
      },
    ],
  }),
  component: Upload,
});

type Preview = { name: string; url: string; kind: "pdf" | "image" | "text"; text?: string };

function Upload() {
  const [file, setFile] = useState<string | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    return () => {
      if (preview?.url) URL.revokeObjectURL(preview.url);
    };
  }, [preview]);

  const onFile = (selected: File | undefined) => {
    if (!selected || busy) return;
    setError(null);
    setDone(false);
    setFile(selected.name);
    const kind =
      selected.type === "application/pdf" || selected.name.toLowerCase().endsWith(".pdf")
        ? "pdf"
        : selected.type.startsWith("image/")
          ? "image"
          : "text";
    const url = URL.createObjectURL(selected);
    const next: Preview = { name: selected.name, url, kind };
    setPreview(next);
    if (kind === "text") {
      void selected.text().then((text) => {
        setPreview((current) => (current?.url === url ? { ...current, text } : current));
      });
    }
    setBusy(true);
    void uploadDischarge(selected)
      .then(() => setDone(true))
      .catch((exc: unknown) => {
        setError(exc instanceof Error ? exc.message : "The report could not be read.");
      })
      .finally(() => setBusy(false));
  };

  return (
    <main className="mx-auto max-w-3xl px-6 py-20">
      <h1 className="text-5xl">
        Upload your <em className="text-primary">discharge report</em>
      </h1>
      <p className="mt-4 text-muted-foreground">
        PDF, image, or text. CareBridge reads that document and builds the care plan from it.
      </p>

      {preview && (busy || done) ? (
        <div className="mt-10">
          <div className="rounded-3xl bg-ink p-4 shadow-soft sm:p-5">
            <div className="relative h-[32rem] overflow-hidden rounded-md bg-white">
              {preview.kind === "pdf" && (
                <iframe
                  title={preview.name}
                  src={`${preview.url}#toolbar=0&navpanes=0&scrollbar=0&view=FitH`}
                  className="relative z-0 h-full w-full bg-white"
                />
              )}
              {preview.kind === "image" && (
                <img
                  src={preview.url}
                  alt={preview.name}
                  className="h-full w-full object-contain"
                />
              )}
              {preview.kind === "text" && (
                <pre className="h-full overflow-hidden whitespace-pre-wrap p-6 text-xs leading-relaxed text-ink">
                  {preview.text ?? ""}
                </pre>
              )}
              {busy && (
                <div
                  className="scan-bar pointer-events-none absolute inset-x-0 z-10 h-16"
                  aria-hidden="true"
                >
                  <div className="h-0.5 w-full bg-primary shadow-[0_0_18px_6px_var(--color-primary)]" />
                  <div className="h-16 bg-gradient-to-b from-primary/30 to-transparent" />
                </div>
              )}
            </div>
          </div>
          <p className="mt-4 font-semibold">{busy ? `Scanning ${file}` : file}</p>
          <p className="mt-1 text-sm text-muted-foreground">
            {busy
              ? "The discharge agent is reading medications, appointments, and home-care instructions."
              : "Scan finished. The care plan is ready."}
          </p>
        </div>
      ) : (
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
          <span className="grid h-14 w-14 place-items-center rounded-full bg-secondary text-2xl text-secondary-foreground">
            ↑
          </span>
          <p className="mt-4 font-semibold">{file ?? "Drop a file or click to browse"}</p>
          <p className="mt-1 text-xs text-muted-foreground">Up to 20 MB</p>
        </label>
      )}

      {error && <p className="mt-6 text-sm text-destructive">{error}</p>}

      {done && (
        <div className="mt-10 rounded-3xl border bg-card p-8 shadow-soft">
          <p className="font-semibold">Care plan ready</p>
          <p className="mt-2 text-sm text-muted-foreground">
            Built from {file}. The check-in agent will use this plan.
          </p>
          <Link
            to="/plan"
            className="mt-8 inline-flex rounded-full bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground"
          >
            View your care plan →
          </Link>
        </div>
      )}
    </main>
  );
}
