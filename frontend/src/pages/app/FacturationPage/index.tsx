import { useState } from "react";
import { Button } from "../../../components";
import { RecordsTab } from "./RecordsTab";
import { BillsTab } from "./BillsTab";
import { CreateBillModal } from "./CreateBillModal";

type Tab = "records" | "bills";

export default function FacturationPage() {
  const [tab, setTab] = useState<Tab>("records");
  const [modalOpen, setModalOpen] = useState(false);
  // Bumped whenever a bill is created or deleted, so whichever tab is mounted refetches —
  // record statuses and the bills list can each change from the other tab's actions.
  const [reloadSignal, setReloadSignal] = useState(0);

  function handleChanged() {
    setReloadSignal((n) => n + 1);
  }

  return (
    <section className="page-panel">
      <div className="page-header">
        <h1>Facturation</h1>
        <div className="page-header-actions">
          <Button type="button" onClick={() => setModalOpen(true)}>
            Créer une facture
          </Button>
        </div>
      </div>

      <div className="page-tabs">
        <button
          type="button"
          className={`page-tab${tab === "records" ? " page-tab-active" : ""}`}
          onClick={() => setTab("records")}
        >
          Facturations
        </button>
        <button
          type="button"
          className={`page-tab${tab === "bills" ? " page-tab-active" : ""}`}
          onClick={() => setTab("bills")}
        >
          Factures générées
        </button>
      </div>

      {tab === "records" ? (
        <RecordsTab reloadSignal={reloadSignal} />
      ) : (
        <BillsTab reloadSignal={reloadSignal} onChanged={handleChanged} />
      )}

      {modalOpen && (
        <CreateBillModal
          onClose={() => setModalOpen(false)}
          onCreated={() => {
            handleChanged();
            setTab("bills");
          }}
        />
      )}
    </section>
  );
}
