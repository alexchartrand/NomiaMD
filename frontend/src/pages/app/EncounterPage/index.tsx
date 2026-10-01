import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { describeError, extractEncounter, getEncounter, type EncounterDetail } from "../../../api";
import { Banner, Button, Card, CardContent, CardHeader, CardTitle, Spinner } from "../../../components";
import { formatClinicTime, formatDate } from "../../../utils/date";
import { AssociatePatient } from "../InboxPage/AssociatePatient";
import { StatusChip } from "../InboxPage/StatusChip";
import { ReviewStep } from "../review/ReviewStep";
import { useCodeReview } from "../review/useCodeReview";

// Why a review can be read but not saved, if it can't.
function readOnlyReason(encounter: EncounterDetail): string | null {
  if (encounter.duplicate_of_id !== null) {
    return "Cette rencontre a été marquée comme doublon d'une autre visite : elle n'est pas facturée.";
  }
  if (encounter.status === "revu") return "Cette rencontre a déjà été facturée.";
  if (encounter.status === "modifié") return "Une version plus récente de cette note a été reçue.";
  return null;
}

// One encounter: its note, and the review of its latest extraction — or whatever it still
// needs first (a patient, an extraction).
export default function EncounterPage() {
  const encounterId = Number(useParams().encounterId);
  // The inbox's period and filters, when we came from it; its default period otherwise.
  const inboxSearch = (useLocation().state as { inboxSearch?: string } | null)?.inboxSearch ?? "";
  const [encounter, setEncounter] = useState<EncounterDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [extracting, setExtracting] = useState(false);

  const load = useCallback(async () => {
    try {
      setEncounter(await getEncounter(encounterId));
      setError(null);
    } catch (err) {
      setError(describeError(err));
    }
  }, [encounterId]);

  useEffect(() => {
    void load();
  }, [load]);

  const readOnly = encounter ? readOnlyReason(encounter) : null;
  const review = useCodeReview(encounter?.extraction ?? null, readOnly !== null);

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

  const backTo = `/app/inbox${inboxSearch}`;
  const canExtract =
    encounter !== null && encounter.patient !== null && (encounter.status === "reçu" || encounter.status === "échec");

  return (
    <section className="max-w-[860px]">
      <p className="mb-2">
        <Button asChild variant="link">
          <Link to={backTo}>← Rencontres</Link>
        </Button>
      </p>

      {error && <Banner tone="error">{error}</Banner>}
      {!encounter && !error && <Spinner label="Chargement..." />}

      {encounter && (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="m-0 font-heading text-2xl font-semibold">
              {encounter.patient?.full_name ?? "Patient à associer"}
            </h1>
            <StatusChip status={encounter.status} />
          </div>
          <p className="m-0 text-sm text-muted-foreground">
            {[
              encounter.source_system,
              encounter.service_date ? formatDate(encounter.service_date) : null,
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
                <AssociatePatient encounterId={encounter.id} onAssigned={load} />
              </CardContent>
            </Card>
          )}

          {encounter.status === "échec" && encounter.extraction_error && (
            <Banner tone="error">L&rsquo;extraction a échoué : {encounter.extraction_error}</Banner>
          )}
          {canExtract && (
            <Button type="button" className="self-start" onClick={handleExtract} disabled={extracting}>
              {extracting ? "Extraction en cours..." : encounter.status === "échec" ? "Réessayer" : "Extraire les codes"}
            </Button>
          )}

          {readOnly && <Banner tone="warning">{readOnly}</Banner>}
          {encounter.extraction && encounter.patient && (
            <ReviewStep result={encounter.extraction} patient={encounter.patient} review={review} />
          )}

          <details open={!encounter.extraction} className="rounded-xl border border-border bg-card px-4 py-3">
            <summary className="cursor-pointer font-heading font-semibold">Note reçue</summary>
            <pre className="mt-3 mb-0 font-mono text-sm whitespace-pre-wrap">{encounter.note_text}</pre>
          </details>
        </div>
      )}
    </section>
  );
}
