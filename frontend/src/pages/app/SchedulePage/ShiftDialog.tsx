import { useState, type FormEvent } from "react";
import {
  CARE_SETTING_LABELS,
  createShift,
  createShiftSeries,
  describeError,
  updateShift,
  updateShiftSeries,
  type PeriodDefault,
  type Shift,
  type ShiftPeriod,
  type WorkSite,
} from "../../../api";
import { Banner, Button, Checkbox, FormField, Modal, SegmentedControl, Select, TextField } from "../../../components";
import { addDays, daysBetween, weekdayIndex } from "../../../utils/date";

interface ShiftDialogProps {
  // null: a new shift on `day`.
  shift: Shift | null;
  day: string;
  sites: WorkSite[];
  periods: PeriodDefault[];
  onClose: () => void;
  onSaved: () => void;
  onDelete: (shift: Shift, scope: SeriesScope) => void;
}

// Which of a series' shifts an edit or a removal applies to.
export type SeriesScope = "one" | "following" | "all";

const SCOPES: { id: SeriesScope; label: string }[] = [
  { id: "one", label: "Ce quart" },
  { id: "following", label: "Ce quart et les suivants" },
  { id: "all", label: "Toute la série" },
];

const hhmm = (time: string) => time.slice(0, 5);

// How many shifts a series from `start` to `end` makes.
function seriesLength(start: string, end: string, weekdaysOnly: boolean): number {
  const span = daysBetween(start, end) + 1;
  if (span < 1) return 0;
  if (!weekdaysOnly) return span;
  return Array.from({ length: span }, (_, i) => addDays(start, i)).filter((day) => weekdayIndex(day) < 5).length;
}

// Add or edit a shift: the site, the day, the period — which fills in its usual hours — and
// the hours actually worked. A new shift can span several days (two weeks at a clinic, a
// week on call): one shift is then saved on each day, same site and hours.
export function ShiftDialog({ shift, day, sites, periods, onClose, onSaved, onDelete }: ShiftDialogProps) {
  const initialPeriod = shift?.period ?? "jour";
  const defaults = (period: ShiftPeriod) => periods.find((p) => p.period === period);

  // A shift on an archived site keeps it pickable while it's being edited.
  const pickable = sites.filter((site) => site.is_active || site.id === shift?.work_site_id);
  const [siteId, setSiteId] = useState<number | "">(shift?.work_site_id ?? pickable[0]?.id ?? "");
  const [serviceDate, setServiceDate] = useState(shift?.service_date ?? day);
  // New shifts only: the last day of the series (the first one when a single day).
  const [lastDate, setLastDate] = useState(day);
  const [weekdaysOnly, setWeekdaysOnly] = useState(false);
  const [period, setPeriod] = useState<ShiftPeriod>(initialPeriod);
  const [startTime, setStartTime] = useState(hhmm(shift?.start_time ?? defaults(initialPeriod)?.start_time ?? "08:00"));
  const [endTime, setEndTime] = useState(hhmm(shift?.end_time ?? defaults(initialPeriod)?.end_time ?? "16:00"));
  const [scope, setScope] = useState<SeriesScope>("one");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function pickPeriod(next: ShiftPeriod) {
    setPeriod(next);
    const hours = defaults(next);
    if (hours) {
      setStartTime(hhmm(hours.start_time));
      setEndTime(hhmm(hours.end_time));
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (siteId === "") {
      setError("Choisissez un lieu de travail.");
      return;
    }
    if (isSeries && count === 0) {
      setError(lastDate < serviceDate ? "La date de fin précède la date de début." : "Aucun jour de semaine dans cette période.");
      return;
    }
    setError(null);
    setSubmitting(true);
    const hours = { work_site_id: siteId, period, start_time: startTime, end_time: endTime };
    try {
      if (shift?.series_id != null && scope !== "one")
        await updateShiftSeries(shift.series_id, { ...hours, from_date: scope === "following" ? shift.service_date : null });
      else if (shift) await updateShift(shift.id, { ...hours, service_date: serviceDate });
      else if (isSeries)
        await createShiftSeries({ ...hours, start_date: serviceDate, end_date: lastDate, weekdays_only: weekdaysOnly });
      else await createShift({ ...hours, service_date: serviceDate });
      onSaved();
    } catch (err) {
      setError(describeError(err));
      setSubmitting(false);
    }
  }

  const endsNextDay = endTime <= startTime;
  const isSeries = shift === null && lastDate !== serviceDate;
  const count = isSeries ? seriesLength(serviceDate, lastDate, weekdaysOnly) : 1;

  function changeFirstDate(value: string) {
    // Moving the start keeps the series' length; a single day stays a single day.
    if (value && serviceDate) setLastDate(addDays(lastDate, daysBetween(serviceDate, value)));
    setServiceDate(value);
  }

  return (
    <Modal title={shift ? "Modifier le quart" : "Nouveau quart"} onClose={onClose}>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4 pb-1">
        <FormField id="shift-site" label="Lieu">
          <Select
            id="shift-site"
            containerClassName="max-w-none"
            value={siteId}
            onChange={(event) => setSiteId(Number(event.target.value))}
          >
            {pickable.map((site) => (
              <option key={site.id} value={site.id}>
                {site.name} — {CARE_SETTING_LABELS[site.care_setting]}
              </option>
            ))}
          </Select>
        </FormField>
        {shift?.series_id != null && (
          <div className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-foreground">Appliquer à</span>
            <SegmentedControl ariaLabel="Appliquer à" segments={SCOPES} value={scope} onChange={setScope} className="w-fit" />
          </div>
        )}
        {shift && scope !== "one" ? null : shift ? (
          <FormField id="shift-date" label="Date">
            <TextField
              id="shift-date"
              type="date"
              value={serviceDate}
              onChange={(event) => setServiceDate(event.target.value)}
              required
            />
          </FormField>
        ) : (
          <div className="flex flex-col gap-2">
            <div className="grid grid-cols-2 gap-4">
              <FormField id="shift-date" label="Du">
                <TextField
                  id="shift-date"
                  type="date"
                  value={serviceDate}
                  onChange={(event) => changeFirstDate(event.target.value)}
                  required
                />
              </FormField>
              <FormField id="shift-last-date" label="Au" hint={isSeries && count > 0 ? `${count} quarts, un par jour.` : undefined}>
                <TextField
                  id="shift-last-date"
                  type="date"
                  value={lastDate}
                  min={serviceDate}
                  onChange={(event) => setLastDate(event.target.value)}
                  required
                />
              </FormField>
            </div>
            {isSeries && (
              <label htmlFor="shift-weekdays-only" className="flex cursor-pointer items-center gap-2 text-sm">
                <Checkbox
                  id="shift-weekdays-only"
                  checked={weekdaysOnly}
                  onCheckedChange={(checked) => setWeekdaysOnly(checked === true)}
                />
                Jours de semaine seulement
              </label>
            )}
          </div>
        )}
        <div className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-foreground">Période</span>
          <SegmentedControl
            ariaLabel="Période"
            segments={periods.map((p) => ({ id: p.period, label: p.label }))}
            value={period}
            onChange={pickPeriod}
            className="w-fit"
          />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <FormField id="shift-start" label="Début">
            <TextField
              id="shift-start"
              type="time"
              value={startTime}
              onChange={(event) => setStartTime(event.target.value)}
              required
            />
          </FormField>
          <FormField id="shift-end" label="Fin" hint={endsNextDay ? "Le lendemain." : undefined}>
            <TextField
              id="shift-end"
              type="time"
              value={endTime}
              onChange={(event) => setEndTime(event.target.value)}
              required
            />
          </FormField>
        </div>
        {error && <Banner tone="error">{error}</Banner>}
        <div className="flex items-center justify-between gap-2">
          <div>
            {shift && (
              <Button type="button" variant="ghost" className="text-destructive" onClick={() => onDelete(shift, scope)}>
                Supprimer
              </Button>
            )}
          </div>
          <div className="flex gap-2">
            <Button type="button" variant="ghost" onClick={onClose}>
              Annuler
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Enregistrement..." : isSeries && count > 1 ? `Enregistrer ${count} quarts` : "Enregistrer"}
            </Button>
          </div>
        </div>
      </form>
    </Modal>
  );
}
