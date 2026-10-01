import { useMemo, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import type { EncounterPeriod, EncounterRow } from "../../../api";
import { Banner, Button, Spinner, Table, TableBody, TableHead, TableHeader, TableRow } from "../../../components";
import { clinicDayOf, formatLongDate } from "../../../utils/date";
import type { ReceivedSummary } from "../AddNotesPage";
import { ApproveAllModal } from "./ApproveAllModal";
import { DuplicateModal } from "./DuplicateModal";
import { ENCOUNTER_COLUMNS, EncounterRowItem } from "./EncounterRowItem";
import { matches, type RowFilters, type StatusFilter } from "./filters";
import { FiltersBar } from "./FiltersBar";
import { DEFAULT_PRESET, presetPeriod, type PresetId } from "./periods";
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

interface DayGroup {
  day: string;
  batches: { label: string | null; rows: EncounterRow[] }[];
}

// The day an encounter belongs to: its service date, or the clinic day it was received on
// while it has none (same rule as the server's period filter).
function dayOf(row: EncounterRow): string {
  return row.service_date ?? clinicDayOf(row.received_at);
}

// Most recent day first; within a day, rows by batch label (an ER shift pasted at once) in
// arrival order, rows with no label forming one unnamed batch.
function groupByDay(rows: EncounterRow[]): DayGroup[] {
  const days = new Map<string, Map<string | null, EncounterRow[]>>();
  for (const row of rows) {
    const batches = days.get(dayOf(row)) ?? new Map<string | null, EncounterRow[]>();
    batches.set(row.batch_label, [...(batches.get(row.batch_label) ?? []), row]);
    days.set(dayOf(row), batches);
  }
  return [...days.entries()]
    .sort(([a], [b]) => b.localeCompare(a))
    .map(([day, batches]) => ({ day, batches: [...batches.entries()].map(([label, grouped]) => ({ label, rows: grouped })) }));
}

// The URL holds the period and the filters, so the encounter page's "back" (and a reload)
// lands on the same list. No period in the URL is the default preset; `all` is no bounds.
function readPeriod(params: URLSearchParams): EncounterPeriod {
  if (params.has("all")) return {};
  if (params.has("from") || params.has("to")) return { date_from: params.get("from"), date_to: params.get("to") };
  return presetPeriod(DEFAULT_PRESET);
}

function readFilters(params: URLSearchParams): RowFilters {
  return {
    status: (params.get("status") ?? "") as StatusFilter,
    source: params.get("source") ?? "",
    patient: params.get("patient") ?? "",
  };
}

function toParams(period: EncounterPeriod, filters: RowFilters): Record<string, string> {
  const params: Record<string, string> = {};
  if (!period.date_from && !period.date_to) params.all = "1";
  if (period.date_from) params.from = period.date_from;
  if (period.date_to) params.to = period.date_to;
  if (filters.status) params.status = filters.status;
  if (filters.source) params.source = filters.source;
  if (filters.patient) params.patient = filters.patient;
  return params;
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
                  <Table>
                    <TableHeader>
                      <TableRow>
                        {ENCOUNTER_COLUMNS.map((column) => (
                          <TableHead key={column}>{column}</TableHead>
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
