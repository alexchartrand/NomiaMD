import type { FormEvent } from "react";
import { cn } from "@/lib/utils";
import { Banner, Button, Card, PatientSearchSelect, Select, TextArea } from "../../../components";
import type { Patient, SamplePatientSummary } from "../../../api";
import { CreatePatientForm } from "../patients/CreatePatientForm";
import type { useCreatePatientForm } from "../patients/useCreatePatientForm";

interface SourceStepProps {
  source: "simule" | null;
  onChooseSource: (source: "simule") => void;
  samplePatients: SamplePatientSummary[];
  selectedSamplePatientId: string;
  onSelectSamplePatient: (id: string) => void;
  samplePatientLoading: boolean;
  samplePatientsError: string | null;
  transcript: string;
  onTranscriptChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  loading: boolean;
  selectedPatient: Patient | null;
  onSelectPatient: (patient: Patient | null) => void;
  createPatientForm: ReturnType<typeof useCreatePatientForm>;
  onStartCreatePatient: () => void;
}

const sourceCardClasses =
  "flex min-w-[160px] cursor-pointer flex-col items-start gap-[0.4rem] rounded-[10px] border border-border bg-card px-5 py-4 text-base text-foreground hover:border-primary disabled:pointer-events-none disabled:cursor-not-allowed disabled:text-muted-foreground";

export function SourceStep({
  source,
  onChooseSource,
  samplePatients,
  selectedSamplePatientId,
  onSelectSamplePatient,
  samplePatientLoading,
  samplePatientsError,
  transcript,
  onTranscriptChange,
  onSubmit,
  loading,
  selectedPatient,
  onSelectPatient,
  createPatientForm,
  onStartCreatePatient,
}: SourceStepProps) {
  return (
    <>
      <ol className="mb-4 flex flex-wrap gap-4 p-0">
        <li>
          <button
            type="button"
            className={cn(sourceCardClasses, source === "simule" && "border-primary bg-[color:var(--color-primary-tint)]")}
            onClick={() => onChooseSource("simule")}
          >
            Patient simulé
          </button>
        </li>
        <li>
          <button type="button" className={sourceCardClasses} disabled>
            Epic
            <span className="text-[0.75rem] text-muted-foreground">Bientôt disponible</span>
          </button>
        </li>
        <li>
          <button type="button" className={sourceCardClasses} disabled>
            Telus Health
            <span className="text-[0.75rem] text-muted-foreground">Bientôt disponible</span>
          </button>
        </li>
      </ol>

      {source && (
        <Card className="gap-4 p-6">
          <div className="flex flex-col gap-[0.35rem]">
            <label htmlFor="patient-search" className="text-sm text-muted-foreground">
              Patient (obligatoire) :
            </label>
            <PatientSearchSelect id="patient-search" selected={selectedPatient} onSelect={onSelectPatient} />
            {!selectedPatient && (
              <Button type="button" variant="link" className="self-start" onClick={onStartCreatePatient}>
                Créer un nouveau patient
              </Button>
            )}
            {createPatientForm.visible && <CreatePatientForm form={createPatientForm} />}
          </div>

          <div className="flex flex-col gap-[0.35rem]">
            <label htmlFor="patient-select" className="text-sm text-muted-foreground">
              Patient simulé :
            </label>
            <Select
              id="patient-select"
              value={selectedSamplePatientId}
              onChange={(e) => onSelectSamplePatient(e.target.value)}
              disabled={samplePatientLoading || samplePatients.length === 0}
            >
              <option value="">
                {samplePatients.length === 0 ? "Aucun patient simulé disponible" : "Sélectionnez un patient..."}
              </option>
              {samplePatients.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </Select>
            {samplePatientLoading && <span className="text-sm text-muted-foreground">Chargement...</span>}
            {samplePatientsError && (
              <Banner tone="error">Impossible de charger la liste des patients : {samplePatientsError}</Banner>
            )}
          </div>

          <form onSubmit={onSubmit} className="flex flex-col items-start gap-4">
            <TextArea
              value={transcript}
              onChange={(e) => onTranscriptChange(e.target.value)}
              rows={12}
              className="w-full"
              placeholder="Collez la transcription de la consultation ici, ou sélectionnez un patient simulé ci-dessus..."
            />
            <Button type="submit" disabled={loading || !transcript.trim() || !selectedPatient}>
              {loading ? "Extraction en cours..." : "Extraire les codes de facturation"}
            </Button>
          </form>
        </Card>
      )}
    </>
  );
}
