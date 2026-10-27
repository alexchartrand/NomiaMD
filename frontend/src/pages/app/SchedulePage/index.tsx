import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Building2, ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { toast } from "sonner";
import {
  deleteShift,
  deleteShiftSeries,
  describeError,
  listPeriodDefaults,
  listShifts,
  listWorkSites,
  type PeriodDefault,
  type Shift,
  type WorkSite,
} from "../../../api";
import {
  AppPage,
  AppPageHeader,
  Banner,
  Button,
  EmptyState,
  SegmentedControl,
  Spinner,
  useConfirm,
} from "../../../components";
import { cn } from "@/lib/utils";
import { useStoredFlag } from "@/lib/useStoredFlag";
import { clinicToday } from "../../../utils/date";
import { rangeLabel, sameMonth, step, visibleDays, weekStartOf, type CalendarView } from "./calendar";
import { ShiftCard, hhmm } from "./ShiftCard";
import { ShiftDialog, type SeriesScope } from "./ShiftDialog";

const VIEWS: { id: CalendarView; label: string }[] = [
  { id: "month", label: "Mois" },
  { id: "week", label: "Semaine" },
];

const WEEKDAYS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];

function dayHeading(day: string): { weekday: string; date: string } {
  const d = new Date(`${day}T00:00:00Z`);
  return {
    weekday: new Intl.DateTimeFormat("fr-CA", { timeZone: "UTC", weekday: "short" }).format(d),
    date: new Intl.DateTimeFormat("fr-CA", { timeZone: "UTC", day: "numeric", month: "short" }).format(d),
  };
}

type DialogState = { shift: Shift | null; day: string } | null;

// The physician's schedule — the month, or a week — their shifts at each of their work sites.
export default function SchedulePage() {
  const today = clinicToday();
  // Any day of the week or month on screen.
  const [anchor, setAnchor] = useState(today);
  const [weekView, setWeekView] = useStoredFlag("nomiamd.schedule.week");
  const view: CalendarView = weekView ? "week" : "month";
  const days = visibleDays(view, anchor);
  const first = days[0];
  const last = days[days.length - 1];
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

  const loadShifts = useCallback(() => {
    setShifts(null);
    listShifts(first, last)
      .then(setShifts)
      .catch((err) => setError(describeError(err)));
  }, [first, last]);

  useEffect(loadShifts, [loadShifts]);

  async function handleDelete(shift: Shift, scope: SeriesScope) {
    const hours = `${shift.work_site_name}, ${hhmm(shift.start_time)}–${hhmm(shift.end_time)}`;
    const question = {
      one: { title: "Supprimer ce quart ?", message: `${hours}.` },
      following: { title: "Supprimer ce quart et les suivants ?", message: `${hours}, à partir du ${shift.service_date}.` },
      all: { title: "Supprimer toute la série ?", message: `${hours}, tous les jours de la série.` },
    }[shift.series_id != null ? scope : "one"];
    const confirmed = await confirm({ ...question, confirmLabel: "Supprimer", tone: "danger" });
    if (!confirmed) return;
    try {
      if (shift.series_id != null && scope !== "one")
        await deleteShiftSeries(shift.series_id, scope === "following" ? shift.service_date : null);
      else await deleteShift(shift.id);
      setDialog(null);
      loadShifts();
      toast.success(scope === "one" ? "Quart supprimé." : "Quarts supprimés.");
    } catch (err) {
      toast.error(describeError(err));
    }
  }

  const hasActiveSite = sites?.some((site) => site.is_active) ?? false;

  return (
    <AppPage width="wide">
      <AppPageHeader
        title="Horaire"
        description="Vos quarts de travail. Le lieu et la période de chaque quart orientent le choix des codes de vos rencontres."
        actions={
          hasActiveSite && (
            <Button onClick={() => setDialog({ shift: null, day: first <= today && today <= last ? today : view === "month" ? `${anchor.slice(0, 7)}-01` : first })}>
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
        <Button
          variant="secondary"
          size="icon"
          aria-label={view === "week" ? "Semaine précédente" : "Mois précédent"}
          onClick={() => setAnchor(step(view, anchor, -1))}
        >
          <ChevronLeft aria-hidden className="size-4" />
        </Button>
        <Button
          variant="secondary"
          size="icon"
          aria-label={view === "week" ? "Semaine suivante" : "Mois suivant"}
          onClick={() => setAnchor(step(view, anchor, 1))}
        >
          <ChevronRight aria-hidden className="size-4" />
        </Button>
        <Button variant="ghost" onClick={() => setAnchor(today)}>
          Aujourd&apos;hui
        </Button>
        <h2 className="m-0 ml-2 font-heading text-lg font-semibold">{rangeLabel(view, anchor)}</h2>
        <SegmentedControl
          ariaLabel="Affichage"
          segments={VIEWS}
          value={view}
          onChange={(next) => {
            // Into the week: today's when it's in the month shown, else the month's first.
            if (next === "week" && !(first <= today && today <= last)) setAnchor(weekStartOf(`${anchor.slice(0, 7)}-01`));
            setWeekView(next === "week");
          }}
          className="ml-auto"
        />
      </div>

      {shifts === null && !error ? (
        <Spinner />
      ) : (
        <>
          {view === "month" && (
            <div aria-hidden className="mb-1 hidden grid-cols-7 gap-1 md:grid">
              {WEEKDAYS.map((weekday) => (
                <span key={weekday} className="px-2 text-xs font-semibold text-muted-foreground uppercase">
                  {weekday}
                </span>
              ))}
            </div>
          )}
          <ol className={cn("m-0 grid list-none p-0 md:grid-cols-7", view === "month" ? "gap-1" : "gap-2")}>
            {days.map((day) => {
              const dayShifts = shifts?.filter((shift) => shift.service_date === day) ?? [];
              const outside = view === "month" && !sameMonth(day, anchor);
              const heading = dayHeading(day);
              return (
                <li
                  key={day}
                  aria-label={day}
                  className={cn(
                    "flex flex-col rounded-xl border border-border bg-card",
                    view === "month" ? "min-h-24 gap-1 p-1.5" : "min-h-32 gap-2 p-2",
                    // Out of the month: dimmed, and left off the phone's one-column list.
                    outside && "hidden bg-muted/40 md:flex",
                    day === today && "border-primary",
                  )}
                >
                  <div className="flex items-center justify-between px-1">
                    {view === "month" ? (
                      <span className={cn("text-sm font-semibold", outside && "text-muted-foreground")}>
                        <span className="md:hidden">{heading.weekday} </span>
                        {Number(day.slice(8))}
                      </span>
                    ) : (
                      <span className="text-sm">
                        <span className="font-semibold capitalize">{heading.weekday}</span>{" "}
                        <span className="text-muted-foreground">{heading.date}</span>
                      </span>
                    )}
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
                    <ShiftCard
                      key={shift.id}
                      shift={shift}
                      compact={view === "month"}
                      onOpen={() => setDialog({ shift, day })}
                    />
                  ))}
                </li>
              );
            })}
          </ol>
        </>
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
            loadShifts();
            toast.success("Horaire mis à jour.");
          }}
          onDelete={(shift, scope) => void handleDelete(shift, scope)}
        />
      )}
      {confirmDialog}
    </AppPage>
  );
}
