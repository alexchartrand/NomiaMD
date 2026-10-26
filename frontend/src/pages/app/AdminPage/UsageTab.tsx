import { useEffect, useState } from "react";
import { BarChart3 } from "lucide-react";
import { cn } from "@/lib/utils";
import { describeError, getUsageReport, type UsageBucket, type UsageGrouping, type UsageReport } from "../../../api";
import {
  Banner,
  EmptyState,
  SegmentedControl,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../../components";
import { clinicToday, formatDate } from "../../../utils/date";
import { formatCount, formatLatency, formatUsd, PURPOSE_LABELS } from "./format";

type Range = "7" | "30" | "90";

const RANGES: { id: Range; label: string }[] = [
  { id: "7", label: "7 jours" },
  { id: "30", label: "30 jours" },
  { id: "90", label: "90 jours" },
];

const GROUPINGS: { id: UsageGrouping; label: string }[] = [
  { id: "model", label: "Par modèle" },
  { id: "purpose", label: "Par étape" },
  { id: "user", label: "Par médecin" },
];

const BAR = "var(--color-chart-reviewed)";

function daysBefore(isoDay: string, days: number): string {
  const date = new Date(`${isoDay}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() - days);
  return date.toISOString().slice(0, 10);
}

function Kpi({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="rounded-xl border border-border bg-card px-5 py-4">
      <p className="m-0 text-sm text-muted-foreground">{label}</p>
      <p className="m-0 mt-1 font-heading text-[1.5rem] font-bold leading-tight tabular-nums">{value}</p>
      {detail && <p className="m-0 mt-0.5 text-xs text-muted-foreground">{detail}</p>}
    </div>
  );
}

// Calls per clinic day, with the day's tokens and cost on hover. Plain flex bars, like the
// dashboard's activity chart — no chart library.
function DailyCallsChart({ days }: { days: UsageBucket[] }) {
  const max = Math.max(...days.map((day) => day.calls), 0);
  if (max === 0) return <p className="m-0 text-sm text-muted-foreground">Aucun appel sur cette période.</p>;
  return (
    <>
      <div className="relative">
        <span className="absolute -top-1 left-0 text-[0.7rem] text-muted-foreground">{max}</span>
        <div className="ml-8 flex h-36 items-end gap-[3px] border-t border-dashed border-border">
          {days.map((day, index) => (
            <div
              key={day.key}
              tabIndex={0}
              aria-label={`${formatDate(day.key)} : ${day.calls} appels`}
              className="group relative flex h-full flex-1 cursor-default flex-col justify-end outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <div
                className={cn(
                  "pointer-events-none absolute bottom-full z-10 mb-2 hidden whitespace-nowrap rounded-md border border-border bg-popover px-2.5 py-1.5 text-xs text-popover-foreground shadow-sm group-hover:block group-focus-visible:block",
                  index < days.length / 2 ? "left-0" : "right-0",
                )}
              >
                <p className="m-0 font-semibold">{formatDate(day.key)}</p>
                <p className="m-0">{formatCount(day.calls)} appels</p>
                <p className="m-0">{formatCount(day.input_tokens + day.output_tokens)} jetons</p>
                <p className="m-0">{formatUsd(day.cost_usd)}</p>
              </div>
              {day.calls > 0 && (
                <div
                  className="mx-auto w-full max-w-6 rounded-t-[3px] group-hover:opacity-85"
                  style={{ height: `${(day.calls / max) * 9}rem`, background: BAR }}
                />
              )}
            </div>
          ))}
        </div>
      </div>
      <div className="ml-8 mt-1.5 flex justify-between border-t border-border pt-1.5 text-[0.7rem] text-muted-foreground">
        <span>{formatDate(days[0].key)}</span>
        <span>{formatDate(days[days.length - 1].key)}</span>
      </div>
    </>
  );
}

function breakdownLabel(bucket: UsageBucket, grouping: UsageGrouping): string {
  return grouping === "purpose" ? (PURPOSE_LABELS[bucket.key] ?? bucket.label) : bucket.label;
}

// What the LLM calls cost: totals, a per-day series and one breakdown. Costs are estimates
// from list prices; calls on a model with no price are counted, not costed.
export function UsageTab() {
  const [range, setRange] = useState<Range>("30");
  const [grouping, setGrouping] = useState<UsageGrouping>("model");
  const [report, setReport] = useState<UsageReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    setError(null);
    const end = clinicToday();
    getUsageReport({ start: daysBefore(end, Number(range) - 1), end, group_by: grouping })
      .then((next) => current && setReport(next))
      .catch((err) => current && setError(describeError(err)));
    return () => {
      current = false;
    };
  }, [range, grouping]);

  const filters = (
    <div className="mb-5 flex flex-wrap items-center gap-3 rounded-xl border border-border bg-card px-4 py-3">
      <SegmentedControl ariaLabel="Période" segments={RANGES} value={range} onChange={setRange} />
      <SegmentedControl ariaLabel="Regrouper" segments={GROUPINGS} value={grouping} onChange={setGrouping} />
    </div>
  );

  if (error) {
    return (
      <>
        {filters}
        <Banner tone="error">{error}</Banner>
      </>
    );
  }
  if (!report) {
    return (
      <>
        {filters}
        <div aria-busy="true" aria-label="Chargement de l'utilisation" className="grid gap-4 sm:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      </>
    );
  }

  const { totals } = report;
  return (
    <>
      {filters}
      <div className="mb-5 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi
          label="Coût estimé"
          value={formatUsd(totals.cost_usd)}
          detail={totals.unpriced_calls > 0 ? `${totals.unpriced_calls} appel(s) sans prix connu` : "USD, prix catalogue"}
        />
        <Kpi
          label="Extractions"
          value={formatCount(report.extractions)}
          detail={`${formatUsd(report.cost_per_extraction_usd)} par extraction`}
        />
        <Kpi
          label="Jetons"
          value={formatCount(totals.input_tokens + totals.output_tokens)}
          detail={`${formatCount(totals.input_tokens)} entrée · ${formatCount(totals.output_tokens)} sortie`}
        />
        <Kpi
          label="Latence médiane"
          value={formatLatency(totals.median_latency_ms)}
          detail={`p95 ${formatLatency(totals.p95_latency_ms)} · ${totals.errors} erreur(s)`}
        />
      </div>

      <div className="mb-5 rounded-xl border border-border bg-card px-5 py-4">
        <h2 className="m-0 mb-4 text-base font-semibold">Appels par jour</h2>
        <DailyCallsChart days={report.by_day} />
      </div>

      {report.breakdown.length === 0 ? (
        <EmptyState icon={BarChart3} title="Aucun appel sur cette période." />
      ) : (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          <Table>
            <TableHeader className="bg-muted/40">
              <TableRow className="hover:bg-transparent">
                <TableHead className="pl-4">{GROUPINGS.find((g) => g.id === grouping)?.label.replace("Par ", "")}</TableHead>
                <TableHead className="text-right">Appels</TableHead>
                <TableHead className="text-right">Jetons entrée</TableHead>
                <TableHead className="text-right">Jetons sortie</TableHead>
                <TableHead className="text-right">Latence médiane</TableHead>
                <TableHead className="text-right">Erreurs</TableHead>
                <TableHead className="pr-4 text-right">Coût estimé</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {report.breakdown.map((bucket) => (
                <TableRow key={bucket.key}>
                  <TableCell className="pl-4 font-medium">{breakdownLabel(bucket, grouping)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatCount(bucket.calls)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatCount(bucket.input_tokens)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatCount(bucket.output_tokens)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatLatency(bucket.median_latency_ms)}</TableCell>
                  <TableCell className="text-right tabular-nums">{bucket.errors}</TableCell>
                  <TableCell className="pr-4 text-right font-semibold tabular-nums">
                    {bucket.unpriced_calls === bucket.calls ? "—" : formatUsd(bucket.cost_usd)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </>
  );
}
