import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import {
  describeError,
  getEpicSandboxStatus,
  importEpicSandboxNotes,
  pushNotes,
  uploadNotes,
  type EpicSandboxStatus,
  type ReceiveOutcome,
} from "../../api";
import { Banner, Button, Card, TextArea, TextField } from "../../components";

// What the inbox shows once it's done: see InboxPage's ReceivedBanner.
export interface ReceivedSummary {
  received: number;
  duplicates: number;
}

function summarize(outcomes: ReceiveOutcome[]): ReceivedSummary {
  const duplicates = outcomes.filter((o) => o.outcome === "duplicate").length;
  return { received: outcomes.length - duplicates, duplicates };
}

type Mode = "paste" | "upload" | "epic";

const modeTabClasses =
  "cursor-pointer rounded-lg border border-border bg-card px-4 py-2 text-sm text-foreground hover:border-primary";

// Notes that come from nowhere automated: pasted, or a .txt/.md file. A whole ER shift can
// go in at once — the server splits it into one note per `**NAM :**` header. Each note goes
// through intake like any other (patient matched by NAM, extraction queued), then the
// physician carries on from the inbox. With the backend's Epic sandbox demo on, a third tab
// pulls the sandbox patients' signed notes instead.
export default function AddNotesPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode>("paste");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [batchLabel, setBatchLabel] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [epicSandbox, setEpicSandbox] = useState<EpicSandboxStatus | null>(null);

  useEffect(() => {
    // Off (a 404) or unreachable: the tab just stays hidden.
    getEpicSandboxStatus()
      .then(setEpicSandbox)
      .catch(() => setEpicSandbox(null));
  }, []);

  const ready = mode === "paste" ? text.trim().length > 0 : file !== null;

  async function handleEpicImport() {
    setSending(true);
    setError(null);
    try {
      const outcomes = await importEpicSandboxNotes();
      // Epic's seeded notes date from 2006–2023: the default period (recent days) would hide
      // them, so land on every date, filtered to this source.
      navigate("/app/inbox?all=1&source=epic_sandbox", { state: { received: summarize(outcomes) } });
    } catch (err) {
      setError(describeError(err));
      setSending(false);
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!ready) return;
    setSending(true);
    setError(null);
    const label = batchLabel.trim() || null;
    try {
      const outcomes =
        mode === "paste" ? await pushNotes({ text, batch_label: label }) : await uploadNotes(file as File, label);
      navigate("/app/inbox", { state: { received: summarize(outcomes) } });
    } catch (err) {
      setError(describeError(err));
      setSending(false);
    }
  }

  return (
    <section className="max-w-[860px]">
      <h1 className="font-heading text-2xl font-semibold">Ajouter manuellement</h1>
      <p className="mt-2 mb-6 text-sm text-muted-foreground">
        Collez une ou plusieurs notes signées, ou téléversez un fichier. Chaque note commençant par un en-tête
        &laquo; **NAM :** &raquo; devient une rencontre dans la boîte de réception.
      </p>

      <div className="mb-4 flex gap-2" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={mode === "paste"}
          className={cn(modeTabClasses, mode === "paste" && "border-primary bg-[color:var(--color-primary-tint)]")}
          onClick={() => setMode("paste")}
        >
          Coller
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === "upload"}
          className={cn(modeTabClasses, mode === "upload" && "border-primary bg-[color:var(--color-primary-tint)]")}
          onClick={() => setMode("upload")}
        >
          Téléverser un fichier
        </button>
        {epicSandbox && (
          <button
            type="button"
            role="tab"
            aria-selected={mode === "epic"}
            className={cn(modeTabClasses, mode === "epic" && "border-primary bg-[color:var(--color-primary-tint)]")}
            onClick={() => setMode("epic")}
          >
            Epic — démo (sandbox)
          </button>
        )}
      </div>

      {mode === "epic" && epicSandbox ? (
        <Card className="gap-4 p-6">
          <p className="text-sm text-muted-foreground">
            Importe une sélection de notes signées des {epicSandbox.patients} patients fictifs du bac à sable
            d&apos;Epic (fhir.epic.com). Ces notes sont en anglais, de style américain et datées de 2006 à 2023 :
            elles montrent le parcours complet Epic → boîte de réception → codes, pas la qualité des codes sur une
            vraie note québécoise. Une note déjà importée n&apos;est pas reçue deux fois.
          </p>
          <div>
            <Button type="button" onClick={handleEpicImport} disabled={sending || epicSandbox.patients === 0}>
              {sending ? "Importation et extraction en cours..." : "Importer les notes"}
            </Button>
          </div>
        </Card>
      ) : (
        <Card className="gap-4 p-6">
          <form onSubmit={handleSubmit} className="flex flex-col items-start gap-4">
            {mode === "paste" ? (
              <TextArea
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={14}
                className="w-full"
                aria-label="Notes à ajouter"
                placeholder="Collez la note signée ici, ou toutes les notes d'un quart de travail..."
              />
            ) : (
              <div className="flex flex-col gap-[0.35rem]">
                <span id="notes-file-label" className="text-sm text-muted-foreground">
                  Fichier texte (.txt ou .md, 2 Mo maximum)
                </span>
                {/* The native picker's button reads in the browser's language ("Choose file"),
                  whatever the page's: it stays hidden, and this button opens it. */}
                <input
                  ref={fileInput}
                  id="notes-file"
                  type="file"
                  accept=".txt,.md,text/plain,text/markdown"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  className="hidden"
                  aria-labelledby="notes-file-label"
                />
                <div className="flex flex-wrap items-center gap-3">
                  <Button type="button" variant="secondary" onClick={() => fileInput.current?.click()}>
                    Parcourir...
                  </Button>
                  <span className="text-sm text-muted-foreground">{file ? file.name : "Aucun fichier choisi"}</span>
                </div>
              </div>
            )}

            <div className="flex w-full max-w-sm flex-col gap-[0.35rem]">
              <label htmlFor="batch-label" className="text-sm text-muted-foreground">
                Lot (facultatif)
              </label>
              <TextField
                id="batch-label"
                value={batchLabel}
                onChange={(e) => setBatchLabel(e.target.value)}
                maxLength={64}
                placeholder="ex. Urgence nuit du 30 sept."
              />
              <span className="text-xs text-muted-foreground">Regroupe ces rencontres dans la boîte de réception.</span>
            </div>

            <Button type="submit" disabled={sending || !ready}>
              {sending ? "Réception et extraction en cours..." : "Ajouter à la boîte de réception"}
            </Button>
          </form>
        </Card>
      )}

      {error && (
        <Banner tone="error" className="mt-4">
          {error}
        </Banner>
      )}
    </section>
  );
}
