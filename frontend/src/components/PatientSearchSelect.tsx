import { useEffect, useRef, useState } from "react";
import { describeError, searchPatients, type Patient } from "../api";
import { TextField } from "./TextField";
import { cn } from "@/lib/utils";

interface PatientSearchSelectProps {
  id?: string;
  selected: Patient | null;
  onSelect: (patient: Patient | null) => void;
  placeholder?: string;
  className?: string;
}

// The first typeahead in the codebase — everywhere else only offers a plain native
// <select> (components/Select.tsx) over an already-loaded, small list. A physician's
// roster no longer bounds "which patients exist" (Patient is global now), so picking one
// needs a live search instead.
export function PatientSearchSelect({ id, selected, onSelect, placeholder, className }: PatientSearchSelectProps) {
  const [query, setQuery] = useState(selected?.full_name ?? "");
  const [results, setResults] = useState<Patient[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setQuery(selected?.full_name ?? "");
  }, [selected]);

  useEffect(() => {
    if (selected || query.trim().length < 2) {
      setResults([]);
      return;
    }
    setLoading(true);
    const handle = setTimeout(() => {
      searchPatients(query)
        .then((found) => {
          setResults(found);
          setError(null);
        })
        .catch((err) => setError(describeError(err)))
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(handle);
  }, [query, selected]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function handleInputChange(value: string) {
    setQuery(value);
    setOpen(true);
    if (selected) onSelect(null);
  }

  function handlePick(patient: Patient) {
    onSelect(patient);
    setOpen(false);
  }

  const showDropdown = open && !selected && query.trim().length >= 2;

  return (
    <div ref={containerRef} className={cn("relative w-full max-w-sm", className)}>
      <TextField
        id={id}
        value={query}
        onChange={(e) => handleInputChange(e.target.value)}
        onFocus={() => setOpen(true)}
        placeholder={placeholder ?? "Nom ou NAM du patient..."}
        autoComplete="off"
      />
      {showDropdown && (
        <div className="absolute z-10 mt-1 max-h-64 w-full overflow-y-auto rounded-lg border border-border bg-card shadow-md">
          {loading && <p className="px-3 py-2 text-sm text-muted-foreground">Recherche...</p>}
          {!loading && error && <p className="px-3 py-2 text-sm text-destructive">{error}</p>}
          {!loading && !error && results.length === 0 && (
            <p className="px-3 py-2 text-sm text-muted-foreground">Aucun patient trouvé</p>
          )}
          {!loading &&
            results.map((patient) => (
              <button
                key={patient.id}
                type="button"
                className="block w-full px-3 py-2 text-left text-sm hover:bg-[color:var(--color-primary-tint)]"
                onClick={() => handlePick(patient)}
              >
                {patient.full_name}
                {patient.ramq_number && (
                  <span className="text-muted-foreground"> — {patient.ramq_number}</span>
                )}
              </button>
            ))}
        </div>
      )}
    </div>
  );
}
