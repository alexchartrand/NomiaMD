import { useEffect, useState } from "react";
import { describeError, getSamplePatient, listSamplePatients, type SamplePatientSummary } from "../../../api";

interface UseSamplePatientsOptions {
  // Called before a new patient's transcript is loaded, so the caller can clear
  // whatever it derived from the previous transcript/extraction.
  onBeforeSelect: () => void;
  onTranscriptLoaded: (transcript: string) => void;
  onError: (message: string) => void;
}

export function useSamplePatients({ onBeforeSelect, onTranscriptLoaded, onError }: UseSamplePatientsOptions) {
  const [samplePatients, setSamplePatients] = useState<SamplePatientSummary[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [listError, setListError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    listSamplePatients()
      .then(setSamplePatients)
      .catch((err) => setListError(describeError(err)));
  }, []);

  async function select(id: string) {
    setSelectedId(id);
    onBeforeSelect();
    if (!id) {
      onTranscriptLoaded("");
      return;
    }
    setLoading(true);
    try {
      const patient = await getSamplePatient(id);
      onTranscriptLoaded(patient.transcript);
    } catch (err) {
      onError(describeError(err));
    } finally {
      setLoading(false);
    }
  }

  return { samplePatients, selectedId, select, listError, loading };
}
