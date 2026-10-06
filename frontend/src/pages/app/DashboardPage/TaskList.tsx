import type { LucideIcon } from "lucide-react";
import { ChevronRight, Copy, FileWarning, Loader, ReceiptText, ScanSearch, UserRoundPlus } from "lucide-react";
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";
import type { Dashboard } from "../../../api";
import { DeadlineList } from "./DeadlineList";
import { formatMoney, inboxUrl, plural } from "./format";
import { Panel } from "./Panel";

type TaskTone = "primary" | "warning" | "danger" | "neutral";

interface Task {
  label: string;
  detail?: string;
  to: string;
  icon: LucideIcon;
  tone: TaskTone;
}

const TONE_CLASSES: Record<TaskTone, string> = {
  primary: "bg-[color:var(--color-primary-tint)] text-primary",
  warning: "bg-[color:var(--color-warning-bg)] text-[color:var(--color-warning-text)]",
  danger: "bg-[color:var(--color-danger-bg)] text-[color:var(--color-danger)]",
  neutral: "bg-muted text-muted-foreground",
};

function tasksOf({ tasks, kpis }: Dashboard): Task[] {
  const list: (Task | false)[] = [
    tasks.to_review > 0 && {
      label: plural(tasks.to_review, "note à réviser", "notes à réviser"),
      detail: tasks.approvable > 0 ? plural(tasks.approvable, "approuvable en lot", "approuvables en lot") : undefined,
      to: inboxUrl("prêt"),
      icon: ScanSearch,
      tone: "primary",
    },
    tasks.to_associate > 0 && {
      label: plural(tasks.to_associate, "note à associer à un patient", "notes à associer à un patient"),
      to: inboxUrl("à associer"),
      icon: UserRoundPlus,
      tone: "warning",
    },
    tasks.failed > 0 && {
      label: plural(tasks.failed, "extraction en échec", "extractions en échec"),
      detail: "à relancer",
      to: inboxUrl("échec"),
      icon: FileWarning,
      tone: "danger",
    },
    tasks.possible_duplicates > 0 && {
      label: plural(tasks.possible_duplicates, "doublon possible à confirmer", "doublons possibles à confirmer"),
      to: inboxUrl("à traiter"),
      icon: Copy,
      tone: "warning",
    },
    tasks.extracting > 0 && {
      label: plural(tasks.extracting, "note en attente d'extraction", "notes en attente d'extraction"),
      to: inboxUrl("reçu"),
      icon: Loader,
      tone: "neutral",
    },
    kpis.draft_count > 0 && {
      label: plural(kpis.draft_count, "réclamation à facturer", "réclamations à facturer"),
      detail: formatMoney(kpis.draft_total),
      // Straight to the bill: every draft preselected (FacturationPage reads `bill`).
      to: "/app/facturation?bill=1",
      icon: ReceiptText,
      tone: "primary",
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
                className="group flex items-center gap-3 rounded-lg px-2 py-2 text-sm text-foreground no-underline transition-colors hover:bg-accent"
              >
                <span
                  aria-hidden
                  className={cn("flex size-7 shrink-0 items-center justify-center rounded-md", TONE_CLASSES[task.tone])}
                >
                  <task.icon className="size-4" />
                </span>
                <span className="font-semibold">{task.label}</span>
                {task.detail && <span className="text-muted-foreground">· {task.detail}</span>}
                <ChevronRight
                  aria-hidden
                  className="ml-auto size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5"
                />
              </Link>
            </li>
          ))}
        </ul>
      )}
      {dashboard.deadlines.length > 0 && <DeadlineList items={dashboard.deadlines} />}
    </Panel>
  );
}
