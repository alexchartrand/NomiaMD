import { ChevronRight } from "lucide-react";
import { Link } from "react-router-dom";
import type { Dashboard } from "../../../api";
import { DeadlineList } from "./DeadlineList";
import { formatMoney, inboxUrl, plural } from "./format";
import { Panel } from "./Panel";

interface Task {
  label: string;
  detail?: string;
  to: string;
}

function tasksOf({ tasks, kpis }: Dashboard): Task[] {
  const list: (Task | false)[] = [
    tasks.to_review > 0 && {
      label: plural(tasks.to_review, "note à réviser", "notes à réviser"),
      detail: tasks.approvable > 0 ? plural(tasks.approvable, "approuvable en lot", "approuvables en lot") : undefined,
      to: inboxUrl("prêt"),
    },
    tasks.to_associate > 0 && {
      label: plural(tasks.to_associate, "note à associer à un patient", "notes à associer à un patient"),
      to: inboxUrl("à associer"),
    },
    tasks.failed > 0 && {
      label: plural(tasks.failed, "extraction en échec", "extractions en échec"),
      detail: "à relancer",
      to: inboxUrl("échec"),
    },
    tasks.possible_duplicates > 0 && {
      label: plural(tasks.possible_duplicates, "doublon possible à confirmer", "doublons possibles à confirmer"),
      to: inboxUrl("à traiter"),
    },
    tasks.extracting > 0 && {
      label: plural(tasks.extracting, "note en attente d'extraction", "notes en attente d'extraction"),
      to: inboxUrl("reçu"),
    },
    kpis.draft_count > 0 && {
      label: plural(kpis.draft_count, "réclamation à facturer", "réclamations à facturer"),
      detail: formatMoney(kpis.draft_total),
      to: "/app/facturation",
    },
  ];
  return list.filter((task): task is Task => task !== false);
}

export function TaskList({ dashboard }: { dashboard: Dashboard }) {
  const tasks = tasksOf(dashboard);
  return (
    <Panel title="À faire">
      {tasks.length === 0 ? (
        <p className="text-sm text-muted-foreground">Rien à faire — tout est à jour.</p>
      ) : (
        <ul className="-mx-2 flex flex-col">
          {tasks.map((task) => (
            <li key={task.label}>
              <Link
                to={task.to}
                className="flex items-center gap-3 rounded-lg px-2 py-2 text-sm text-foreground no-underline transition-colors hover:bg-accent"
              >
                <span className="font-semibold">{task.label}</span>
                {task.detail && <span className="text-muted-foreground">· {task.detail}</span>}
                <ChevronRight aria-hidden className="ml-auto size-4 text-muted-foreground" />
              </Link>
            </li>
          ))}
        </ul>
      )}
      {dashboard.deadlines.length > 0 && <DeadlineList items={dashboard.deadlines} />}
    </Panel>
  );
}
