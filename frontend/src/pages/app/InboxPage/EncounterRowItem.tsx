import { Fragment, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { describeError, extractEncounter, type EncounterRow } from "../../../api";
import { Button, TableCell, TableRow } from "../../../components";
import { formatClinicTime } from "../../../utils/date";
import { AssociatePatient } from "./AssociatePatient";
import { DuplicateBadge, StatusChip } from "./StatusChip";

// Fixed widths, so every day's (and shift's) table lines up with the others whatever its
// rows contain — e.g. whether any row shows an "Extraire" button.
export const ENCOUNTER_COLUMNS = [
  { label: "Reçue", width: "w-[10%]" },
  { label: "Patient", width: "w-[20%]" },
  { label: "Source", width: "w-[14%]" },
  { label: "Codes", width: "w-[8%]" },
  { label: "Statut", width: "w-[20%]" },
  { label: "", width: "w-[28%]" },
] as const;

interface EncounterRowItemProps {
  row: EncounterRow;
  // Something about the row changed server-side (patient picked, extraction run).
  onChanged: () => void;
  onOpenDuplicate: (row: EncounterRow) => void;
}

export function EncounterRowItem({ row, onChanged, onOpenDuplicate }: EncounterRowItemProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const [associating, setAssociating] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // A first extraction ("reçu": e.g. seeded, never queued) or a retry ("échec"). Runs in
  // the request, so it waits on the LLM.
  async function handleExtract() {
    setExtracting(true);
    setError(null);
    try {
      await extractEncounter(row.id);
      onChanged();
    } catch (err) {
      setError(describeError(err));
      // The failure was recorded on the encounter: its status is now "échec".
      onChanged();
    } finally {
      setExtracting(false);
    }
  }

  // Remembers the list's period and filters for the encounter page's "back".
  const open = () => navigate(`/app/inbox/${row.id}`, { state: { inboxSearch: location.search } });
  const canExtract = row.patient !== null && (row.status === "reçu" || row.status === "échec");

  return (
    <Fragment>
      <TableRow>
        <TableCell className="text-muted-foreground">{formatClinicTime(row.received_at)}</TableCell>
        <TableCell className="truncate">
          {row.patient ? (
            <>
              <span className="font-semibold">{row.patient.display_name}</span>
              {row.patient.nam && <span className="block font-mono text-xs text-muted-foreground">{row.patient.nam}</span>}
            </>
          ) : (
            <span className="text-muted-foreground">—</span>
          )}
        </TableCell>
        <TableCell className="truncate text-sm">{row.source_system}</TableCell>
        <TableCell>{row.code_count ?? "—"}</TableCell>
        <TableCell>
          <div className="flex flex-wrap items-center gap-1.5">
            <StatusChip status={row.status} />
            {row.possible_duplicate_ids.length > 0 && <DuplicateBadge onClick={() => onOpenDuplicate(row)} />}
          </div>
        </TableCell>
        <TableCell>
          <div className="flex flex-wrap justify-end gap-2">
            {row.status === "à associer" && !associating && (
              <Button type="button" variant="secondary" onClick={() => setAssociating(true)}>
                Associer un patient
              </Button>
            )}
            {canExtract && (
              <Button type="button" variant="secondary" onClick={handleExtract} disabled={extracting}>
                {extracting ? "Extraction..." : row.status === "échec" ? "Réessayer" : "Extraire"}
              </Button>
            )}
            {row.status === "prêt" ? (
              <Button type="button" onClick={open}>
                Réviser
              </Button>
            ) : (
              <Button type="button" variant="ghost" onClick={open}>
                Voir
              </Button>
            )}
          </div>
        </TableCell>
      </TableRow>
      {associating && (
        <TableRow className="hover:bg-transparent">
          <TableCell colSpan={ENCOUNTER_COLUMNS.length}>
            <AssociatePatient
              encounterId={row.id}
              onAssigned={() => {
                setAssociating(false);
                onChanged();
              }}
              onCancel={() => setAssociating(false)}
            />
          </TableCell>
        </TableRow>
      )}
      {error && (
        <TableRow className="hover:bg-transparent">
          <TableCell colSpan={ENCOUNTER_COLUMNS.length} className="text-sm whitespace-normal text-destructive">
            {error}
          </TableCell>
        </TableRow>
      )}
    </Fragment>
  );
}
