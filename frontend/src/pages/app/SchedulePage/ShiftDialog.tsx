import { useState, type FormEvent } from "react";
import {
  CARE_SETTING_LABELS,
  createShift,
  describeError,
  updateShift,
  type PeriodDefault,
  type Shift,
  type ShiftPeriod,
  type WorkSite,
} from "../../../api";
import { Banner, Button, FormField, Modal, SegmentedControl, Select, TextField } from "../../../components";

interface ShiftDialogProps {
  // null: a new shift on `day`.
  shift: Shift | null;
  day: string;
  sites: WorkSite[];
  periods: PeriodDefault[];
  onClose: () => void;
  onSaved: (shift: Shift) => void;
  onDelete: (shift: Shift) => void;
}

const hhmm = (time: string) => time.slice(0, 5);

// Add or edit one shift: the site, the day, the period — which fills in its usual hours —
// and the hours actually worked.
export function ShiftDialog({ shift, day, sites, periods, onClose, onSaved, onDelete }: ShiftDialogProps) {
  const initialPeriod = shift?.period ?? "jour";
  const defaults = (period: ShiftPeriod) => periods.find((p) => p.period === period);

  // A shift on an archived site keeps it pickable while it's being edited.
  const pickable = sites.filter((site) => site.is_active || site.id === shift?.work_site_id);
  const [siteId, setSiteId] = useState<number | "">(shift?.work_site_id ?? pickable[0]?.id ?? "");
  const [serviceDate, setServiceDate] = useState(shift?.service_date ?? day);
  const [period, setPeriod] = useState<ShiftPeriod>(initialPeriod);
  const [startTime, setStartTime] = useState(hhmm(shift?.start_time ?? defaults(initialPeriod)?.start_time ?? "08:00"));
  const [endTime, setEndTime] = useState(hhmm(shift?.end_time ?? defaults(initialPeriod)?.end_time ?? "16:00"));
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
    setError(null);
    setSubmitting(true);
    const payload = { work_site_id: siteId, period, service_date: serviceDate, start_time: startTime, end_time: endTime };
    try {
      onSaved(shift ? await updateShift(shift.id, payload) : await createShift(payload));
    } catch (err) {
      setError(describeError(err));
      setSubmitting(false);
    }
  }

  const endsNextDay = endTime <= startTime;

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
        <FormField id="shift-date" label="Date">
          <TextField
            id="shift-date"
            type="date"
            value={serviceDate}
            onChange={(event) => setServiceDate(event.target.value)}
            required
          />
        </FormField>
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
              <Button type="button" variant="ghost" className="text-destructive" onClick={() => onDelete(shift)}>
                Supprimer
              </Button>
            )}
          </div>
          <div className="flex gap-2">
            <Button type="button" variant="ghost" onClick={onClose}>
              Annuler
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Enregistrement..." : "Enregistrer"}
            </Button>
          </div>
        </div>
      </form>
    </Modal>
  );
}
