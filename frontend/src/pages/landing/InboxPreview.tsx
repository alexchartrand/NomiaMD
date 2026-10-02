import { CheckIcon } from "lucide-react";

// Fictional patients; the codes and fees are real (omnipraticien manual, revision
// 2026-09-17, cabinet fee for a panel of 500+ patients). Check them again whenever the
// manual changes.
const ENCOUNTERS = [
  { time: "08 h 30", patient: "L. M.", label: "Visite de suivi", codes: [{ code: "15824", fee: 59.8 }] },
  { time: "09 h 10", patient: "C. B.", label: "Prise en charge", codes: [{ code: "15802", fee: 99.4 }] },
  { time: "09 h 50", patient: "É. R.", label: "Visite périodique", codes: [{ code: "15814", fee: 75.85 }] },
  {
    time: "10 h 30",
    patient: "J. P.",
    label: "Suivi de grossesse",
    codes: [
      { code: "15812", fee: 57.0 },
      { code: "15188", fee: 27.25 },
    ],
  },
];

const money = new Intl.NumberFormat("fr-CA", { style: "currency", currency: "CAD" });

export function InboxPreview() {
  const total = ENCOUNTERS.flatMap((encounter) => encounter.codes).reduce((sum, code) => sum + code.fee, 0);

  return (
    <div
      className="w-full rounded-2xl border border-border bg-card p-5 shadow-[0_24px_50px_-24px_rgba(18,35,44,0.35)]"
      role="img"
      aria-label={`Exemple de boîte de réception : ${ENCOUNTERS.length} rencontres prêtes, total ${money.format(total)}`}
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <div className="font-heading text-[0.95rem] font-[650] text-foreground">Rencontres du jour</div>
          <div className="text-[0.78rem] text-muted-foreground">{ENCOUNTERS.length} rencontres · toutes prêtes</div>
        </div>
        <span className="shrink-0 whitespace-nowrap rounded-full border border-border bg-background px-2.5 py-0.5 text-[0.7rem] font-[650] text-muted-foreground">
          Exemple fictif
        </span>
      </div>

      <ul className="m-0 list-none p-0">
        {ENCOUNTERS.map((encounter) => (
          <li key={encounter.time} className="flex items-start gap-3 border-t border-border py-3">
            <span className="w-14 shrink-0 whitespace-nowrap pt-0.5 font-mono text-[0.75rem] text-muted-foreground">{encounter.time}</span>
            <div className="min-w-0 flex-1">
              <div className="text-[0.88rem] font-semibold text-foreground">
                {encounter.patient} <span className="font-normal text-muted-foreground">· {encounter.label}</span>
              </div>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {encounter.codes.map((code) => (
                  <span
                    key={code.code}
                    className="inline-flex items-baseline gap-1.5 rounded-md bg-[color:var(--color-primary-tint)] px-1.5 py-0.5 text-[0.75rem]"
                  >
                    <span className="font-mono font-[650] text-primary">{code.code}</span>
                    <span className="text-foreground">{money.format(code.fee)}</span>
                  </span>
                ))}
              </div>
            </div>
            <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-[color:var(--color-success-bg)] px-2 py-0.5 text-[0.72rem] font-[650] text-[color:var(--color-success-text)]">
              <CheckIcon className="size-3" aria-hidden="true" />
              Prêt
            </span>
          </li>
        ))}
      </ul>

      <div className="mt-1 flex items-center justify-between border-t border-border pt-3">
        <span className="text-[0.85rem] text-muted-foreground">Total de la matinée</span>
        <span className="font-heading text-[1.15rem] font-[650] text-foreground">{money.format(total)}</span>
      </div>
    </div>
  );
}
