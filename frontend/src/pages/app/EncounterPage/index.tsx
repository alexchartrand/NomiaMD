import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { ChevronLeft, ChevronRight, FileClock, Info, RotateCw, Trash2 } from "lucide-react";
import { toast } from "sonner";
import {
  deleteEncounter,
  describeError,
  extractEncounter,
  getEncounter,
  type EncounterDetail,
} from "../../../api";
import {
  AppPage,
  AppPageHeader,
  Badge,
  Banner,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  RowActions,
  Skeleton,
  Spinner,
  useConfirm,
} from "../../../components";
import { AssociatePatient } from "../InboxPage/AssociatePatient";
import { StatusChip } from "../InboxPage/StatusChip";
import { NotePanel } from "../review/NotePanel";
import { ReviewStep } from "../review/ReviewStep";
import { useCodeReview } from "../review/useCodeReview";
import { useSaveShortcut } from "../review/useSaveShortcut";
import { EncounterFacts } from "./EncounterFacts";
import { useEncounterNeighbours } from "./useEncounterNeighbours";

// A step to a neighbouring encounter, carrying the inbox's period and filters along; inert
// at either end of the list. Replaces the history entry so "back" isn't a walk through them.
function StepButton({
  id,
  inboxSearch,
  direction,
}: {
  id: number | null;
  inboxSearch: string;
  direction: "previous" | "next";
}) {
  const label = direction === "previous" ? "Précédente" : "Suivante";
  const content =
    direction === "previous" ? (
      <>
        <ChevronLeft aria-hidden />
        {label}
      </>
    ) : (
      <>
        {label}
        <ChevronRight aria-hidden />
      </>
    );
  if (id === null) {
    return (
      <Button type="button" variant="ghost" disabled>
        {content}
      </Button>
    );
  }
  return (
    <Button asChild variant="ghost">
      <Link to={`/app/inbox/${id}`} replace state={{ inboxSearch }}>
        {content}
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
    return "Cette rencontre fait partie d'une facture : supprimez d'abord la facture pour la modifier.";
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
    void load();
  }, [encounterId, load]);

  // Saved, with a way to the claims. One id per encounter, so a re-render never stacks two.
  const announceSaved = useCallback(
    (message: string) =>
      toast.success(message, {
        id: `saved-${encounterId}`,
        action: { label: "Voir la facturation", onClick: () => navigate("/app/facturation") },
      }),
    [encounterId, navigate],
  );

  // Arrived from "Enregistrer et suivante": the previous encounter's save is announced here.
  useEffect(() => {
    if (opened?.savedFor) announceSaved(`Facturation de ${opened.savedFor} enregistrée.`);
  }, [opened?.savedFor, announceSaved]);

  const { confirm, dialog } = useConfirm();
  const readOnly = encounter ? readOnlyReason(encounter) : null;
  const review = useCodeReview(encounter?.extraction ?? null, {
    readOnly: readOnly !== null,
    claim: encounter?.claim ?? null,
    // A saved claim (first save or a draft's changes) changes the status and the claim the
    // review starts from, so reload rather than keep the stale encounter.
    onSaved: () => {
      announceSaved("Facturation enregistrée.");
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
      toast.success("Rencontre supprimée.");
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
  const savable = review.canSave && !review.state.saved && !review.state.saving;
  useSaveShortcut(savable ? (nextId !== null ? handleSaveAndNext : review.save) : null);


  if (!encounter) {
    return (
      <AppPage width="narrow">
        {error ? (
          <>
            <AppPageHeader back={{ to: backTo, label: "Rencontres" }} title="Rencontre" className="mb-4" />
            <Banner tone="error">{error}</Banner>
          </>
        ) : (
          // No heading until the encounter is here: the page's h1 is the patient's name.
          <div aria-busy="true" aria-label="Chargement de la rencontre" className="flex flex-col gap-4">
            <Skeleton className="h-5 w-28" />
            <Skeleton className="h-9 w-72" />
            <Skeleton className="h-[60vh] rounded-xl" />
          </div>
        )}
      </AppPage>
    );
  }

  return (
    <AppPage width={reviewing ? "wide" : "narrow"}>
      {dialog}
      <AppPageHeader
        back={{ to: backTo, label: "Rencontres" }}
        title={encounter.patient?.full_name ?? "Patient à associer"}
        documentTitle={encounter.patient?.full_name ?? "Rencontre"}
        className="mb-4"
        aside={
          <>
            {encounter.patient?.nam && (
              <span className="font-mono text-sm text-muted-foreground">{encounter.patient.nam}</span>
            )}
            <StatusChip status={encounter.status} />
            {!readOnly && encounter.claim && (
              <Badge tone="primary" icon={FileClock}>
                Brouillon enregistré
              </Badge>
            )}
          </>
        }
        actions={
          <>
            {neighbours && (
              <nav
                aria-label="Navigation entre les rencontres"
                className="mr-2 flex items-center gap-1 text-sm text-muted-foreground"
              >
                <StepButton id={neighbours.previousId} inboxSearch={inboxSearch} direction="previous" />
                <span className="tabular-nums">
                  {neighbours.position} / {neighbours.total}
                </span>
                <StepButton id={neighbours.nextId} inboxSearch={inboxSearch} direction="next" />
              </nav>
            )}
            {canRerun && (
              <Button type="button" variant="secondary" onClick={handleRerun} disabled={extracting}>
                {extracting ? (
                  <Spinner label="Extraction en cours…" />
                ) : (
                  <>
                    <RotateCw aria-hidden />
                    Relancer l&apos;extraction
                  </>
                )}
              </Button>
            )}
            <RowActions
              label="Plus d'actions sur la rencontre"
              actions={[
                {
                  label: "Supprimer la rencontre",
                  icon: Trash2,
                  danger: true,
                  onSelect: handleDelete,
                  disabled: encounter.claim !== null || deleting,
                },
              ]}
            />
          </>
        }
      />

      {error && <Banner tone="error">{error}</Banner>}

      <div className="flex flex-col gap-4">
        <EncounterFacts encounter={encounter} />

        {encounter.status === "à associer" && (
          <Card>
            <CardHeader>
              <CardTitle>Associer un patient</CardTitle>
            </CardHeader>
            <CardContent>
              <AssociatePatient encounterId={encounter.id} onAssigned={load} />
            </CardContent>
          </Card>
        )}

        {encounter.status === "échec" && encounter.extraction_error && (
          <Banner tone="error">L&rsquo;extraction a échoué : {encounter.extraction_error}</Banner>
        )}
        {canExtract && (
          <Button type="button" className="self-start" onClick={handleExtract} disabled={extracting}>
            {extracting ? (
              <Spinner label="Extraction en cours…" />
            ) : encounter.status === "échec" ? (
              "Réessayer"
            ) : (
              "Extraire les codes"
            )}
          </Button>
        )}

        {readOnly && <Banner tone="warning">{readOnly}</Banner>}
        {!readOnly && encounter.claim && (
          <p className="m-0 flex items-center gap-2 text-sm text-muted-foreground">
            <Info aria-hidden className="size-4 shrink-0" />
            Facturation enregistrée (brouillon). Vos modifications remplaceront la facturation existante.
          </p>
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
          <NotePanel text={encounter.note_text} defaultOpen={!encounter.extraction} />
        )}
      </div>
    </AppPage>
  );
}
