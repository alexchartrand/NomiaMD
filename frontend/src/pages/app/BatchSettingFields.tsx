import { useEffect, useState } from "react";
import { CARE_SETTING_LABELS, listShifts, type CareSetting, type Shift } from "../../api";
import { FormField, Select } from "../../components";
import { addDays, clinicToday } from "../../utils/date";
import { clinicNow, likelyShift, shiftLabel } from "../../utils/shifts";

// Every setting a paste can be, including those no work site is (cabinet, domicile).
const CARE_SETTINGS = Object.entries(CARE_SETTING_LABELS) as [CareSetting, string][];

export interface BatchSetting {
  shiftId: number | null;
  careSetting: CareSetting | null;
}

// The shifts a paste may come from: today's and the two days before (a night's notes are
// often pasted the next morning), the latest first. None when they can't be read.
export function useRecentShifts(): Shift[] | null {
  const [shifts, setShifts] = useState<Shift[] | null>(null);
  useEffect(() => {
    const today = clinicToday();
    listShifts(addDays(today, -2), today)
      .then((found) => setShifts([...found].reverse()))
      .catch(() => setShifts([]));
  }, []);
  return shifts;
}

// The shift the pasted notes come from, picked for the physician when one is under way or
// just ended. With no shift, where they took place instead — the server prefers the shift.
export function BatchSettingFields({
  shifts,
  value,
  onChange,
}: {
  shifts: Shift[];
  value: BatchSetting;
  onChange: (value: BatchSetting) => void;
}) {
  return (
    <div className="flex flex-wrap gap-4">
      {shifts.length > 0 && (
        <FormField
          id="batch-shift"
          label="Quart"
          hint="Le lieu et l'heure de ce quart guident le choix des codes."
          className="min-w-64 flex-1"
        >
          <Select
            id="batch-shift"
            containerClassName="max-w-none"
            value={value.shiftId ?? ""}
            onChange={(e) => onChange({ ...value, shiftId: e.target.value ? Number(e.target.value) : null })}
          >
            <option value="">Aucun quart</option>
            {shifts.map((shift) => (
              <option key={shift.id} value={shift.id}>
                {shiftLabel(shift)}
              </option>
            ))}
          </Select>
        </FormField>
      )}
      {value.shiftId === null && (
        <FormField id="batch-care-setting" label="Lieu (facultatif)" className="min-w-48">
          <Select
            id="batch-care-setting"
            value={value.careSetting ?? ""}
            onChange={(e) => onChange({ ...value, careSetting: (e.target.value || null) as CareSetting | null })}
          >
            <option value="">Non précisé</option>
            {CARE_SETTINGS.map(([setting, label]) => (
              <option key={setting} value={setting}>
                {label}
              </option>
            ))}
          </Select>
        </FormField>
      )}
    </div>
  );
}

// What the form starts with once the shifts are in.
export function initialBatchSetting(shifts: Shift[]): BatchSetting {
  return { shiftId: likelyShift(shifts, clinicNow())?.id ?? null, careSetting: null };
}
