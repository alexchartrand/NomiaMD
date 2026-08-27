import { useState } from "react";
import { cn } from "@/lib/utils";
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
    <section className="max-w-[860px]">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="font-heading text-2xl font-semibold">Facturation</h1>
        <Button type="button" onClick={() => setModalOpen(true)}>
          Créer une facture
        </Button>
      </div>

      <div className="mt-6 mb-4 flex gap-1 border-b border-border">
        <button
          type="button"
          className={cn(
            "cursor-pointer border-b-2 border-transparent px-[0.9rem] py-[0.6rem] text-sm text-muted-foreground hover:text-foreground",
            tab === "records" && "border-primary font-semibold text-primary",
          )}
          onClick={() => setTab("records")}
        >
          Réclamations
        </button>
        <button
          type="button"
          className={cn(
            "cursor-pointer border-b-2 border-transparent px-[0.9rem] py-[0.6rem] text-sm text-muted-foreground hover:text-foreground",
            tab === "bills" && "border-primary font-semibold text-primary",
          )}
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
