import { useSearchParams } from "react-router-dom";
import { AppPage, AppPageHeader, Tabs } from "../../../components";
import { AuditTab } from "./AuditTab";
import { ContactsTab } from "./ContactsTab";
import { SystemTab } from "./SystemTab";
import { UsageTab } from "./UsageTab";
import { UsersTab } from "./UsersTab";

type Tab = "utilisateurs" | "utilisation" | "journal" | "systeme" | "contacts";

const TABS: { id: Tab; label: string }[] = [
  { id: "utilisateurs", label: "Utilisateurs" },
  { id: "utilisation", label: "Utilisation IA" },
  { id: "journal", label: "Journal" },
  { id: "systeme", label: "Système" },
  { id: "contacts", label: "Demandes de contact" },
];

// The admin console (admins only): accounts, LLM usage and cost, the audit trail, system
// health and the public site's contact requests. The tab lives in the URL.
export default function AdminPage() {
  const [params, setParams] = useSearchParams();
  const requested = params.get("tab");
  const tab: Tab = TABS.some((t) => t.id === requested) ? (requested as Tab) : "utilisateurs";

  return (
    <AppPage>
      <AppPageHeader
        title="Administration"
      />
      <Tabs<Tab>
        ariaLabel="Administration"
        className="mb-5"
        items={TABS}
        value={tab}
        onChange={(id) => setParams(id === "utilisateurs" ? {} : { tab: id })}
      />
      {tab === "utilisateurs" && <UsersTab />}
      {tab === "utilisation" && <UsageTab />}
      {tab === "journal" && <AuditTab />}
      {tab === "systeme" && <SystemTab />}
      {tab === "contacts" && <ContactsTab />}
    </AppPage>
  );
}
