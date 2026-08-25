import type { FormEvent } from "react";
import { Banner, Button, Card, Select, TextArea } from "../../../components";
import type { SamplePatientSummary } from "../../../api";

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
}

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
}: SourceStepProps) {
  return (
    <>
      <ol className="source-list">
        <li>
          <button
            type="button"
            className={`source-card${source === "simule" ? " selected" : ""}`}
            onClick={() => onChooseSource("simule")}
          >
            Patient simulé
          </button>
        </li>
        <li>
          <button type="button" className="source-card" disabled>
            Epic
            <span className="source-card-badge">Bientôt disponible</span>
          </button>
        </li>
        <li>
          <button type="button" className="source-card" disabled>
            Telus Health
            <span className="source-card-badge">Bientôt disponible</span>
          </button>
        </li>
      </ol>

      {source && (
        <Card>
          <div className="field-row">
            <label htmlFor="patient-select">Patient simulé :</label>
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
            {samplePatientLoading && <span className="status-inline">Chargement...</span>}
            {samplePatientsError && (
              <Banner tone="error">Impossible de charger la liste des patients : {samplePatientsError}</Banner>
            )}
          </div>

          <form onSubmit={onSubmit}>
            <TextArea
              value={transcript}
              onChange={(e) => onTranscriptChange(e.target.value)}
              rows={12}
              placeholder="Collez la transcription de la consultation ici, ou sélectionnez un patient simulé ci-dessus..."
            />
            <Button type="submit" disabled={loading || !transcript.trim()}>
              {loading ? "Extraction en cours..." : "Extraire les codes de facturation"}
            </Button>
          </form>
        </Card>
      )}
    </>
  );
}
