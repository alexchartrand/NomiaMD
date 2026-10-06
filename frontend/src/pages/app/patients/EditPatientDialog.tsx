import { useState, type FormEvent } from "react";
import { GENDERS, describeError, updatePatient, type Gender, type PatientInput, type RosterEntry } from "../../../api";
import { Banner, Button, Checkbox, FormField, Modal, Select, TextField } from "../../../components";

interface EditPatientDialogProps {
  entry: RosterEntry;
  onClose: () => void;
  onSaved: () => void;
}

function formOf(entry: RosterEntry): PatientInput {
  return {
    full_name: entry.full_name,
    ramq_number: entry.ramq_number,
    date_of_birth: entry.date_of_birth,
    gender: entry.gender,
    is_vulnerable: entry.is_vulnerable,
    family_doctor_name: entry.family_doctor_name,
    family_doctor_practice_number: entry.family_doctor_practice_number,
  };
}

// The shared patient record (admins only): what every physician's billing context reads.
export function EditPatientDialog({ entry, onClose, onSaved }: EditPatientDialogProps) {
  const [form, setForm] = useState<PatientInput>(() => formOf(entry));
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const update = (changes: Partial<PatientInput>) => setForm((current) => ({ ...current, ...changes }));

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!form.full_name.trim() || !form.date_of_birth) {
      setError("Le nom et la date de naissance sont obligatoires.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await updatePatient(entry.id, {
        ...form,
        full_name: form.full_name.trim(),
        ramq_number: form.ramq_number?.trim() || null,
        family_doctor_name: form.family_doctor_name?.trim() || null,
        family_doctor_practice_number: form.family_doctor_practice_number?.trim() || null,
      });
      onSaved();
    } catch (err) {
      setError(describeError(err));
      setSubmitting(false);
    }
  }

  return (
    <Modal title={`Modifier le patient — ${entry.full_name}`} onClose={onClose}>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4 pb-1">
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField id="edit-full-name" label="Nom complet">
            <TextField id="edit-full-name" value={form.full_name} onChange={(e) => update({ full_name: e.target.value })} />
          </FormField>
          <FormField id="edit-ramq-number" label="Numéro RAMQ (NAM)">
            <TextField
              id="edit-ramq-number"
              className="font-mono"
              value={form.ramq_number ?? ""}
              onChange={(e) => update({ ramq_number: e.target.value })}
            />
          </FormField>
          <FormField id="edit-dob" label="Date de naissance">
            <TextField
              id="edit-dob"
              type="date"
              value={form.date_of_birth}
              onChange={(e) => update({ date_of_birth: e.target.value })}
            />
          </FormField>
          <FormField id="edit-gender" label="Genre">
            <Select
              id="edit-gender"
              containerClassName="max-w-none"
              value={form.gender ?? ""}
              onChange={(e) => update({ gender: (e.target.value || null) as Gender | null })}
            >
              <option value="">—</option>
              {GENDERS.map((g) => (
                <option key={g} value={g}>
                  {g}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="edit-family-doctor-name" label="Médecin de famille">
            <TextField
              id="edit-family-doctor-name"
              value={form.family_doctor_name ?? ""}
              onChange={(e) => update({ family_doctor_name: e.target.value })}
            />
          </FormField>
          <FormField id="edit-family-doctor-practice-number" label="Numéro de pratique du médecin de famille">
            <TextField
              id="edit-family-doctor-practice-number"
              value={form.family_doctor_practice_number ?? ""}
              onChange={(e) => update({ family_doctor_practice_number: e.target.value })}
              placeholder="12345"
            />
          </FormField>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <Checkbox
            checked={form.is_vulnerable}
            onCheckedChange={(checked) => update({ is_vulnerable: checked === true })}
          />
          Clientèle vulnérable
        </label>
        {error && <Banner tone="error">{error}</Banner>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose} disabled={submitting}>
            Annuler
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? "Enregistrement..." : "Enregistrer"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
