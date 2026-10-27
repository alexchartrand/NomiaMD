import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Building2, ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { toast } from "sonner";
import {
  CARE_SETTING_LABELS,
  SHIFT_PERIODS,
  deleteShift,
  describeError,
  listPeriodDefaults,
  listShifts,
  listWorkSites,
  type PeriodDefault,
  type Shift,
  type WorkSite,
} from "../../../api";
import { AppPage, AppPageHeader, Badge, Banner, Button, EmptyState, Spinner, useConfirm } from "../../../components";
import { cn } from "@/lib/utils";
import { addDays, clinicToday, weekdayIndex } from "../../../utils/date";
import { ShiftDialog } from "./ShiftDialog";

const PERIOD_LABELS = Object.fromEntries(SHIFT_PERIODS.map((p) => [p.value, p.label]));

const weekStartOf = (day: string) => addDays(day, -weekdayIndex(day));
const hhmm = (time: string) => time.slice(0, 5);

function dayHeading(day: string): { weekday: string; date: string } {
  const d = new Date(`${day}T00:00:00Z`);
  return {
    weekday: new Intl.DateTimeFormat("fr-CA", { timeZone: "UTC", weekday: "short" }).format(d),
    date: new Intl.DateTimeFormat("fr-CA", { timeZone: "UTC", day: "numeric", month: "short" }).format(d),
  };
}

function weekLabel(start: string): string {
  const format = new Intl.DateTimeFormat("fr-CA", { timeZone: "UTC", day: "numeric", month: "long", year: "numeric" });
  return `Semaine du ${format.format(new Date(`${start}T00:00:00Z`))}`;
}

type DialogState = { shift: Shift | null; day: string } | null;

// The physician's schedule, a week at a time: their shifts at each of their work sites.
export default function SchedulePage() {
  const today = clinicToday();
  const [weekStart, setWeekStart] = useState(() => weekStartOf(today));
  const [sites, setSites] = useState<WorkSite[] | null>(null);
  const [periods, setPeriods] = useState<PeriodDefault[]>([]);
  const [shifts, setShifts] = useState<Shift[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dialog, setDialog] = useState<DialogState>(null);
  const { confirm, dialog: confirmDialog } = useConfirm();

  useEffect(() => {
    Promise.all([listWorkSites(true), listPeriodDefaults()])
      .then(([loadedSites, loadedPeriods]) => {
        setSites(loadedSites);
        setPeriods(loadedPeriods);
      })
      .catch((err) => setError(describeError(err)));
  }, []);

  const loadWeek = useCallback(() => {
    setShifts(null);
    listShifts(weekStart, addDays(weekStart, 6))
      .then(setShifts)
      .catch((err) => setError(describeError(err)));
  }, [weekStart]);

  useEffect(loadWeek, [loadWeek]);

  async function handleDelete(shift: Shift) {
    const confirmed = await confirm({
      title: "Supprimer ce quart ?",
      message: `${shift.work_site_name}, ${hhmm(shift.start_time)}–${hhmm(shift.end_time)}.`,
      confirmLabel: "Supprimer",
      tone: "danger",
    });
    if (!confirmed) return;
    try {
      await deleteShift(shift.id);
      setDialog(null);
      setShifts((current) => current?.filter((s) => s.id !== shift.id) ?? null);
      toast.success("Quart supprimé.");
    } catch (err) {
      toast.error(describeError(err));
    }
  }

  const days = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));
  const hasActiveSite = sites?.some((site) => site.is_active) ?? false;

  return (
    <AppPage width="wide">
      <AppPageHeader
        title="Horaire"
        description="Vos quarts de travail. Le lieu et la période de chaque quart orientent le choix des codes de vos rencontres."
        actions={
          hasActiveSite && (
            <Button onClick={() => setDialog({ shift: null, day: weekStart <= today && today <= days[6] ? today : weekStart })}>
              <Plus aria-hidden className="size-4" />
              Ajouter un quart
            </Button>
          )
        }
      />

      {error && <Banner tone="error">{error}</Banner>}

      {sites !== null && !hasActiveSite && (
        <EmptyState
          icon={Building2}
          title="Aucun lieu de travail"
          description="Ajoutez d'abord les lieux où vous travaillez — urgence, unité, CHSLD ou GMF — dans votre profil."
          action={
            <Button asChild variant="secondary">
              <Link to="/app/profile">Ajouter un lieu</Link>
            </Button>
          }
          className="mb-6"
        />
      )}

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Button variant="secondary" size="icon" aria-label="Semaine précédente" onClick={() => setWeekStart(addDays(weekStart, -7))}>
          <ChevronLeft aria-hidden className="size-4" />
        </Button>
        <Button variant="secondary" size="icon" aria-label="Semaine suivante" onClick={() => setWeekStart(addDays(weekStart, 7))}>
          <ChevronRight aria-hidden className="size-4" />
        </Button>
        <Button variant="ghost" onClick={() => setWeekStart(weekStartOf(today))}>
          Aujourd&apos;hui
        </Button>
        <h2 className="m-0 ml-2 font-heading text-lg font-semibold">{weekLabel(weekStart)}</h2>
      </div>

      {shifts === null && !error ? (
        <Spinner />
      ) : (
        <ol className="m-0 grid list-none gap-2 p-0 md:grid-cols-7">
          {days.map((day) => {
            const heading = dayHeading(day);
            const dayShifts = shifts?.filter((shift) => shift.service_date === day) ?? [];
            return (
              <li
                key={day}
                aria-label={day}
                className={cn(
                  "flex min-h-32 flex-col gap-2 rounded-xl border border-border bg-card p-2",
                  day === today && "border-primary",
                )}
              >
                <div className="flex items-center justify-between px-1">
                  <span className="text-sm">
                    <span className="font-semibold capitalize">{heading.weekday}</span>{" "}
                    <span className="text-muted-foreground">{heading.date}</span>
                  </span>
                  {hasActiveSite && (
                    <button
                      type="button"
                      aria-label={`Ajouter un quart le ${day}`}
                      onClick={() => setDialog({ shift: null, day })}
                      className="inline-flex size-6 cursor-pointer items-center justify-center rounded-md border-none bg-transparent text-muted-foreground hover:bg-accent hover:text-foreground"
                    >
                      <Plus aria-hidden className="size-4" />
                    </button>
                  )}
                </div>
                {dayShifts.map((shift) => (
                  <button
                    key={shift.id}
                    type="button"
                    onClick={() => setDialog({ shift, day })}
                    className="flex cursor-pointer flex-col items-start gap-1 rounded-lg border-none bg-[color:var(--color-primary-tint)] p-2 text-left transition-colors hover:bg-accent"
                  >
                    <span className="text-sm font-semibold">
                      {hhmm(shift.start_time)}–{hhmm(shift.end_time)}
                      {shift.ends_next_day && <span className="font-normal text-muted-foreground"> +1</span>}
                    </span>
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
                  </button>
                ))}
              </li>
            );
          })}
        </ol>
      )}

      {dialog && sites && (
        <ShiftDialog
          shift={dialog.shift}
          day={dialog.day}
          sites={sites}
          periods={periods}
          onClose={() => setDialog(null)}
          onSaved={() => {
            setDialog(null);
            loadWeek();
            toast.success("Horaire mis à jour.");
          }}
          onDelete={(shift) => void handleDelete(shift)}
        />
      )}
      {confirmDialog}
    </AppPage>
  );
}
