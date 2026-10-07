import { CircleAlert, Clock } from "lucide-react";
import { Link } from "react-router-dom";
import type { DeadlineItem } from "../../../api";
import { Badge } from "../../../components";
import { formatDate } from "../../../utils/date";

const SHOWN = 5;

function DaysLeft({ days }: { days: number }) {
  const overdue = days <= 0;
  const label = days < 0 ? `Délai dépassé de ${days * -1} j` : days === 0 ? "Dernier jour" : `${days} j restants`;
  return (
    <Badge tone={overdue ? "danger" : "warning"} icon={overdue ? CircleAlert : Clock}>
      {label}
    </Badge>
  );
}

// Unbilled work closest to RAMQ's 90-day billing limit (most urgent first, as served).
export function DeadlineList({ items }: { items: DeadlineItem[] }) {
  const hidden = items.length - SHOWN;
  return (
    <div className="mt-4 border-t border-border pt-4">
      <h3 className="text-sm font-semibold">Délai de facturation RAMQ (90 jours)</h3>
      <ul className="-mx-2 mt-2 flex flex-col">
        {items.slice(0, SHOWN).map((item) => (
          <li key={`${item.kind}-${item.id}`}>
            <Link
              to={item.kind === "encounter" ? `/app/inbox/${item.id}` : "/app/facturation"}
              className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg px-2 py-2 text-sm text-foreground no-underline transition-colors hover:bg-accent"
            >
              <span className="font-semibold">{item.patient_display ?? "Patient à associer"}</span>
              <span className="text-muted-foreground">
                {item.kind === "encounter" ? "Note" : "Réclamation"} du {formatDate(item.service_date)}
              </span>
              <span className="ml-auto">
                <DaysLeft days={item.days_left} />
              </span>
            </Link>
          </li>
        ))}
      </ul>
      {hidden > 0 && (
        <p className="mt-1 px-0 text-xs text-muted-foreground">
          et {hidden} autre{hidden > 1 ? "s" : ""} près du délai
        </p>
      )}
    </div>
  );
}
