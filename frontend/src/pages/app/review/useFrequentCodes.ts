import { useEffect, useState } from "react";
import { describeError, searchCodes, type CodeHit } from "../../../api";

const FREQUENT_LIMIT = 12;

// The codes the physician bills most (GET /codes/search with no query), most billed first.
// With a patient, only the ones that patient may be billed on serviceDate.
export function useFrequentCodes(patientId: number | null = null, serviceDate: string | null = null) {
  const [codes, setCodes] = useState<CodeHit[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    setLoading(true);
    searchCodes({ patientId, serviceDate, limit: FREQUENT_LIMIT })
      .then((found) => {
        if (!current) return;
        setCodes(found);
        setError(null);
      })
      .catch((err) => current && setError(describeError(err)))
      .finally(() => current && setLoading(false));
    return () => {
      current = false;
    };
  }, [patientId, serviceDate]);

  return { codes, loading, error };
}
