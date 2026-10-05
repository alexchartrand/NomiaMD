import { cn } from "@/lib/utils";
import type { WeekActivity } from "../../../api";
import { formatShortDay, plural } from "./format";
import { Panel } from "./Panel";

const REVIEWED = "var(--color-chart-reviewed)";
const PENDING = "var(--color-chart-pending)";

function Swatch({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span aria-hidden className="size-2.5 rounded-[3px]" style={{ background: color }} />
      {label}
    </span>
  );
}

function summary(week: WeekActivity): string {
  return `Semaine du ${formatShortDay(week.week_start)} : ${plural(week.received, "rencontre", "rencontres")}, ${plural(
    week.reviewed,
    "revue",
    "revues",
  )}`;
}

// Centered over its bar, except at the chart's edges, where it opens inward so it never
// runs past the card.
function tooltipPosition(index: number, count: number): string {
  if (index === 0) return "left-0";
  if (index === count - 1) return "right-0";
  return "left-1/2 -translate-x-1/2";
}

// Encounters per week, stacked: reviewed (a claim saved) at the base, the rest on top, so
// the bar's height is everything received. Plain flex bars — no chart library.
export function WeeklyActivityChart({ weeks }: { weeks: WeekActivity[] }) {
  const max = Math.max(...weeks.map((week) => week.received), 0);
  return (
    <Panel
      title="Activité des 8 dernières semaines"
      action={
        <div className="flex gap-4 text-xs text-muted-foreground">
          <Swatch color={REVIEWED} label="Revues" />
          <Swatch color={PENDING} label="En attente" />
        </div>
      }
    >
      {max === 0 ? (
        <p className="text-sm text-muted-foreground">Aucune rencontre ces 8 dernières semaines.</p>
      ) : (
        <>
          <div className="relative">
            <span className="absolute -top-1 left-0 text-[0.7rem] text-muted-foreground">{max}</span>
            <div className="ml-6 flex h-36 items-end gap-2 border-t border-dashed border-border pt-0">
              {weeks.map((week, index) => {
                const pending = week.received - week.reviewed;
                return (
                  <div
                    key={week.week_start}
                    tabIndex={0}
                    aria-label={summary(week)}
                    className="group relative flex h-full flex-1 cursor-default flex-col justify-end rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <div
                      className={cn(
                        "pointer-events-none absolute bottom-full z-10 mb-2 hidden whitespace-nowrap rounded-md border border-border bg-popover px-2.5 py-1.5 text-xs text-popover-foreground shadow-sm group-hover:block group-focus-visible:block",
                        tooltipPosition(index, weeks.length),
                      )}
                    >
                      <p className="font-semibold">Semaine du {formatShortDay(week.week_start)}</p>
                      <p>{plural(week.received, "rencontre", "rencontres")}</p>
                      <p className="flex items-center gap-1.5">
                        <span aria-hidden className="size-2 rounded-[2px]" style={{ background: REVIEWED }} />
                        {week.reviewed} revue{week.reviewed > 1 ? "s" : ""}
                      </p>
                      <p className="flex items-center gap-1.5">
                        <span aria-hidden className="size-2 rounded-[2px]" style={{ background: PENDING }} />
                        {pending} en attente
                      </p>
                    </div>
                    <div className="mx-auto flex w-full max-w-9 flex-col gap-[2px] group-hover:opacity-85">
                      {pending > 0 && (
                        <div
                          className="rounded-t-[4px]"
                          style={{ height: `${(pending / max) * 8.75}rem`, background: PENDING }}
                        />
                      )}
                      {week.reviewed > 0 && (
                        <div
                          className={pending > 0 ? "" : "rounded-t-[4px]"}
                          style={{ height: `${(week.reviewed / max) * 8.75}rem`, background: REVIEWED }}
                        />
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
          <div className="ml-6 mt-1.5 flex gap-2 border-t border-border pt-1.5">
            {weeks.map((week) => (
              <span key={week.week_start} className="flex-1 text-center text-[0.7rem] text-muted-foreground">
                {formatShortDay(week.week_start)}
              </span>
            ))}
          </div>
          <table className="sr-only">
            <caption>Rencontres par semaine</caption>
            <thead>
              <tr>
                <th scope="col">Semaine du</th>
                <th scope="col">Rencontres</th>
                <th scope="col">Revues</th>
              </tr>
            </thead>
            <tbody>
              {weeks.map((week) => (
                <tr key={week.week_start}>
                  <td>{formatShortDay(week.week_start)}</td>
                  <td>{week.received}</td>
                  <td>{week.reviewed}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </Panel>
  );
}
