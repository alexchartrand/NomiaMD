import { Link } from "react-router-dom";
import type { EncounterRow } from "../../../api";
import { clinicDayOf, formatDate } from "../../../utils/date";
import { StatusChip } from "../InboxPage/StatusChip";
import { Panel, panelLinkClasses } from "./Panel";

export function RecentEncounters({ rows }: { rows: EncounterRow[] }) {
  return (
    <Panel
      title="Dernières rencontres"
      action={
        <Link to="/app/inbox" className={panelLinkClasses}>
          Tout voir
        </Link>
      }
    >
      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">Aucune rencontre reçue pour l'instant.</p>
      ) : (
        <ul className="-mx-2 flex flex-col">
          {rows.map((row) => (
            <li key={row.id}>
              <Link
                to={`/app/inbox/${row.id}`}
                className="flex items-center gap-3 rounded-lg px-2 py-2 text-sm text-foreground no-underline transition-colors hover:bg-accent"
              >
                <span className="w-24 shrink-0 text-muted-foreground">
                  {formatDate(row.service_date ?? clinicDayOf(row.received_at))}
                </span>
                <span className="min-w-0 flex-1 truncate font-semibold">
                  {row.patient?.display_name ?? "Patient à associer"}
                </span>
                <StatusChip status={row.status} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
