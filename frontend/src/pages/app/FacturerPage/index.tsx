import { useEffect, useMemo, useReducer, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  createManualClaim,
  describeError,
  getClaim,
  getCode,
  getPatient,
  MANUAL_SOURCE_SYSTEM,
  replaceManualClaim,
  type CodeHit,
  type Patient,
} from "../../../api";
import { Banner, Card, CardContent, CardHeader, CardTitle, PatientSearchSelect, TextField } from "../../../components";
import { clinicToday } from "../../../utils/date";
import { AddedCodes } from "../review/AddedCodes";
import { feeTotals } from "../review/feeOptions";
import {
  emptyManualCodes,
  manualCodesFromClaim,
  manualCodesReducer,
  manualEntries,
  manualSelectedCodes,
} from "../review/manualCodes";
import { SaveSummary } from "../review/SaveSummary";

// Billing without an encounter: no note to read codes from, so the physician names the patient
// and the date and picks every code from the code search — only the codes that patient may be
// billed are offered, and the server checks again. With a claim id, edits that draft instead
// (saving replaces it).
export default function FacturerPage() {
  const { claimId } = useParams();
  const editingId = claimId ? Number(claimId) : null;
  const navigate = useNavigate();

  const [patient, setPatient] = useState<Patient | null>(null);
  const [serviceDate, setServiceDate] = useState(clinicToday());
  const [manual, dispatch] = useReducer(manualCodesReducer, emptyManualCodes);
  const [loading, setLoading] = useState(editingId !== null);
  const [loadError, setLoadError] = useState<string | null>(null);
  // Codes of the draft the current codes table no longer has: they'd be dropped on save.
  const [retired, setRetired] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (editingId === null) return;
    let current = true;
    (async () => {
      try {
        const claim = await getClaim(editingId);
        if (claim.source_system !== MANUAL_SOURCE_SYSTEM || claim.status !== "brouillon") {
          throw new Error("Seule une facturation sans rencontre, encore en brouillon, se modifie ici.");
        }
        const [claimPatient, outcomes] = await Promise.all([
          getPatient(claim.patient_id),
          Promise.allSettled(claim.codes.map((line) => getCode(line.code))),
        ]);
        if (!current) return;
        const hits = outcomes.flatMap((o): CodeHit[] => (o.status === "fulfilled" ? [o.value] : []));
        setPatient(claimPatient);
        setServiceDate(claim.service_date);
        dispatch({ type: "manual-codes-restored", manual: manualCodesFromClaim(hits, claim.codes) });
        setRetired(claim.codes.map((line) => line.code).filter((code) => !hits.some((h) => h.number === code)));
      } catch (err) {
        if (current) setLoadError(describeError(err));
      } finally {
        if (current) setLoading(false);
      }
    })();
    return () => {
      current = false;
    };
  }, [editingId]);

  const entries = useMemo(() => manualEntries(manual), [manual]);
  const { totalAmount, codesMissingFee } = feeTotals(entries.map((e) => e.fee));
  const canSave = patient !== null && Boolean(serviceDate) && entries.length > 0;

  async function handleSave() {
    if (!patient || !canSave) return;
    setSaving(true);
    setSaveError(null);
    const payload = { patient_id: patient.id, service_date: serviceDate, selected_codes: manualSelectedCodes(manual) };
    try {
      await (editingId !== null ? replaceManualClaim(editingId, payload) : createManualClaim(payload));
      navigate("/app/facturation");
    } catch (err) {
      setSaveError(describeError(err));
      setSaving(false);
    }
  }

  const title = editingId !== null ? "Modifier une facturation sans rencontre" : "Facturer sans rencontre";

  if (loading) return <p className="text-sm text-muted-foreground">Chargement...</p>;
  if (loadError) {
    return (
      <section className="flex max-w-[860px] flex-col gap-4">
        <h1 className="font-heading text-2xl font-semibold">{title}</h1>
        <Banner tone="error">{loadError}</Banner>
        <Link to="/app/facturation">← Retour à la facturation</Link>
      </section>
    );
  }

  return (
    <section className="flex max-w-[860px] flex-col gap-6">
      <div>
        <h1 className="font-heading text-2xl font-semibold">{title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Choisissez le patient et la date, puis ajoutez les codes à facturer. Seuls les codes admissibles pour ce
          patient sont proposés.
        </p>
      </div>

      <Card className="overflow-visible">
        <CardHeader className="flex flex-wrap items-end gap-6">
          <div className="flex min-w-[16rem] flex-1 flex-col gap-1.5">
            <label htmlFor="facturer-patient" className="text-sm font-semibold">
              Patient
            </label>
            <PatientSearchSelect id="facturer-patient" selected={patient} onSelect={setPatient} className="max-w-none" />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="facturer-date" className="text-sm font-semibold">
              Date du service
            </label>
            <TextField
              id="facturer-date"
              type="date"
              className="w-auto"
              value={serviceDate}
              onChange={(e) => setServiceDate(e.target.value)}
            />
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-[0.85rem]">
          <CardTitle className="text-[1.1rem] font-bold">Codes</CardTitle>
          {retired.length > 0 && (
            <Banner tone="warning">
              ⚠ Code(s) retiré(s) du manuel en vigueur, qui ne seront pas conservés : {retired.join(", ")}
            </Banner>
          )}
          {patient ? (
            <AddedCodes
              entries={entries}
              onAdd={(hit) => dispatch({ type: "manual-code-added", hit })}
              onRemove={(number) => dispatch({ type: "manual-code-removed", number })}
              onFeeSelected={(number, feeIndex, lieu) => dispatch({ type: "manual-fee-selected", number, feeIndex, lieu })}
              patientId={patient.id}
              serviceDate={serviceDate || null}
            />
          ) : (
            <p className="text-sm text-muted-foreground">Choisissez d&rsquo;abord le patient.</p>
          )}

          <SaveSummary
            totalAmount={totalAmount}
            codesMissingFee={codesMissingFee}
            saving={saving}
            saveError={saveError}
            saved={false}
            canSave={canSave}
            editing={editingId !== null}
            readOnly={false}
            onSave={handleSave}
          />
        </CardContent>
      </Card>
    </section>
  );
}
