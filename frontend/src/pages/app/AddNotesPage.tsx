import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  describeError,
  getEpicSandboxStatus,
  importEpicSandboxNotes,
  pushNotes,
  uploadNotes,
  type EpicSandboxStatus,
  type ReceiveOutcome,
} from "../../api";
import { CloudDownload, FileUp } from "lucide-react";
import { AppPage, AppPageHeader, Banner, Button, Card, FormField, Spinner, Tabs, TextArea, TextField } from "../../components";

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

  const tabs = [
    { id: "paste" as const, label: "Coller" },
    { id: "upload" as const, label: "Téléverser un fichier" },
    ...(epicSandbox ? [{ id: "epic" as const, label: "Epic — démo (sandbox)" }] : []),
  ];

  return (
    <AppPage width="narrow">
      <AppPageHeader
        back={{ to: "/app/inbox", label: "Rencontres" }}
        title="Ajouter des notes"
        description={
          <>
            Collez une ou plusieurs notes signées, ou téléversez un fichier. Chaque note commence par la ligne du NAM du
            patient (&laquo;&nbsp;**NAM :**&nbsp;&raquo;) : un quart de travail collé d&apos;un coup devient autant de
            rencontres, et leurs codes sont extraits aussitôt.
          </>
        }
      />

      <Tabs<Mode> ariaLabel="Source des notes" className="mb-5" items={tabs} value={mode} onChange={setMode} />

      {mode === "epic" && epicSandbox ? (
        <Card className="gap-4 p-6">
          <p className="text-sm text-muted-foreground">
            Importe une sélection de notes signées des {epicSandbox.patients} patients fictifs du bac à sable
            d&apos;Epic (fhir.epic.com). Ces notes sont en anglais, de style américain et datées de 2006 à 2023 :
            elles montrent le parcours complet Epic → rencontres → codes, pas la qualité des codes sur une
            vraie note québécoise. Une note déjà importée n&apos;est pas reçue deux fois.
          </p>
          <div>
            <Button type="button" onClick={handleEpicImport} disabled={sending || epicSandbox.patients === 0}>
              {sending ? <Spinner label="Importation et extraction en cours…" /> : (
                <>
                  <CloudDownload aria-hidden />
                  Importer les notes
                </>
              )}
            </Button>
          </div>
        </Card>
      ) : (
        <Card className="gap-4 p-6">
          <form onSubmit={handleSubmit} className="flex flex-col gap-5">
            {mode === "paste" ? (
              <TextArea
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={14}
                className="w-full text-[0.85rem]"
                aria-label="Notes à ajouter"
                placeholder="Collez la note signée ici, ou toutes les notes d'un quart de travail..."
              />
            ) : (
              <div className="flex flex-col gap-2">
                <span id="notes-file-label" className="text-sm font-medium">
                  Fichier texte (.txt ou .md, 2 Mo maximum)
                </span>
                {/* The native picker's button reads in the browser's language ("Choose file"),
                  whatever the page's: it stays hidden, and this drop zone opens it. */}
                <input
                  ref={fileInput}
                  id="notes-file"
                  type="file"
                  accept=".txt,.md,text/plain,text/markdown"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  className="hidden"
                  aria-labelledby="notes-file-label"
                />
                <button
                  type="button"
                  onClick={() => fileInput.current?.click()}
                  className="flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed border-border bg-muted/30 px-6 py-10 text-center transition-colors hover:border-primary hover:bg-[color:var(--color-primary-tint)]"
                >
                  <FileUp aria-hidden className="size-6 text-primary" />
                  <span className="text-sm font-semibold">{file ? file.name : "Parcourir..."}</span>
                  <span className="text-xs text-muted-foreground">{file ? "Cliquez pour en choisir un autre" : "Aucun fichier choisi"}</span>
                </button>
              </div>
            )}

            <FormField
              id="batch-label"
              label="Lot (facultatif)"
              hint="Regroupe ces rencontres sous un même titre dans la liste."
              className="max-w-sm"
            >
              <TextField
                id="batch-label"
                value={batchLabel}
                onChange={(e) => setBatchLabel(e.target.value)}
                maxLength={64}
                placeholder="ex. Urgence nuit du 30 sept."
              />
            </FormField>

            <div className="flex justify-end">
              <Button type="submit" disabled={sending || !ready}>
                {sending ? <Spinner label="Réception et extraction en cours…" /> : "Ajouter aux rencontres"}
              </Button>
            </div>
          </form>
        </Card>
      )}

      {error && (
        <Banner tone="error" className="mt-4">
          {error}
        </Banner>
      )}
    </AppPage>
  );
}
