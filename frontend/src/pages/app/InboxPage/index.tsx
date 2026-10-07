import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { CalendarSearch, CheckCheck, FilePlus2, SearchX } from "lucide-react";
import { toast } from "sonner";
import type { EncounterPeriod, EncounterRow } from "../../../api";
import { AppPage, AppPageHeader, Banner, Button, EmptyState, Skeleton, Tabs } from "../../../components";
import { formatMoney } from "../../../utils/money";
import type { ReceivedSummary } from "../AddNotesPage";
import { ApproveAllModal } from "./ApproveAllModal";
import { DayCard } from "./DayCard";
import { DuplicateModal } from "./DuplicateModal";
import { matches, type RowFilters, type StatusFilter } from "./filters";
import { FiltersBar } from "./FiltersBar";
import { groupByDay, readFilters, readPeriod, toParams } from "./inboxView";
import { statusTabs } from "./statusTabs";
import { useInbox } from "./useInbox";

function plural(count: number, singular: string, pluralForm: string): string {
  return `${count} ${count > 1 ? pluralForm : singular}`;
}

function receivedMessage(summary: ReceivedSummary): string {
  const parts = [plural(summary.received, "note reçue", "notes reçues")];
  if (summary.duplicates > 0) parts.push(`${plural(summary.duplicates, "déjà reçue", "déjà reçues")} (ignorées)`);
  return `${parts.join(" · ")}.`;
}

// Notes just added from the Ajouter page: said once, as a toast, then dropped from the
// history entry so a reload doesn't say it again.
function useReceivedToast() {
  const location = useLocation();
  const navigate = useNavigate();
  const received = (location.state as { received?: ReceivedSummary } | null)?.received;
  const shown = useRef(false);
  useEffect(() => {
    if (!received || shown.current) return;
    shown.current = true;
    toast.success(receivedMessage(received));
    navigate(`${location.pathname}${location.search}`, { replace: true, state: null });
  }, [received, location.pathname, location.search, navigate]);
}

// The physician's encounters over a period — a day, or the whole week for whoever bills on
// Friday: what's ready, what needs a patient, and a one-click path for the clean ones.
export default function InboxPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const period = readPeriod(searchParams);
  const filters = readFilters(searchParams);
  useReceivedToast();

  const { rows, loading, error, reload } = useInbox(period);
  const [approving, setApproving] = useState(false);
  const [duplicateOf, setDuplicateOf] = useState<EncounterRow | null>(null);

  const sources = useMemo(() => [...new Set(rows.map((row) => row.source_system))].sort(), [rows]);
  const shown = useMemo(() => rows.filter((row) => matches(row, filters)), [rows, filters.status, filters.source, filters.patient]);
  const tabs = useMemo(() => statusTabs(rows, filters), [rows, filters.source, filters.patient, filters.status]);
  const cleanRows = useMemo(() => shown.filter((row) => row.all_clean), [shown]);
  const cleanTotal = cleanRows.reduce((sum, row) => sum + (row.indicative_total ?? 0), 0);
  const days = useMemo(() => groupByDay(shown), [shown]);

  function changePeriod(next: EncounterPeriod) {
    if (next.date_from && next.date_to && next.date_from > next.date_to) return;
    setSearchParams(toParams(next, filters));
  }

  function changeFilters(next: RowFilters) {
    // Typing in the patient search shouldn't stack a history entry per keystroke.
    setSearchParams(toParams(period, next), { replace: true });
  }

  const addNotes = (
    <Button asChild>
      <Link to="/app/ajouter">
        <FilePlus2 aria-hidden />
        Ajouter des notes
      </Link>
    </Button>
  );

  return (
    <AppPage>
      <AppPageHeader
        title="Rencontres"
        description="Les notes reçues, avec les codes proposés. Révisez-les une à une, ou approuvez en lot celles qui ne présentent aucune ambiguïté."
        actions={addNotes}
      />

      <FiltersBar
        period={period}
        onPeriodChange={changePeriod}
        filters={filters}
        onFiltersChange={changeFilters}
        sources={sources}
      />

      <Tabs<StatusFilter>
        ariaLabel="Statut"
        className="mt-5"
        items={tabs.map((tab) => ({ id: tab.id, label: tab.label, count: loading ? undefined : tab.count }))}
        value={filters.status}
        onChange={(status) => changeFilters({ ...filters, status })}
      />

      {cleanRows.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-primary/25 bg-[color:var(--color-primary-tint)] px-4 py-3">
          <p className="m-0 flex items-center gap-2.5 text-sm">
            <CheckCheck aria-hidden className="size-5 shrink-0 text-primary" />
            <span>
              <span className="font-semibold">{plural(cleanRows.length, "rencontre prête", "rencontres prêtes")} sans ambiguïté</span>
              <span className="text-muted-foreground">
                {" "}
                · codes à confiance élevée, rien à confirmer{cleanTotal > 0 ? ` · ${formatMoney(cleanTotal)}` : ""}
              </span>
            </span>
          </p>
          <Button type="button" onClick={() => setApproving(true)}>
            Approuver en lot ({cleanRows.length})
          </Button>
        </div>
      )}

      <div className="mt-5 flex flex-col gap-5">
        {error && <Banner tone="error">{error}</Banner>}

        {loading ? (
          <div aria-busy="true" aria-label="Chargement des rencontres" className="flex flex-col gap-3">
            <Skeleton className="h-11 rounded-xl" />
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-14 rounded-lg" />
            ))}
          </div>
        ) : shown.length === 0 ? (
          rows.length === 0 ? (
            <EmptyState
              icon={CalendarSearch}
              title="Aucune rencontre pour cette période."
              description="Choisissez une autre période, ou ajoutez les notes signées de vos consultations."
              action={addNotes}
            />
          ) : (
            <EmptyState
              icon={SearchX}
              title="Aucune rencontre ne correspond aux filtres."
              action={
                <Button type="button" variant="secondary" onClick={() => changeFilters({ status: "", source: "", patient: "" })}>
                  Effacer les filtres
                </Button>
              }
            />
          )
        ) : (
          days.map((group) => <DayCard key={group.day} group={group} onChanged={reload} onOpenDuplicate={setDuplicateOf} />)
        )}
      </div>

      {approving && <ApproveAllModal rows={cleanRows} onClose={() => setApproving(false)} onApproved={reload} />}
      {duplicateOf && (
        <DuplicateModal
          encounterId={duplicateOf.id}
          otherId={duplicateOf.possible_duplicate_ids[0]}
          onClose={() => setDuplicateOf(null)}
          onResolved={reload}
        />
      )}
    </AppPage>
  );
}
