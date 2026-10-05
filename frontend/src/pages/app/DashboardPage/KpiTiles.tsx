import type { Dashboard } from "../../../api";
import { formatMoney, monthName, plural } from "./format";

function Tile({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="rounded-xl border border-border bg-card px-5 py-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-1 font-heading text-[1.6rem] font-bold leading-tight">{value}</p>
      {detail && <p className="mt-0.5 text-xs text-muted-foreground">{detail}</p>}
    </div>
  );
}

export function KpiTiles({ dashboard }: { dashboard: Dashboard }) {
  const { tasks, kpis, today } = dashboard;
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Tile label="Notes à traiter" value={String(tasks.to_do)} />
      <Tile label="Rencontres cette semaine" value={String(kpis.encounters_this_week)} />
      <Tile
        label="En brouillon"
        value={formatMoney(kpis.draft_total)}
        detail={plural(kpis.draft_count, "réclamation à facturer", "réclamations à facturer")}
      />
      <Tile label={`Facturé en ${monthName(today)}`} value={formatMoney(kpis.billed_this_month)} />
    </div>
  );
}
