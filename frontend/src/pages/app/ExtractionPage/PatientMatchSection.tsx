import { Banner } from "../../../components";
import type { Patient, PatientVerification } from "../../../api";

interface PatientMatchSectionProps {
  patient: Patient;
  verification: PatientVerification | null;
}

// The patient was fixed before extraction ran (SourceStep.tsx) — this just shows who was
// chosen and, if the transcript itself describes a different identity, a mismatch
// warning. Never a picker any more: to change the patient, the physician goes back to the
// source step.
export function PatientMatchSection({ patient, verification }: PatientMatchSectionProps) {
  const warnings: string[] = [];
  if (verification?.nam_mismatch) {
    warnings.push(
      `Le NAM mentionné dans la transcription (${verification.extracted.ramq_number_as_stated ?? "inconnu"}) ne correspond pas au patient sélectionné.`,
    );
  }
  if (verification?.name_mismatch) {
    warnings.push(
      `Le nom mentionné dans la transcription (${verification.extracted.name_as_stated ?? "inconnu"}) ne correspond pas au patient sélectionné.`,
    );
  }
  if (verification?.age_mismatch) {
    warnings.push("L'âge mentionné dans la transcription ne correspond pas au patient sélectionné.");
  }

  return (
    <div className="my-4 flex flex-col items-stretch gap-2">
      <Banner tone={warnings.length > 0 ? "warning" : "success"}>
        Patient : {patient.full_name}
        {patient.ramq_number ? ` (${patient.ramq_number})` : ""}
      </Banner>
      {warnings.map((warning) => (
        <Banner key={warning} tone="warning">
          ⚠ {warning}
        </Banner>
      ))}
    </div>
  );
}
