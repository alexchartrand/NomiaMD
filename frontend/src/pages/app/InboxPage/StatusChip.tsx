import { CircleAlert, CircleCheck, Copy, type LucideIcon } from "lucide-react";
import type { EncounterStatus } from "../../../api";
import { Badge, type BadgeTone } from "../../../components";

const STATUS: Record<EncounterStatus, { label: string; tone: BadgeTone; icon?: LucideIcon }> = {
  reçu: { label: "Reçu", tone: "neutral" },
  prêt: { label: "Prêt", tone: "primary" },
  revu: { label: "Revu", tone: "success", icon: CircleCheck },
  modifié: { label: "Modifié", tone: "neutral" },
  échec: { label: "Échec", tone: "danger", icon: CircleAlert },
  "à associer": { label: "À associer", tone: "warning" },
};

export function StatusChip({ status }: { status: EncounterStatus }) {
  const { label, tone, icon } = STATUS[status];
  return (
    <Badge tone={tone} icon={icon}>
      {label}
    </Badge>
  );
}

export function DuplicateBadge({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex cursor-pointer items-center gap-1 rounded-full border border-[color:var(--color-warning-text)]/40 bg-[color:var(--color-warning-bg)] px-2.5 py-0.5 text-[0.8rem] font-semibold whitespace-nowrap text-[color:var(--color-warning-text)] transition-colors hover:border-[color:var(--color-warning-text)]"
    >
      <Copy aria-hidden className="size-3.5" />
      Doublon possible
    </button>
  );
}
