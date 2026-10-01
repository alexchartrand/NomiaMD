import { cn } from "@/lib/utils";
import { ENCOUNTER_STATUSES, type EncounterPeriod } from "../../../api";
import { Button, Select, TextField } from "../../../components";
import type { RowFilters, StatusFilter } from "./filters";
import { PRESETS, presetOf, type PresetId } from "./periods";

interface FiltersBarProps {
  period: EncounterPeriod;
  onPeriodChange: (period: EncounterPeriod) => void;
  onPresetChange: (id: PresetId) => void;
  filters: RowFilters;
  onFiltersChange: (filters: RowFilters) => void;
  // The sources seen in the period, for the source filter.
  sources: string[];
}

const presetClasses =
  "cursor-pointer rounded-full border border-border bg-card px-3 py-1 text-sm text-foreground hover:border-primary";

export function FiltersBar({ period, onPeriodChange, onPresetChange, filters, onFiltersChange, sources }: FiltersBarProps) {
  const activePreset = presetOf(period);
  const hasRowFilters = Boolean(filters.status || filters.source || filters.patient);

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-card px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        {PRESETS.map((preset) => (
          <button
            key={preset.id}
            type="button"
            aria-pressed={activePreset === preset.id}
            className={cn(presetClasses, activePreset === preset.id && "border-primary bg-[color:var(--color-primary-tint)] text-primary")}
            onClick={() => onPresetChange(preset.id)}
          >
            {preset.label}
          </button>
        ))}
        <div className="flex flex-wrap items-center gap-2 sm:ml-auto">
          <label htmlFor="period-from" className="text-sm text-muted-foreground">
            Du
          </label>
          <TextField
            id="period-from"
            type="date"
            className="w-auto"
            value={period.date_from ?? ""}
            max={period.date_to ?? undefined}
            onChange={(e) => onPeriodChange({ ...period, date_from: e.target.value || null })}
          />
          <label htmlFor="period-to" className="text-sm text-muted-foreground">
            au
          </label>
          <TextField
            id="period-to"
            type="date"
            className="w-auto"
            value={period.date_to ?? ""}
            min={period.date_from ?? undefined}
            onChange={(e) => onPeriodChange({ ...period, date_to: e.target.value || null })}
          />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <label htmlFor="filter-status" className="text-sm text-muted-foreground">
          Statut
        </label>
        <Select
          id="filter-status"
          value={filters.status}
          onChange={(e) => onFiltersChange({ ...filters, status: e.target.value as StatusFilter })}
        >
          <option value="">Tous</option>
          <option value="à traiter">À traiter (non facturées)</option>
          {ENCOUNTER_STATUSES.map((status) => (
            <option key={status} value={status}>
              {status.charAt(0).toUpperCase() + status.slice(1)}
            </option>
          ))}
        </Select>

        <label htmlFor="filter-source" className="text-sm text-muted-foreground">
          Source
        </label>
        <Select
          id="filter-source"
          value={filters.source}
          onChange={(e) => onFiltersChange({ ...filters, source: e.target.value })}
        >
          <option value="">Toutes</option>
          {sources.map((source) => (
            <option key={source} value={source}>
              {source}
            </option>
          ))}
        </Select>

        <label htmlFor="filter-patient" className="text-sm text-muted-foreground">
          Patient
        </label>
        <TextField
          id="filter-patient"
          className="w-48"
          value={filters.patient}
          placeholder="Nom ou NAM..."
          onChange={(e) => onFiltersChange({ ...filters, patient: e.target.value })}
        />

        {hasRowFilters && (
          <Button type="button" variant="link" onClick={() => onFiltersChange({ status: "", source: "", patient: "" })}>
            Effacer les filtres
          </Button>
        )}
      </div>
    </div>
  );
}
