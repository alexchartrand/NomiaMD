import { searchPatients, type Patient } from "../api";
import { SearchCombobox } from "./SearchCombobox";

interface PatientSearchSelectProps {
  id?: string;
  selected: Patient | null;
  onSelect: (patient: Patient | null) => void;
  placeholder?: string;
  className?: string;
}

// A physician's roster no longer bounds "which patients exist" (Patient is global now), so
// picking one needs a live search rather than a native <select> over a loaded list.
export function PatientSearchSelect({ id, selected, onSelect, placeholder, className }: PatientSearchSelectProps) {
  return (
    <SearchCombobox<Patient>
      id={id}
      search={searchPatients}
      itemKey={(patient) => patient.id}
      renderItem={(patient) => (
        <>
          {patient.full_name}
          {patient.ramq_number && <span className="text-muted-foreground"> — {patient.ramq_number}</span>}
        </>
      )}
      onPick={onSelect}
      selectedLabel={selected?.full_name ?? null}
      onEdit={() => onSelect(null)}
      emptyText="Aucun patient trouvé"
      placeholder={placeholder ?? "Nom ou NAM du patient..."}
      ariaLabel="Patient"
      className={className}
    />
  );
}
