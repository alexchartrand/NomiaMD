import { useEffect, useMemo, useState } from "react";
import { CalendarSearch, SearchX } from "lucide-react";
import { deleteClaim, describeError, type Bill, type Claim } from "../../../api";
import { Banner, Button, EmptyState, Skeleton, Tabs, useConfirm } from "../../../components";
import { clinicToday, formatDate } from "../../../utils/date";
import type { Period } from "../../../utils/periods";
import { ClaimFiltersBar } from "./ClaimFiltersBar";
import { matches, NO_FILTERS, statusTabs, type ClaimFilters, type ClaimStatusFilter } from "./claimFilters";
import { ClaimsTable } from "./ClaimsTable";
import { SelectionBar } from "./SelectionBar";
import { useClaims } from "./useClaims";

interface RecordsTabProps {
  reloadSignal: number;
  // Kept in the URL by the page, so the dashboard can link to the drafts.
  period: Period;
  onPeriodChange: (period: Period) => void;
  filters: ClaimFilters;
  onFiltersChange: (filters: ClaimFilters) => void;
  // Asked by "Créer une facture" (or the dashboard's link): tick every draft shown, once
  // the claims are in, then say how many with `onSelectAllDone`.
  selectAll: boolean;
  onSelectAllDone: (count: number) => void;
  onBillCreated: (bill: Bill) => void;
}

// The claims over a period, filtered like the inbox; the drafts are ticked straight in the
// list and billed together.
export function RecordsTab({
  reloadSignal,
  period,
  onPeriodChange,
  filters,
  onFiltersChange,
  selectAll,
  onSelectAllDone,
  onBillCreated,
}: RecordsTabProps) {
  const { confirm, dialog } = useConfirm();
  const { claims, loading, error, reload } = useClaims(period, reloadSignal);
  const [actionError, setActionError] = useState<string | null>(null);
  const [selection, setSelection] = useState<Set<number>>(new Set());
  const today = clinicToday();

  const sources = useMemo(
    () => [...new Set(claims.map((claim) => claim.source_system).filter((source): source is string => Boolean(source)))].sort(),
    [claims],
  );
  const shown = useMemo(
    () => claims.filter((claim) => matches(claim, filters, today)),
    [claims, filters.status, filters.source, filters.patient, today],
  );
  const tabs = useMemo(() => statusTabs(claims, filters, today), [claims, filters.status, filters.source, filters.patient, today]);
  const shownDrafts = useMemo(() => shown.filter((claim) => claim.status === "brouillon"), [shown]);
  // What you see is what you bill: a claim ticked, then filtered out of view, isn't billed.
  const selected = shownDrafts.filter((claim) => selection.has(claim.id));

  useEffect(() => {
    if (!selectAll || loading) return;
    setSelection(new Set(shownDrafts.map((claim) => claim.id)));
    onSelectAllDone(shownDrafts.length);
  }, [selectAll, loading, shownDrafts, onSelectAllDone]);

  function toggle(id: number) {
    setSelection((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    const allTicked = selected.length === shownDrafts.length;
    setSelection((prev) => {
      const next = new Set(prev);
      for (const claim of shownDrafts) {
        if (allTicked) next.delete(claim.id);
        else next.add(claim.id);
      }
      return next;
    });
  }

  async function handleDelete(claim: Claim) {
    const confirmed = await confirm({
      title: "Supprimer la réclamation ?",
      message: `La réclamation de ${claim.patient_full_name} du ${formatDate(claim.service_date)} sera supprimée. Cette action est irréversible.`,
      confirmLabel: "Supprimer",
      tone: "danger",
    });
    if (!confirmed) return;
    setActionError(null);
    try {
      await deleteClaim(claim.id);
      await reload();
    } catch (err) {
      setActionError(describeError(err));
    }
  }

  const clearFilters = () => onFiltersChange(NO_FILTERS);

  return (
    <>
      {dialog}
      <ClaimFiltersBar
        period={period}
        onPeriodChange={onPeriodChange}
        filters={filters}
        onFiltersChange={onFiltersChange}
        sources={sources}
      />

      <Tabs<ClaimStatusFilter>
        ariaLabel="Statut"
        className="mt-5"
        items={tabs.map((tab) => ({ id: tab.id, label: tab.label, count: loading ? undefined : tab.count }))}
        value={filters.status}
        onChange={(status) => onFiltersChange({ ...filters, status })}
      />

      <div className="mt-5 flex flex-col gap-4">
        {error && <Banner tone="error">{error}</Banner>}
        {actionError && <Banner tone="error">{actionError}</Banner>}

        {loading ? (
          <div aria-busy="true" aria-label="Chargement des réclamations" className="flex flex-col gap-2">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-12 rounded-lg" />
            ))}
          </div>
        ) : shown.length === 0 ? (
          claims.length === 0 ? (
            <EmptyState
              icon={CalendarSearch}
              title="Aucune réclamation pour cette période."
              description="Les réclamations apparaissent ici dès que vous enregistrez la révision d'une rencontre."
            />
          ) : (
            <EmptyState
              icon={SearchX}
              title="Aucune réclamation ne correspond aux filtres."
              action={
                <Button type="button" variant="secondary" onClick={clearFilters}>
                  Effacer les filtres
                </Button>
              }
            />
          )
        ) : (
          <div>
            <ClaimsTable
              claims={shown}
              selected={selection}
              onToggle={toggle}
              onToggleAll={toggleAll}
              onDelete={handleDelete}
              today={today}
            />
            <SelectionBar
              selected={selected}
              onClear={() => setSelection(new Set())}
              onCreated={(bill) => {
                setSelection(new Set());
                onBillCreated(bill);
              }}
              onStale={() => {
                setSelection(new Set());
                void reload();
              }}
            />
          </div>
        )}
      </div>
    </>
  );
}
