import type { ReactNode } from "react";
import { Search, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { EncounterPeriod } from "../../../api";
import { Button, Select, TextField } from "../../../components";
import { sourceLabel } from "../../../utils/sources";
import type { RowFilters } from "./filters";
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

// Keeps a label glued to its field so a wrapping row never splits them apart.
function FilterField({ htmlFor, label, children }: { htmlFor: string; label: string; children: ReactNode }) {
  return (
    <div className="flex shrink-0 items-center gap-2">
      <label htmlFor={htmlFor} className="text-sm text-muted-foreground">
        {label}
      </label>
      {children}
    </div>
  );
}

// The period (presets or a date range), then who and where from. The status is the tabs
// under this bar.
export function FiltersBar({ period, onPeriodChange, onPresetChange, filters, onFiltersChange, sources }: FiltersBarProps) {
  const activePreset = presetOf(period);
  const hasRowFilters = Boolean(filters.source || filters.patient);

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-card px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label="Période" className="inline-flex flex-wrap rounded-lg bg-muted p-0.5">
          {PRESETS.map((preset) => {
            const active = activePreset === preset.id;
            return (
              <button
                key={preset.id}
                type="button"
                aria-pressed={active}
                className={cn(
                  "cursor-pointer rounded-md border-none bg-transparent px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground",
                  active && "bg-card text-primary shadow-sm hover:text-primary",
                )}
                onClick={() => onPresetChange(preset.id)}
              >
                {preset.label}
              </button>
            );
          })}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <FilterField htmlFor="period-from" label="Du">
            <TextField
              id="period-from"
              type="date"
              className="w-auto"
              value={period.date_from ?? ""}
              max={period.date_to ?? undefined}
              onChange={(e) => onPeriodChange({ ...period, date_from: e.target.value || null })}
            />
          </FilterField>
          <FilterField htmlFor="period-to" label="au">
            <TextField
              id="period-to"
              type="date"
              className="w-auto"
              value={period.date_to ?? ""}
              min={period.date_from ?? undefined}
              onChange={(e) => onPeriodChange({ ...period, date_to: e.target.value || null })}
            />
          </FilterField>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border pt-3">
        <div className="relative w-64">
          <Search aria-hidden className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <TextField
            id="filter-patient"
            aria-label="Patient"
            className="pl-8"
            value={filters.patient}
            placeholder="Patient : nom ou NAM…"
            onChange={(e) => onFiltersChange({ ...filters, patient: e.target.value })}
          />
        </div>

        <FilterField htmlFor="filter-source" label="Source">
          <Select
            id="filter-source"
            containerClassName="w-48"
            value={filters.source}
            onChange={(e) => onFiltersChange({ ...filters, source: e.target.value })}
          >
            <option value="">Toutes</option>
            {sources.map((source) => (
              <option key={source} value={source}>
                {sourceLabel(source)}
              </option>
            ))}
          </Select>
        </FilterField>

        {hasRowFilters && (
          <Button
            type="button"
            variant="ghost"
            className="text-muted-foreground"
            onClick={() => onFiltersChange({ ...filters, source: "", patient: "" })}
          >
            <X aria-hidden />
            Effacer les filtres
          </Button>
        )}
      </div>
    </div>
  );
}
