import type { LucideIcon } from "lucide-react";
import { CalendarDays, FileClock, Inbox, Landmark } from "lucide-react";
import { Link } from "react-router-dom";
import type { Dashboard } from "../../../api";
import { formatMoney, inboxUrl, monthName, plural } from "./format";

interface TileProps {
  label: string;
  value: string;
  detail?: string;
  icon: LucideIcon;
  to: string;
}

// A headline figure that opens the list behind it.
function Tile({ label, value, detail, icon: Icon, to }: TileProps) {
  return (
    <Link
      to={to}
      className="group relative block rounded-xl border border-border bg-card px-5 py-4 text-foreground no-underline transition-all hover:border-primary/40 hover:shadow-[0_8px_24px_-16px_rgba(18,35,44,0.35)]"
    >
      <span
        aria-hidden
        className="absolute top-4 right-4 flex size-8 items-center justify-center rounded-lg bg-[color:var(--color-primary-tint)] text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground"
      >
        <Icon className="size-4" />
      </span>
      <p className="pr-10 text-sm text-muted-foreground">{label}</p>
      <p className="mt-1 font-heading text-[1.6rem] font-bold leading-tight tabular-nums">{value}</p>
      {detail && <p className="mt-0.5 text-xs text-muted-foreground">{detail}</p>}
    </Link>
  );
}

export function KpiTiles({ dashboard }: { dashboard: Dashboard }) {
  const { tasks, kpis, today } = dashboard;
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Tile label="Notes à traiter" value={String(tasks.to_do)} icon={Inbox} to={inboxUrl("à traiter")} />
      <Tile
        label="Rencontres cette semaine"
        value={String(kpis.encounters_this_week)}
        icon={CalendarDays}
        to="/app/inbox"
      />
      <Tile
        label="En brouillon"
        value={formatMoney(kpis.draft_total)}
        detail={plural(kpis.draft_count, "réclamation à facturer", "réclamations à facturer")}
        icon={FileClock}
        to="/app/facturation?status=brouillon"
      />
      <Tile
        label={`Facturé en ${monthName(today)}`}
        value={formatMoney(kpis.billed_this_month)}
        icon={Landmark}
        to="/app/facturation?tab=factures"
      />
    </div>
  );
}
