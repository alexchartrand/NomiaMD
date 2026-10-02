import { cn } from "@/lib/utils";
import type { EncounterStatus } from "../../../api";

const STATUS_LABELS: Record<EncounterStatus, string> = {
  reçu: "Reçu",
  prêt: "Prêt",
  revu: "Revu",
  modifié: "Modifié",
  échec: "Échec",
  "à associer": "À associer",
};

const STATUS_CLASSES: Record<EncounterStatus, string> = {
  reçu: "bg-muted text-muted-foreground",
  prêt: "bg-[color:var(--color-primary-tint)] text-primary",
  revu: "bg-[color:var(--color-success-bg)] text-[color:var(--color-success-text)]",
  modifié: "bg-muted text-muted-foreground",
  échec: "bg-[color:var(--color-danger-bg)] text-destructive",
  "à associer": "bg-[color:var(--color-warning-bg)] text-[color:var(--color-warning-text)]",
};

const chipClasses = "inline-block whitespace-nowrap rounded-full px-[0.6rem] py-[0.15rem] text-[0.85rem] font-[650]";

export function StatusChip({ status }: { status: EncounterStatus }) {
  return <span className={cn(chipClasses, STATUS_CLASSES[status])}>{STATUS_LABELS[status]}</span>;
}

export function DuplicateBadge({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        chipClasses,
        "cursor-pointer border border-[color:var(--color-warning-text)] bg-[color:var(--color-warning-bg)] text-[color:var(--color-warning-text)] hover:opacity-80",
      )}
    >
      Doublon possible
    </button>
  );
}
