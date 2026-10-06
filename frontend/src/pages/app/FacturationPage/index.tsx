import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { FilePlus2, ReceiptText } from "lucide-react";
import { toast } from "sonner";
import { AppPage, AppPageHeader, Button, Tabs } from "../../../components";
import { BillsTab } from "./BillsTab";
import { CreateBillModal } from "./CreateBillModal";
import { RecordsTab, type StatusFilter } from "./RecordsTab";

type Tab = "reclamations" | "factures";

// The URL says which tab, which claim status, and whether the bill dialog is open (`bill=1`,
// what the dashboard's "réclamations à facturer" task links to).
export default function FacturationPage() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get("tab") === "factures" ? "factures" : "reclamations";
  const status = (params.get("status") ?? "") as StatusFilter;
  const billing = params.get("bill") === "1";
  // Bumped whenever a bill is created or deleted, so whichever tab is mounted refetches —
  // record statuses and the bills list can each change from the other tab's actions.
  const [reloadSignal, setReloadSignal] = useState(0);

  // One call per change: react-router doesn't queue search-param updates like setState.
  function update(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    setParams(next, { replace: true });
  }

  function handleChanged() {
    setReloadSignal((n) => n + 1);
  }

  return (
    <AppPage>
      <AppPageHeader
        title="Facturation"
        description="Vos réclamations enregistrées, et les factures qui les regroupent pour la RAMQ."
        actions={
          <>
            <Button asChild variant="secondary">
              <Link to="/app/facturer">
                <ReceiptText aria-hidden />
                Facturer sans rencontre
              </Link>
            </Button>
            <Button type="button" onClick={() => update({ bill: "1" })}>
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
        onChange={(id) => update({ tab: id === "factures" ? id : null })}
      />

      {tab === "reclamations" ? (
        <RecordsTab reloadSignal={reloadSignal} status={status} onStatusChange={(next) => update({ status: next || null })} />
      ) : (
        <BillsTab reloadSignal={reloadSignal} onChanged={handleChanged} />
      )}

      {billing && (
        <CreateBillModal
          onClose={() => update({ bill: null })}
          onCreated={() => {
            handleChanged();
            update({ tab: "factures", bill: null });
            toast.success("Facture générée.");
          }}
        />
      )}
    </AppPage>
  );
}
