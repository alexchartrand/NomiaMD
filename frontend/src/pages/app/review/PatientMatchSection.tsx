import { Banner } from "../../../components";

// Who the codes were extracted for. Fixed before extraction ran (a NAM match at intake, or
// the physician's pick in the inbox) — never a picker here.
export interface ReviewedPatient {
  full_name: string;
  nam: string | null;
}

interface PatientMatchSectionProps {
  patient: ReviewedPatient;
}

export function PatientMatchSection({ patient }: PatientMatchSectionProps) {
  return (
    <div className="my-4 flex flex-col items-stretch gap-2">
      <Banner tone="success">
        Patient : {patient.full_name}
        {patient.nam ? ` (${patient.nam})` : ""}
      </Banner>
    </div>
  );
}
