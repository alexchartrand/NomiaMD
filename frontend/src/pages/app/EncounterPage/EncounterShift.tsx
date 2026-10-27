import { useState } from "react";
import { CalendarClock, MapPin } from "lucide-react";
import { CARE_SETTING_LABELS, describeError, setEncounterShift, type EncounterDetail } from "../../../api";
import { Badge, Select, Spinner } from "../../../components";
import { shiftLabel } from "../../../utils/shifts";

// The "let the server derive it" choice in the picker.
const AUTOMATIC = "auto";

interface EncounterShiftProps {
  encounter: EncounterDetail;
  disabled: boolean;
  onChanged: (detail: EncounterDetail) => void;
}

// The shift the encounter took place during — the physician's pick, or the one its time
// falls in — and where that puts it, with a way to pick another. The codes already
// extracted stay until the physician re-extracts (the page says when they should).
export function EncounterShift({ encounter, disabled, onChanged }: EncounterShiftProps) {
  const { setting } = encounter;
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function pick(value: string) {
    setSaving(true);
    setError(null);
    try {
      onChanged(await setEncounterShift(encounter.id, value === AUTOMATIC ? null : Number(value)));
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSaving(false);
    }
  }

  const place = setting.care_setting ? CARE_SETTING_LABELS[setting.care_setting] : "Lieu non précisé";
  const pickable = setting.shift_options.length > 0;

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-border bg-card px-4 py-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <span className="flex min-w-0 items-center gap-2 text-sm">
          {setting.shift ? (
            <CalendarClock aria-hidden className="size-4 shrink-0 text-muted-foreground" />
          ) : (
            <MapPin aria-hidden className="size-4 shrink-0 text-muted-foreground" />
          )}
          <span className="truncate">
            {setting.shift ? <>Quart : {shiftLabel(setting.shift)}</> : place}
          </span>
        </span>
        {setting.needs_shift_choice && <Badge tone="warning">Quart à confirmer</Badge>}
        {setting.shift && !setting.shift_picked && <Badge tone="neutral">Déduit de l&apos;heure</Badge>}
        {pickable && (
          <div className="ml-auto flex items-center gap-2">
            {saving && <Spinner label="Enregistrement…" />}
            <Select
              aria-label="Quart de la rencontre"
              value={setting.shift_picked && setting.shift ? setting.shift.id : AUTOMATIC}
              onChange={(e) => void pick(e.target.value)}
              disabled={disabled || saving}
              containerClassName="max-w-sm"
            >
              <option value={AUTOMATIC}>
                {setting.needs_shift_choice ? "Choisir le quart…" : "Quart déduit automatiquement"}
              </option>
              {setting.shift_options.map((shift) => (
                <option key={shift.id} value={shift.id}>
                  {shiftLabel(shift)}
                </option>
              ))}
            </Select>
          </div>
        )}
      </div>
      {error && <p className="m-0 text-sm text-destructive">{error}</p>}
    </div>
  );
}
