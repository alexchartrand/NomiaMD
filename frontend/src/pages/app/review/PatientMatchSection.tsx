import { Banner } from "../../../components";
import type { Patient } from "../../../api";

interface PatientMatchSectionProps {
  patient: Patient;
}

// The patient was fixed before extraction ran (SourceStep.tsx) — this just shows who was
// chosen. Never a picker any more: to change the patient, the physician goes back to the
// source step.
export function PatientMatchSection({ patient }: PatientMatchSectionProps) {
  return (
    <div className="my-4 flex flex-col items-stretch gap-2">
      <Banner tone="success">
        Patient : {patient.full_name}
        {patient.ramq_number ? ` (${patient.ramq_number})` : ""}
      </Banner>
    </div>
  );
}
