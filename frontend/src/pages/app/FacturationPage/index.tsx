import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { FilePlus2, ReceiptText } from "lucide-react";
import { toast } from "sonner";
import type { Bill } from "../../../api";
import { AppPage, AppPageHeader, Button, Tabs } from "../../../components";
import { periodToParams, readPeriodParams, type Period } from "../../../utils/periods";
import { BillsTab } from "./BillsTab";
import { claimFiltersToParams, readClaimFilters, type ClaimFilters } from "./claimFilters";
import { RecordsTab } from "./RecordsTab";

type Tab = "reclamations" | "factures";

// The URL holds the tab, its period (all of it by default) and, on the claims, the
// filters — so the dashboard can link to the drafts (`status=brouillon`), and `bill=1` (its
// "réclamations à facturer" task) lands with every draft ticked.
export default function FacturationPage() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get("tab") === "factures" ? "factures" : "reclamations";
  const period = readPeriodParams(params, "all");
  const filters = readClaimFilters(params);
  const [selectAll, setSelectAll] = useState(false);

  function show(next: { tab?: Tab; period: Period; filters?: ClaimFilters }, options?: { replace?: boolean }) {
    setParams(
      {
        ...(next.tab === "factures" ? { tab: "factures" } : {}),
        ...periodToParams(next.period),
        ...(next.filters ? claimFiltersToParams(next.filters) : {}),
      },
      options,
    );
  }

  function changePeriod(next: Period) {
    if (next.date_from && next.date_to && next.date_from > next.date_to) return;
    show({ tab, period: next, filters: tab === "reclamations" ? filters : undefined });
  }

  // The drafts, all ticked: what's still to bill in the period shown.
  function billDrafts(options?: { replace?: boolean }) {
    show({ period, filters: { ...filters, status: "brouillon" } }, options);
    setSelectAll(true);
  }

  useEffect(() => {
    if (params.get("bill") === "1") billDrafts({ replace: true });
    // Only the link the page was opened with: `billDrafts` drops `bill` from the URL.
  }, []);

  const handleSelectAllDone = useCallback((count: number) => {
    setSelectAll(false);
    if (count === 0) toast.info("Aucune réclamation en brouillon à facturer pour cette période.");
  }, []);

  function handleBillCreated(bill: Bill) {
    toast.success(`Facture ${bill.number} générée.`, {
      action: { label: "Voir les factures", onClick: () => setParams({ tab: "factures" }) },
    });
  }

  return (
    <AppPage>
      <AppPageHeader
        title="Facturation"
        description="Vos réclamations enregistrées, et les factures qui les regroupent pour la RAMQ. Cochez les brouillons à facturer."
        actions={
          <>
            <Button asChild variant="secondary">
              <Link to="/app/facturer">
                <ReceiptText aria-hidden />
                Facturer sans rencontre
              </Link>
            </Button>
            <Button type="button" onClick={() => billDrafts()}>
              <FilePlus2 aria-hidden />
              Créer une facture
            </Button>
          </>
        }
      />

      <Tabs<Tab>
        ariaLabel="Facturation"
        className="mb-5"
        items={[
          { id: "reclamations", label: "Réclamations" },
          { id: "factures", label: "Factures générées" },
        ]}
        value={tab}
        // Each tab starts on its default period: a bill's period isn't a claim's date.
        onChange={(id) => setParams(id === "factures" ? { tab: id } : {})}
      />

      {tab === "reclamations" ? (
        <RecordsTab
          period={period}
          onPeriodChange={changePeriod}
          filters={filters}
          // Typing in the patient search shouldn't stack a history entry per keystroke.
          onFiltersChange={(next) => show({ period, filters: next }, { replace: true })}
          selectAll={selectAll}
          onSelectAllDone={handleSelectAllDone}
          onBillCreated={handleBillCreated}
        />
      ) : (
        <BillsTab period={period} onPeriodChange={changePeriod} />
      )}
    </AppPage>
  );
}
