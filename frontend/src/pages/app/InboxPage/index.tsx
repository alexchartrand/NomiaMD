import { useMemo, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import type { EncounterPeriod, EncounterRow } from "../../../api";
import { Banner, Button, Spinner, Table, TableBody, TableHead, TableHeader, TableRow } from "../../../components";
import { formatLongDate } from "../../../utils/date";
import type { ReceivedSummary } from "../AddNotesPage";
import { ApproveAllModal } from "./ApproveAllModal";
import { DuplicateModal } from "./DuplicateModal";
import { ENCOUNTER_COLUMNS, EncounterRowItem } from "./EncounterRowItem";
import { matches, type RowFilters } from "./filters";
import { FiltersBar } from "./FiltersBar";
import { presetPeriod, type PresetId } from "./periods";
import { groupByDay, readFilters, readPeriod, toParams } from "./inboxView";
import { useInbox } from "./useInbox";

function plural(count: number, singular: string, pluralForm: string): string {
  return `${count} ${count > 1 ? pluralForm : singular}`;
}

// "23 rencontres · 19 prêtes · 2 à associer" (+ failures, when there are any).
function countsLine(rows: EncounterRow[]): string {
  const count = (status: EncounterRow["status"]) => rows.filter((row) => row.status === status).length;
  const parts = [
    plural(rows.length, "rencontre", "rencontres"),
    plural(count("prêt"), "prête", "prêtes"),
    `${count("à associer")} à associer`,
  ];
  const failed = count("échec");
  if (failed > 0) parts.push(plural(failed, "échec", "échecs"));
  return parts.join(" · ");
}

function ReceivedBanner({ summary }: { summary: ReceivedSummary }) {
  const parts = [plural(summary.received, "note reçue", "notes reçues")];
  if (summary.duplicates > 0) parts.push(`${plural(summary.duplicates, "déjà reçue", "déjà reçues")} (ignorées)`);
  return <Banner tone="success">{parts.join(" · ")}.</Banner>;
}

// The physician's encounters over a period — a day, or the whole week for whoever bills on
// Friday: what's ready, what needs a patient, and a one-click path for the clean ones.
export default function InboxPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const period = readPeriod(searchParams);
  const filters = readFilters(searchParams);
  const location = useLocation();
  const received = (location.state as { received?: ReceivedSummary } | null)?.received;

  const { rows, loading, error, reload } = useInbox(period);
  const [approving, setApproving] = useState(false);
  const [duplicateOf, setDuplicateOf] = useState<EncounterRow | null>(null);

  const sources = useMemo(() => [...new Set(rows.map((row) => row.source_system))].sort(), [rows]);
  const shown = useMemo(() => rows.filter((row) => matches(row, filters)), [rows, filters.status, filters.source, filters.patient]);
  const cleanRows = useMemo(() => shown.filter((row) => row.all_clean), [shown]);
  const days = useMemo(() => groupByDay(shown), [shown]);

  function changePeriod(next: EncounterPeriod) {
    if (next.date_from && next.date_to && next.date_from > next.date_to) return;
    setSearchParams(toParams(next, filters));
  }

  function changePreset(id: PresetId) {
    changePeriod(presetPeriod(id));
  }

  function changeFilters(next: RowFilters) {
    // Typing in the patient search shouldn't stack a history entry per keystroke.
    setSearchParams(toParams(period, next), { replace: true });
  }

  return (
    <section className="max-w-[1100px]">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
        <h1 className="font-heading text-2xl font-semibold">Rencontres</h1>
        <Button asChild variant="secondary">
          <Link to="/app/ajouter">Ajouter manuellement</Link>
        </Button>
      </div>

      <FiltersBar
        period={period}
        onPeriodChange={changePeriod}
        onPresetChange={changePreset}
        filters={filters}
        onFiltersChange={changeFilters}
        sources={sources}
      />

      <div className="my-5 flex flex-wrap items-center justify-between gap-4">
        <p className="m-0 text-muted-foreground">
          {loading ? "" : countsLine(shown)}
          {!loading && shown.length !== rows.length && ` (sur ${rows.length})`}
        </p>
        <Button type="button" onClick={() => setApproving(true)} disabled={cleanRows.length === 0}>
          Approuver les rencontres prêtes{cleanRows.length > 0 ? ` (${cleanRows.length})` : ""}
        </Button>
      </div>

      {received && <ReceivedBanner summary={received} />}
      {error && <Banner tone="error">{error}</Banner>}

      {loading ? (
        <Spinner label="Chargement..." />
      ) : shown.length === 0 ? (
        <p>{rows.length === 0 ? "Aucune rencontre pour cette période." : "Aucune rencontre ne correspond aux filtres."}</p>
      ) : (
        <div className="flex flex-col gap-8">
          {days.map((group) => (
            <div key={group.day} className="flex flex-col gap-3">
              <h2 className="m-0 font-heading text-lg font-semibold first-letter:uppercase">
                {formatLongDate(group.day)}
                <span className="ml-2 text-sm font-normal text-muted-foreground">
                  {plural(group.batches.reduce((n, batch) => n + batch.rows.length, 0), "rencontre", "rencontres")}
                </span>
              </h2>
              {group.batches.map((batch) => (
                <div key={batch.label ?? ""}>
                  {batch.label !== null && <h3 className="mb-1 text-sm font-semibold text-muted-foreground">{batch.label}</h3>}
                  <Table className="min-w-[760px] table-fixed">
                    <colgroup>
                      {ENCOUNTER_COLUMNS.map((column, i) => (
                        <col key={i} className={column.width} />
                      ))}
                    </colgroup>
                    <TableHeader>
                      <TableRow>
                        {ENCOUNTER_COLUMNS.map((column, i) => (
                          <TableHead key={i}>{column.label}</TableHead>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {batch.rows.map((row) => (
                        <EncounterRowItem key={row.id} row={row} onChanged={reload} onOpenDuplicate={setDuplicateOf} />
                      ))}
                    </TableBody>
                  </Table>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      {approving && <ApproveAllModal rows={cleanRows} onClose={() => setApproving(false)} onApproved={reload} />}
      {duplicateOf && (
        <DuplicateModal
          encounterId={duplicateOf.id}
          otherId={duplicateOf.possible_duplicate_ids[0]}
          onClose={() => setDuplicateOf(null)}
          onResolved={reload}
        />
      )}
    </section>
  );
}
