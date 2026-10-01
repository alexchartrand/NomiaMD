import { useState } from "react";
import { assignEncounterPatient, describeError, type Patient } from "../../../api";
import { Banner, Button, PatientSearchSelect } from "../../../components";
import { CreatePatientForm } from "../patients/CreatePatientForm";
import { useCreatePatientForm } from "../patients/useCreatePatientForm";

interface AssociatePatientProps {
  encounterId: number;
  onAssigned: () => void;
  // Omitted where the pick isn't a collapsible inline form.
  onCancel?: () => void;
}

// An "à associer" row's inline patient pick. Picking queues the extraction, which runs in
// the request until the background worker exists — hence the wait.
export function AssociatePatient({ encounterId, onAssigned, onCancel }: AssociatePatientProps) {
  const [patient, setPatient] = useState<Patient | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const createPatientForm = useCreatePatientForm({ onCreated: setPatient });

  async function handleAssign() {
    if (!patient) return;
    setSaving(true);
    setError(null);
    try {
      await assignEncounterPatient(encounterId, patient.id);
      onAssigned();
    } catch (err) {
      setError(describeError(err));
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <PatientSearchSelect id={`associate-${encounterId}`} selected={patient} onSelect={setPatient} />
        <Button type="button" onClick={handleAssign} disabled={!patient || saving}>
          {saving ? "Association et extraction..." : "Associer"}
        </Button>
        {onCancel && (
          <Button type="button" variant="ghost" onClick={onCancel} disabled={saving}>
            Annuler
          </Button>
        )}
      </div>
      {!patient && !createPatientForm.visible && (
        <Button type="button" variant="link" className="self-start" onClick={() => createPatientForm.open()}>
          Créer un patient
        </Button>
      )}
      {createPatientForm.visible && <CreatePatientForm form={createPatientForm} />}
      {error && <Banner tone="error">{error}</Banner>}
    </div>
  );
}
