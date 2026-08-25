import { useEffect, useState } from "react";
import { describeError, listPatients, type Patient } from "../../../api";

export function useRoster() {
  const [roster, setRoster] = useState<Patient[]>([]);
  const [error, setError] = useState<string | null>(null);

  function reload() {
    listPatients()
      .then(setRoster)
      .catch((err) => setError(describeError(err)));
  }

  useEffect(reload, []);

  return { roster, error, reload };
}
