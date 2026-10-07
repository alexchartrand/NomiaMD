import type { EncounterRow } from "../../../api";
import { Table, TableBody, TableHead, TableHeader, TableRow, TableCell } from "../../../components";
import { formatLongDate } from "../../../utils/date";
import { formatMoney } from "../../../utils/money";
import { ENCOUNTER_COLUMNS, EncounterRowItem } from "./EncounterRowItem";
import type { DayGroup } from "./inboxView";

function plural(count: number, singular: string, pluralForm: string): string {
  return `${count} ${count > 1 ? pluralForm : singular}`;
}

interface DayCardProps {
  // The day's rows on this page of the inbox…
  group: DayGroup;
  // …and all of them, for its count and total, when the day runs over more than one page.
  whole?: DayGroup;
  onChanged: () => void;
  onOpenDuplicate: (row: EncounterRow) => void;
}

// One day of encounters: its date, count and indicative total, then its rows — a shift
// pasted at once (batch label) under its own sub-heading.
export function DayCard({ group, whole = group, onChanged, onOpenDuplicate }: DayCardProps) {
  const rows = whole.batches.flatMap((batch) => batch.rows);
  const total = rows.reduce((sum, row) => sum + (row.indicative_total ?? 0), 0);
  return (
    <section aria-label={formatLongDate(group.day)} className="overflow-hidden rounded-xl border border-border bg-card">
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-border bg-muted/40 px-4 py-2.5">
        <h2 className="m-0 font-heading text-base font-semibold first-letter:uppercase">
          {formatLongDate(group.day)}
          <span className="ml-2 text-sm font-normal text-muted-foreground">
            {plural(rows.length, "rencontre", "rencontres")}
          </span>
        </h2>
        {total > 0 && (
          <span className="text-sm text-muted-foreground">
            Total indicatif <span className="font-semibold text-foreground tabular-nums">{formatMoney(total)}</span>
          </span>
        )}
      </div>
      <Table className="table-fixed">
        <colgroup>
          {ENCOUNTER_COLUMNS.map((column, i) => (
            <col key={i} className={column.width} />
          ))}
        </colgroup>
        <TableHeader className="sr-only">
          <TableRow>
            {ENCOUNTER_COLUMNS.map((column, i) => (
              <TableHead key={i}>{column.label}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        {group.batches.map((batch) => (
          <TableBody key={batch.label ?? ""}>
            {batch.label !== null && (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={ENCOUNTER_COLUMNS.length} className="px-4 pt-3 pb-1">
                  <h3 className="m-0 text-xs font-semibold tracking-wide text-muted-foreground uppercase">{batch.label}</h3>
                </TableCell>
              </TableRow>
            )}
            {batch.rows.map((row) => (
              <EncounterRowItem key={row.id} row={row} onChanged={onChanged} onOpenDuplicate={onOpenDuplicate} />
            ))}
          </TableBody>
        ))}
      </Table>
    </section>
  );
}
