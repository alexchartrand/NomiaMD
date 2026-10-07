import { useState, type FormEvent } from "react";
import { addToRoster, describeError, type Patient } from "../../../api";
import { Banner, Button, FormField, Modal, PatientSearchSelect, TextArea } from "../../../components";

interface AddExistingDialogProps {
  onClose: () => void;
  onAdded: () => void;
}

// A patient the clinic already knows (patients are shared, unique by NAM), added to this
// physician's own list.
export function AddExistingDialog({ onClose, onAdded }: AddExistingDialogProps) {
  const [patient, setPatient] = useState<Patient | null>(null);
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!patient) {
      setError("Sélectionnez un patient.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await addToRoster({ patient_id: patient.id, notes: notes.trim() || null });
      onAdded();
    } catch (err) {
      setError(describeError(err));
      setSubmitting(false);
    }
  }

  return (
    <Modal title="Ajouter un patient existant" onClose={onClose}>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4 pb-1">
        <FormField id="roster-patient-search" label="Patient">
          <PatientSearchSelect id="roster-patient-search" selected={patient} onSelect={setPatient} className="max-w-none" />
        </FormField>
        <FormField id="roster-notes" label="Notes personnelles">
          <TextArea id="roster-notes" className="font-sans" value={notes} onChange={(e) => setNotes(e.target.value)} />
        </FormField>
        {error && <Banner tone="error">{error}</Banner>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose} disabled={submitting}>
            Annuler
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? "Ajout..." : "Ajouter"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
