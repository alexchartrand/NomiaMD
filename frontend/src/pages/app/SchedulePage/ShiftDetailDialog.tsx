import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  CARE_SETTING_LABELS,
  describeError,
  getShiftBilling,
  listEncounters,
  SHIFT_PERIODS,
  type EncounterRow,
  type Shift,
  type ShiftBilling,
} from "../../../api";
import { Badge, Banner, Button, Modal, Spinner } from "../../../components";
import { addDays, formatLongDate } from "../../../utils/date";
import { StatusChip } from "../InboxPage/StatusChip";
import { hhmm } from "./ShiftCard";
import { ShiftCodesForm } from "./ShiftCodesForm";

const PERIOD_LABELS = Object.fromEntries(SHIFT_PERIODS.map((p) => [p.value, p.label]));

interface ShiftDetailDialogProps {
  shift: Shift;
  onClose: () => void;
  onEdit: () => void;
}

// A shift opened from the calendar: its encounters, and its own codes (09791, 19953…) to
// confirm as the shift's claim. "Modifier le quart" moves on to its hours and site.
export function ShiftDetailDialog({ shift, onClose, onEdit }: ShiftDetailDialogProps) {
  const [billing, setBilling] = useState<ShiftBilling | null>(null);
  const [encounters, setEncounters] = useState<EncounterRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getShiftBilling(shift.id)
      .then(setBilling)
      .catch((err) => setError(describeError(err)));
    // Its encounters are those the inbox places in it: the physician's pick, else the match.
    listEncounters({
      date_from: shift.service_date,
      date_to: shift.ends_next_day ? addDays(shift.service_date, 1) : shift.service_date,
    })
      .then((rows) => setEncounters(rows.filter((row) => row.setting.shift?.id === shift.id)))
      .catch((err) => setError(describeError(err)));
  }, [shift.id, shift.service_date, shift.ends_next_day]);

  return (
    <Modal
      title={shift.work_site_name}
      onClose={onClose}
      footer={
        <>
          <Button type="button" variant="secondary" onClick={onEdit}>
            Modifier le quart
          </Button>
          <Button type="button" variant="ghost" onClick={onClose}>
            Fermer
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-5">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="capitalize">{formatLongDate(shift.service_date)}</span>
          <span className="font-semibold">
            {hhmm(shift.start_time)}–{hhmm(shift.end_time)}
            {shift.ends_next_day && <span className="font-normal text-muted-foreground"> +1</span>}
          </span>
          <Badge tone="primary">
            {CARE_SETTING_LABELS[shift.care_setting]} · {PERIOD_LABELS[shift.period]}
          </Badge>
          {shift.day_type === "ferie" && <Badge tone="warning">Férié</Badge>}
        </div>

        {error && <Banner tone="error">{error}</Banner>}

        <section aria-label="Rencontres du quart" className="flex flex-col gap-2">
          <h3 className="m-0 font-heading text-base font-semibold">Rencontres</h3>
          {encounters === null ? (
            !error && <Spinner />
          ) : encounters.length === 0 ? (
            <p className="m-0 text-sm text-muted-foreground">Aucune rencontre associée à ce quart.</p>
          ) : (
            <ul className="m-0 flex list-none flex-col gap-1 p-0">
              {encounters.map((row) => (
                <li key={row.id}>
                  <Link
                    to={`/app/inbox/${row.id}`}
                    className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-sm no-underline hover:bg-accent"
                  >
                    <span className="truncate">{row.patient?.display_name ?? "Patient à associer"}</span>
                    <StatusChip status={row.status} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section aria-label="Codes du quart" className="flex flex-col gap-2">
          <h3 className="m-0 font-heading text-base font-semibold">Codes du quart</h3>
          {billing === null ? (
            !error && <Spinner />
          ) : (
            <ShiftCodesForm
              // A fresh form once saved: it starts again from the stored claim.
              key={billing.claim?.id ?? "new"}
              billing={billing}
              onSaved={(claim) => setBilling({ ...billing, claim })}
            />
          )}
        </section>
      </div>
    </Modal>
  );
}
