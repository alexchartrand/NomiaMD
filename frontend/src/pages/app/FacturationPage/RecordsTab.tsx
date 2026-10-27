import { useEffect, useMemo, useState } from "react";
import { CalendarSearch, SearchX } from "lucide-react";
import { deleteClaim, deleteShiftClaim, describeError, type Bill, type Claim, type ShiftClaim } from "../../../api";
import { Banner, Button, EmptyState, Skeleton, Tabs, useConfirm } from "../../../components";
import { clinicToday, formatDate } from "../../../utils/date";
import type { Period } from "../../../utils/periods";
import { ClaimFiltersBar } from "./ClaimFiltersBar";
import { matches, matchesShift, NO_FILTERS, statusTabs, type ClaimFilters, type ClaimStatusFilter } from "./claimFilters";
import { ClaimsTable } from "./ClaimsTable";
import { SelectionBar } from "./SelectionBar";
import { ShiftClaimsTable } from "./ShiftClaimsTable";
import { useClaims } from "./useClaims";
import { useShiftClaims } from "./useShiftClaims";

interface RecordsTabProps {
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

// The claims over a period, filtered like the inbox — the patients' claims, then the shifts'
// own; the drafts are ticked straight in the lists and billed together.
export function RecordsTab({
  period,
  onPeriodChange,
  filters,
  onFiltersChange,
  selectAll,
  onSelectAllDone,
  onBillCreated,
}: RecordsTabProps) {
  const { confirm, dialog } = useConfirm();
  const { claims, loading: claimsLoading, error: claimsError, reload: reloadClaims } = useClaims(period);
  const { shiftClaims, loading: shiftsLoading, error: shiftsError, reload: reloadShifts } = useShiftClaims(period);
  const loading = claimsLoading || shiftsLoading;
  const error = claimsError ?? shiftsError;
  const reload = () => Promise.all([reloadClaims(), reloadShifts()]);
  const [actionError, setActionError] = useState<string | null>(null);
  const [selection, setSelection] = useState<Set<number>>(new Set());
  const [shiftSelection, setShiftSelection] = useState<Set<number>>(new Set());
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
  const shiftsShown = useMemo(
    () => shiftClaims.filter((claim) => matchesShift(claim, filters, today)),
    [shiftClaims, filters.status, filters.source, filters.patient, today],
  );
  const shiftDrafts = useMemo(() => shiftsShown.filter((claim) => claim.status === "brouillon"), [shiftsShown]);
  // What you see is what you bill: a claim ticked, then filtered out of view, isn't billed.
  const selected = shownDrafts.filter((claim) => selection.has(claim.id));
  const selectedShifts = shiftDrafts.filter((claim) => shiftSelection.has(claim.id));

  useEffect(() => {
    if (!selectAll || loading) return;
    setSelection(new Set(shownDrafts.map((claim) => claim.id)));
    setShiftSelection(new Set(shiftDrafts.map((claim) => claim.id)));
    onSelectAllDone(shownDrafts.length + shiftDrafts.length);
  }, [selectAll, loading, shownDrafts, shiftDrafts, onSelectAllDone]);

  function toggleIn(setter: typeof setSelection, id: number) {
    setter((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const toggle = (id: number) => toggleIn(setSelection, id);

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

  async function handleDeleteShift(claim: ShiftClaim) {
    const confirmed = await confirm({
      title: "Supprimer la réclamation du quart ?",
      message: `La réclamation du quart ${claim.work_site_name} du ${formatDate(claim.service_date)} sera supprimée. Le quart reste à l'horaire.`,
      confirmLabel: "Supprimer",
      tone: "danger",
    });
    if (!confirmed) return;
    setActionError(null);
    try {
      await deleteShiftClaim(claim.id);
      await reloadShifts();
    } catch (err) {
      setActionError(describeError(err));
    }
  }

  const clearFilters = () => onFiltersChange(NO_FILTERS);
  const clearSelection = () => {
    setSelection(new Set());
    setShiftSelection(new Set());
  };
  const selectionBar = (
    <SelectionBar
      selected={selected}
      selectedShifts={selectedShifts}
      onClear={clearSelection}
      onCreated={(bill) => {
        clearSelection();
        // The billed drafts are now submitted.
        void reload();
        onBillCreated(bill);
      }}
      onStale={() => {
        clearSelection();
        void reload();
      }}
    />
  );

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
        ) : shown.length === 0 && shiftsShown.length === 0 ? (
          claims.length === 0 && shiftClaims.length === 0 ? (
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
          <>
            {shown.length > 0 && (
              <ClaimsTable
                claims={shown}
                selected={selection}
                onToggle={toggle}
                onToggleAll={toggleAll}
                onDelete={handleDelete}
                today={today}
                filtersKey={JSON.stringify([period.date_from, period.date_to, filters])}
                // The selection's bar closes the last list shown.
                footer={shiftsShown.length === 0 ? selectionBar : undefined}
              />
            )}
            {shiftsShown.length > 0 && (
              <ShiftClaimsTable
                claims={shiftsShown}
                selected={shiftSelection}
                onToggle={(id) => toggleIn(setShiftSelection, id)}
                onDelete={handleDeleteShift}
                footer={selectionBar}
              />
            )}
          </>
        )}
      </div>
    </>
  );
}
