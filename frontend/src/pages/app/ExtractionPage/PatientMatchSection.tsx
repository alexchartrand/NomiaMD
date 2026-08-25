import { Banner, Button, Select } from "../../../components";
import type { Patient, PatientSuggestionExtracted } from "../../../api";
import { CreatePatientForm } from "./CreatePatientForm";
import type { useCreatePatientForm } from "./useCreatePatientForm";

interface PatientMatchSectionProps {
  matchedId: number | null;
  matchedPatientName: string | null | undefined;
  extracted: PatientSuggestionExtracted | null;
  roster: Patient[];
  rosterError: string | null;
  selectedRosterId: number | "";
  onSelectRoster: (id: number | "") => void;
  onStartCreatePatient: () => void;
  createPatientForm: ReturnType<typeof useCreatePatientForm>;
}

export function PatientMatchSection({
  matchedId,
  matchedPatientName,
  extracted,
  roster,
  rosterError,
  selectedRosterId,
  onSelectRoster,
  onStartCreatePatient,
  createPatientForm,
}: PatientMatchSectionProps) {
  return (
    <div className="patient-match">
      {matchedId != null ? (
        <Banner tone="success">
          Patient identifié par son NAM : {matchedPatientName ?? extracted?.suggested_full_name}
        </Banner>
      ) : extracted?.suggested_ramq_number ? (
        <Banner tone="warning">
          Aucun patient de votre liste ne correspond au NAM &laquo; {extracted.suggested_ramq_number} &raquo;
          {extracted.suggested_full_name ? ` (${extracted.suggested_full_name})` : ""}
        </Banner>
      ) : (
        <Banner tone="warning">Aucun NAM n&rsquo;a été trouvé dans la note — sélectionnez le patient</Banner>
      )}

      <label htmlFor="roster-select">Patient</label>
      <Select
        id="roster-select"
        value={selectedRosterId}
        onChange={(e) => onSelectRoster(e.target.value ? Number(e.target.value) : "")}
      >
        <option value="">Sélectionnez un patient...</option>
        {roster.map((p) => (
          <option key={p.id} value={p.id}>
            {p.full_name}
          </option>
        ))}
      </Select>
      {rosterError && <Banner tone="error">{rosterError}</Banner>}

      {matchedId == null && (
        <Button type="button" variant="secondary" onClick={onStartCreatePatient}>
          Créer ce patient
        </Button>
      )}

      {createPatientForm.visible && (
        <CreatePatientForm form={createPatientForm} dateOfBirthIsEstimated={extracted?.date_of_birth_is_estimated ?? false} />
      )}
    </div>
  );
}
