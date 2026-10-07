import { Fragment, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ChevronRight, RotateCw, Trash2 } from "lucide-react";
import { deleteEncounter, describeError, extractEncounter, type EncounterRow } from "../../../api";
import { Button, CodeChips, RowActions, Spinner, TableCell, TableRow, useConfirm } from "../../../components";
import { formatClinicTime } from "../../../utils/date";
import { formatMoney } from "../../../utils/money";
import { sourceLabel } from "../../../utils/sources";
import { AssociatePatient } from "./AssociatePatient";
import { DuplicateBadge, StatusChip } from "./StatusChip";

// Fixed widths, so every day's (and shift's) table lines up with the others whatever its
// rows contain. The header is for screen readers: the cells speak for themselves.
export const ENCOUNTER_COLUMNS = [
  { label: "Reçue", width: "w-[11%]" },
  { label: "Patient", width: "w-[21%]" },
  { label: "Codes", width: "w-[24%]" },
  { label: "Total indicatif", width: "w-[11%]" },
  { label: "Statut", width: "w-[15%]" },
  { label: "Actions", width: "w-[18%]" },
] as const;

interface EncounterRowItemProps {
  row: EncounterRow;
  // Something about the row changed server-side (patient picked, extraction run).
  onChanged: () => void;
  onOpenDuplicate: (row: EncounterRow) => void;
}

// What the codes cell says before there are codes to show.
function noCodesText(row: EncounterRow): string {
  if (row.status === "à associer") return "Patient à associer d'abord";
  if (row.status === "échec") return "Extraction échouée";
  if (row.codes === null) return "Extraction en attente";
  const toChoose = row.code_count ?? 0;
  if (toChoose > 0) return `${toChoose} code${toChoose > 1 ? "s" : ""} à confirmer`;
  return "Aucun code proposé";
}

export function EncounterRowItem({ row, onChanged, onOpenDuplicate }: EncounterRowItemProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { confirm, dialog } = useConfirm();
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

  async function handleDelete() {
    const confirmed = await confirm({
      title: "Supprimer la rencontre ?",
      message: "La rencontre et ses extractions seront supprimées. Cette action est irréversible.",
      confirmLabel: "Supprimer",
      tone: "danger",
    });
    if (!confirmed) return;
    setError(null);
    try {
      await deleteEncounter(row.id);
      onChanged();
    } catch (err) {
      setError(describeError(err));
    }
  }

  // Remembers the list's period and filters for the encounter page's "back".
  const open = () => navigate(`/app/inbox/${row.id}`, { state: { inboxSearch: location.search } });
  const canExtract = row.patient !== null && (row.status === "reçu" || row.status === "échec");
  const hasCodes = row.codes !== null && row.codes.length > 0;

  // The one thing to do next on this row; the rest is in its "⋯" menu.
  let primary = (
    <Button type="button" variant="ghost" className="text-muted-foreground" onClick={open} aria-label="Ouvrir">
      <ChevronRight aria-hidden />
    </Button>
  );
  if (row.status === "prêt") {
    primary = (
      <Button type="button" onClick={open}>
        Réviser
      </Button>
    );
  } else if (row.status === "à associer" && !associating) {
    primary = (
      <Button type="button" variant="secondary" onClick={() => setAssociating(true)}>
        Associer un patient
      </Button>
    );
  } else if (canExtract) {
    primary = (
      <Button type="button" variant="secondary" onClick={handleExtract} disabled={extracting}>
        {extracting ? (
          <Spinner label="Extraction…" />
        ) : row.status === "échec" ? (
          <>
            <RotateCw aria-hidden />
            Réessayer
          </>
        ) : (
          "Extraire"
        )}
      </Button>
    );
  }

  return (
    <Fragment>
      {dialog}
      <TableRow
        className="cursor-pointer"
        tabIndex={0}
        onClick={(event) => {
          // Clicks on the row's own buttons do their own thing.
          if (!(event.target as HTMLElement).closest("button, a, [role=menuitem]")) open();
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" && event.target === event.currentTarget) open();
        }}
      >
        <TableCell className="py-3 pl-4">
          <span className="block text-sm tabular-nums">{formatClinicTime(row.received_at)}</span>
          <span className="block truncate text-xs text-muted-foreground">{sourceLabel(row.source_system)}</span>
        </TableCell>
        <TableCell className="truncate py-3">
          {row.patient ? (
            <>
              <span className="font-semibold">{row.patient.display_name}</span>
              {row.patient.nam && <span className="block font-mono text-xs text-muted-foreground">{row.patient.nam}</span>}
            </>
          ) : (
            <span className="text-muted-foreground italic">Patient inconnu</span>
          )}
        </TableCell>
        <TableCell className="py-3 whitespace-normal">
          {hasCodes ? (
            <CodeChips codes={row.codes!} max={3} />
          ) : (
            <span className="text-sm text-muted-foreground">{noCodesText(row)}</span>
          )}
        </TableCell>
        <TableCell className="py-3 font-semibold tabular-nums">
          {row.indicative_total != null ? formatMoney(row.indicative_total) : <span className="text-muted-foreground">—</span>}
        </TableCell>
        <TableCell className="py-3">
          <div className="flex flex-wrap items-center gap-1.5">
            <StatusChip status={row.status} />
            {row.possible_duplicate_ids.length > 0 && <DuplicateBadge onClick={() => onOpenDuplicate(row)} />}
          </div>
        </TableCell>
        <TableCell className="py-2.5 pr-3">
          <div className="flex items-center justify-end gap-1">
            {primary}
            <RowActions
              label={`Actions — ${row.patient?.display_name ?? "rencontre"}`}
              actions={[{ label: "Supprimer", icon: Trash2, danger: true, onSelect: handleDelete, disabled: !row.deletable }]}
            />
          </div>
        </TableCell>
      </TableRow>
      {associating && (
        <TableRow className="hover:bg-transparent">
          <TableCell colSpan={ENCOUNTER_COLUMNS.length} className="bg-muted/40 px-4">
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
          <TableCell colSpan={ENCOUNTER_COLUMNS.length} className="px-4 text-sm whitespace-normal text-destructive">
            {error}
          </TableCell>
        </TableRow>
      )}
    </Fragment>
  );
}
