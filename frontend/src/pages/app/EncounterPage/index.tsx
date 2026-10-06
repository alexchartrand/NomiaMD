import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  deleteEncounter,
  describeError,
  extractEncounter,
  getEncounter,
  type EncounterDetail,
} from "../../../api";
import {
  Banner,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Spinner,
  useConfirm,
} from "../../../components";
import { formatClinicTime, formatDate } from "../../../utils/date";
import { AssociatePatient } from "../InboxPage/AssociatePatient";
import { StatusChip } from "../InboxPage/StatusChip";
import { NotePanel } from "../review/NotePanel";
import { ReviewStep } from "../review/ReviewStep";
import { useCodeReview } from "../review/useCodeReview";
import { useEncounterNeighbours } from "./useEncounterNeighbours";

// A step to a neighbouring encounter, carrying the inbox's period and filters along; inert
// at either end of the list. Replaces the history entry so "back" isn't a walk through them.
function StepButton({
  id,
  inboxSearch,
  children,
}: {
  id: number | null;
  inboxSearch: string;
  children: ReactNode;
}) {
  if (id === null) {
    return (
      <Button type="button" variant="secondary" disabled>
        {children}
      </Button>
    );
  }
  return (
    <Button asChild variant="secondary">
      <Link to={`/app/inbox/${id}`} replace state={{ inboxSearch }}>
        {children}
      </Link>
    </Button>
  );
}

// Why a review can be read but not saved, if it can't.
function readOnlyReason(encounter: EncounterDetail): string | null {
  if (encounter.duplicate_of_id !== null) {
    return "Cette rencontre a été marquée comme doublon d'une autre visite : elle n'est pas facturée.";
  }
  if (encounter.claim?.status === "soumis") {
    return "Cette facturation fait partie d'une facture générée : supprimez d'abord la facture pour la modifier.";
  }
  if (encounter.status === "modifié")
    return "Une version plus récente de cette note a été reçue.";
  return null;
}

// What the page is opened with: the inbox's period and filters, when it came from it, and
// whose claim was just saved, when it came from "Enregistrer et suivante".
interface EncounterPageState {
  inboxSearch?: string;
  savedFor?: string;
}

// One encounter: its note, and the review of its latest extraction — or whatever it still
// needs first (a patient, an extraction).
export default function EncounterPage() {
  const encounterId = Number(useParams().encounterId);
  const opened = useLocation().state as EncounterPageState | null;
  // The inbox's default period when it wasn't opened from the inbox.
  const inboxSearch = opened?.inboxSearch ?? "";
  const [encounter, setEncounter] = useState<EncounterDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const [deleting, setDeleting] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [savedNotice, setSavedNotice] = useState(false);
  const neighbours = useEncounterNeighbours(encounterId, inboxSearch);
  // The encounter on screen, so a load still in flight for the previous one is dropped.
  const shownId = useRef(encounterId);

  const load = useCallback(async () => {
    try {
      const detail = await getEncounter(encounterId);
      if (shownId.current !== encounterId) return;
      setEncounter(detail);
      setError(null);
    } catch (err) {
      if (shownId.current === encounterId) setError(describeError(err));
    }
  }, [encounterId]);

  // Stepping to another encounter keeps this page mounted: start it from scratch.
  useEffect(() => {
    shownId.current = encounterId;
    setEncounter(null);
    setError(null);
    setSavedNotice(false);
    void load();
  }, [encounterId, load]);

  const { confirm, dialog } = useConfirm();
  const readOnly = encounter ? readOnlyReason(encounter) : null;
  const review = useCodeReview(encounter?.extraction ?? null, {
    readOnly: readOnly !== null,
    claim: encounter?.claim ?? null,
    // A saved claim (first save or a draft's changes) changes the status and the claim the
    // review starts from, so reload rather than keep the stale encounter.
    onSaved: () => {
      setSavedNotice(true);
      void load();
    },
    confirmDuplicate: (message) =>
      confirm({
        title: "Facturation déjà enregistrée",
        message,
        confirmLabel: "Enregistrer quand même",
      }),
  });

  async function handleRerun() {
    const confirmed = await confirm({
      title: "Relancer l'extraction ?",
      message: encounter?.claim
        ? "Les codes proposés seront remplacés par une nouvelle lecture de la note. La facturation enregistrée reste en place jusqu'à ce que vous enregistriez de nouveau."
        : "Les codes proposés seront remplacés par une nouvelle lecture de la note, et les cases cochées seront perdues.",
      confirmLabel: "Relancer",
    });
    if (confirmed) await handleExtract();
  }

  async function handleExtract() {
    setExtracting(true);
    setError(null);
    try {
      await extractEncounter(encounterId);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setExtracting(false);
      // Either way the encounter changed: a new run, or the failure recorded on it.
      await load();
    }
  }

  async function handleDelete() {
    const confirmed = await confirm({
      title: "Supprimer la rencontre ?",
      message: "La rencontre et ses extractions seront supprimées. Cette action est irréversible.",
      confirmLabel: "Supprimer",
      tone: "danger",
    });
    if (!confirmed) return;
    setDeleting(true);
    setError(null);
    try {
      await deleteEncounter(encounterId);
      navigate(backTo);
    } catch (err) {
      setError(describeError(err));
      setDeleting(false);
    }
  }

  const nextId = neighbours?.nextId ?? null;
  const goToNext = (savedFor?: string) =>
    nextId !== null &&
    navigate(`/app/inbox/${nextId}`, { replace: true, state: { inboxSearch, savedFor } });

  async function handleSaveAndNext() {
    const patientName = encounter?.patient?.full_name;
    if (await review.save()) goToNext(patientName);
  }

  const backTo = `/app/inbox${inboxSearch}`;
  const reviewing = encounter?.extraction != null && encounter.patient != null;
  const canExtract =
    encounter !== null &&
    encounter.patient !== null &&
    (encounter.status === "reçu" || encounter.status === "échec");
  // A new reading of a note whose codes can still change.
  const canRerun = reviewing && readOnly === null;

  return (
    <section className={reviewing ? "max-w-[1500px]" : "max-w-[860px]"}>
      {dialog}
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <Button asChild variant="link">
          <Link to={backTo}>← Rencontres</Link>
        </Button>
        {neighbours && (
          <nav
            aria-label="Navigation entre les rencontres"
            className="flex items-center gap-2 text-sm text-muted-foreground"
          >
            <StepButton id={neighbours.previousId} inboxSearch={inboxSearch}>
              ← Précédente
            </StepButton>
            <span>
              {neighbours.position} / {neighbours.total}
            </span>
            <StepButton id={neighbours.nextId} inboxSearch={inboxSearch}>
              Suivante →
            </StepButton>
          </nav>
        )}
      </div>

      {error && <Banner tone="error">{error}</Banner>}
      {!encounter && !error && <Spinner label="Chargement..." />}

      {encounter && (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="m-0 font-heading text-2xl font-semibold">
              {encounter.patient?.full_name ?? "Patient à associer"}
            </h1>
            {encounter.patient?.nam && (
              <span className="font-mono text-sm text-muted-foreground">
                {encounter.patient.nam}
              </span>
            )}
            <StatusChip status={encounter.status} />
            {canRerun && (
              <Button
                type="button"
                variant="ghost"
                className="ml-auto"
                onClick={handleRerun}
                disabled={extracting}
              >
                {extracting ? "Extraction en cours..." : "Relancer l'extraction"}
              </Button>
            )}
          </div>
          <p className="m-0 text-sm text-muted-foreground">
            {[
              encounter.source_system,
              encounter.service_date
                ? formatDate(encounter.service_date)
                : null,
              `reçue à ${formatClinicTime(encounter.received_at)}`,
              encounter.batch_label,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>

          {encounter.status === "à associer" && (
            <Card>
              <CardHeader>
                <CardTitle>Associer un patient</CardTitle>
              </CardHeader>
              <CardContent>
                <AssociatePatient
                  encounterId={encounter.id}
                  onAssigned={load}
                />
              </CardContent>
            </Card>
          )}

          {encounter.status === "échec" && encounter.extraction_error && (
            <Banner tone="error">
              L&rsquo;extraction a échoué : {encounter.extraction_error}
            </Banner>
          )}
          {canExtract && (
            <Button
              type="button"
              className="self-start"
              onClick={handleExtract}
              disabled={extracting}
            >
              {extracting
                ? "Extraction en cours..."
                : encounter.status === "échec"
                  ? "Réessayer"
                  : "Extraire les codes"}
            </Button>
          )}

          {readOnly && <Banner tone="warning">{readOnly}</Banner>}
          {!readOnly && encounter.claim && !savedNotice && (
            <p className="m-0 text-sm text-muted-foreground">
              Facturation enregistrée (brouillon). Vos modifications
              remplaceront la facturation existante.
            </p>
          )}
          {savedNotice && (
            <Banner tone="success">
              Facturation enregistrée.{" "}
              <Link to="/app/facturation">Voir la facturation</Link>
            </Banner>
          )}
          {!savedNotice && opened?.savedFor && (
            <Banner tone="success">
              Facturation de {opened.savedFor} enregistrée.{" "}
              <Link to="/app/facturation">Voir la facturation</Link>
            </Banner>
          )}
          {reviewing ? (
            <ReviewStep
              result={encounter.extraction!}
              noteText={encounter.note_text}
              patientId={encounter.patient!.id}
              review={review}
              onSaveAndNext={nextId !== null ? handleSaveAndNext : undefined}
              onNext={nextId !== null ? () => goToNext() : undefined}
            />
          ) : (
            <NotePanel
              text={encounter.note_text}
              defaultOpen={!encounter.extraction}
            />
          )}

          {!encounter.claim && (
            <Button
              type="button"
              variant="danger"
              className="self-start"
              onClick={handleDelete}
              disabled={deleting}
            >
              {deleting ? "Suppression..." : "Supprimer la rencontre"}
            </Button>
          )}
        </div>
      )}
    </section>
  );
}
