import { CARE_SETTING_LABELS, SHIFT_PERIODS, type Shift } from "../../../api";
import { Badge } from "../../../components";
import { cn } from "@/lib/utils";

const PERIOD_LABELS = Object.fromEntries(SHIFT_PERIODS.map((p) => [p.value, p.label]));

export const hhmm = (time: string) => time.slice(0, 5);

interface ShiftCardProps {
  shift: Shift;
  // One line (the month grid's small cells) or the full card (the week).
  compact?: boolean;
  onOpen: () => void;
}

// A shift on the calendar; opens it for editing.
export function ShiftCard({ shift, compact = false, onOpen }: ShiftCardProps) {
  const hours = (
    <>
      {hhmm(shift.start_time)}–{hhmm(shift.end_time)}
      {shift.ends_next_day && <span className="font-normal text-muted-foreground"> +1</span>}
    </>
  );
  const title = `${shift.work_site_name} — ${CARE_SETTING_LABELS[shift.care_setting]}, ${PERIOD_LABELS[shift.period]}`;

  return (
    <button
      type="button"
      onClick={onOpen}
      title={compact ? title : undefined}
      className={cn(
        "flex w-full min-w-0 cursor-pointer rounded-lg border-none bg-[color:var(--color-primary-tint)] text-left transition-colors hover:bg-accent",
        compact ? "items-baseline gap-1.5 px-1.5 py-1 text-xs" : "flex-col items-start gap-1 p-2",
        shift.day_type === "ferie" && "ring-1 ring-[color:var(--color-warning-text)]/40",
      )}
    >
      {compact ? (
        <>
          <span className="shrink-0 font-semibold">{hours}</span>
          <span className="truncate">{shift.work_site_name}</span>
        </>
      ) : (
        <>
          <span className="text-sm font-semibold">{hours}</span>
          <span className="text-xs">{shift.work_site_name}</span>
          <span className="flex flex-wrap gap-1">
            <Badge tone="primary" className="text-[0.7rem]">
              {CARE_SETTING_LABELS[shift.care_setting]} · {PERIOD_LABELS[shift.period]}
            </Badge>
            {shift.day_type === "ferie" && (
              <Badge tone="warning" className="text-[0.7rem]">
                Férié
              </Badge>
            )}
          </span>
        </>
      )}
    </button>
  );
}
