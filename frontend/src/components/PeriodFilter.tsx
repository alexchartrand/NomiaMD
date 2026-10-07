import { PRESETS, presetOf, presetPeriod, type Period, type PresetId } from "../utils/periods";
import { FilterField } from "./FilterField";
import { SegmentedControl } from "./SegmentedControl";
import { TextField } from "./TextField";

interface PeriodFilterProps {
  period: Period;
  onChange: (period: Period) => void;
  // Keeps the date inputs' ids unique when two lists on a page each have one.
  idPrefix?: string;
}

// A list's period: the presets ("cette semaine", "tout"…), or any date range.
export function PeriodFilter({ period, onChange, idPrefix = "period" }: PeriodFilterProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <SegmentedControl<PresetId>
        ariaLabel="Période"
        segments={PRESETS}
        value={presetOf(period)}
        onChange={(id) => onChange(presetPeriod(id))}
      />
      <div className="flex flex-wrap items-center gap-2">
        <FilterField htmlFor={`${idPrefix}-from`} label="Du">
          <TextField
            id={`${idPrefix}-from`}
            type="date"
            className="w-auto"
            value={period.date_from ?? ""}
            max={period.date_to ?? undefined}
            onChange={(e) => onChange({ ...period, date_from: e.target.value || null })}
          />
        </FilterField>
        <FilterField htmlFor={`${idPrefix}-to`} label="au">
          <TextField
            id={`${idPrefix}-to`}
            type="date"
            className="w-auto"
            value={period.date_to ?? ""}
            min={period.date_from ?? undefined}
            onChange={(e) => onChange({ ...period, date_to: e.target.value || null })}
          />
        </FilterField>
      </div>
    </div>
  );
}
