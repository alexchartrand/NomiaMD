import { Search, X } from "lucide-react";
import { Button, FilterField, PeriodFilter, Select, TextField } from "../../../components";
import type { Period } from "../../../utils/periods";
import { sourceLabel } from "../../../utils/sources";
import type { ClaimFilters } from "./claimFilters";

interface ClaimFiltersBarProps {
  period: Period;
  onPeriodChange: (period: Period) => void;
  filters: ClaimFilters;
  onFiltersChange: (filters: ClaimFilters) => void;
  // The sources seen in the period, for the source filter.
  sources: string[];
}

// The claims' period (presets or a date range), then who and where from — the inbox's
// filters. The status is the tabs under this bar.
export function ClaimFiltersBar({ period, onPeriodChange, filters, onFiltersChange, sources }: ClaimFiltersBarProps) {
  const hasRowFilters = Boolean(filters.source || filters.patient);

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-card px-4 py-3">
      <PeriodFilter period={period} onChange={onPeriodChange} idPrefix="claims-period" />

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border pt-3">
        <div className="relative w-64">
          <Search aria-hidden className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <TextField
            id="claims-filter-patient"
            aria-label="Patient"
            className="pl-8"
            value={filters.patient}
            placeholder="Patient : nom…"
            onChange={(e) => onFiltersChange({ ...filters, patient: e.target.value })}
          />
        </div>

        <FilterField htmlFor="claims-filter-source" label="Source">
          <Select
            id="claims-filter-source"
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
