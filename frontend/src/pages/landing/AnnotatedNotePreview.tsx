// The hero's example: a consultation note with the phrases NomiaMD billed from highlighted and
// numbered, and the codes found underneath carrying the same numbers. Fictional patient; the
// codes and fees are real (omnipraticien manual, revision 2026-09-17, en cabinet). Check them
// again whenever the manual changes.

/** A run of the note's text; `code` marks the phrase that code was found from. */
interface NoteSegment {
  text: string;
  code?: string;
}

const PATIENT = { initials: "J. P.", time: "10 h 30" };

const NOTE: NoteSegment[] = [
  { text: "Patiente de 31 ans, " },
  { text: "suivi de grossesse à 24 semaines", code: "15812" },
  { text: ". Consultation menée " },
  { text: "avec une interprète (espagnol)", code: "15188" },
  { text: ". TA 112/70, hauteur utérine 24 cm, BCF 145/min. Dépistage du diabète gestationnel prévu à 26 semaines." },
];

const CODES = [
  { code: "15812", label: "Visite de suivi de grossesse", fee: 57.0 },
  { code: "15188", label: "Supplément pour interprète", fee: 27.25, oftenForgotten: true },
];

const money = new Intl.NumberFormat("fr-CA", { style: "currency", currency: "CAD" });

function markerOf(code: string) {
  return CODES.findIndex((c) => c.code === code) + 1;
}

function Marker({ n }: { n: number }) {
  return (
    <span className="inline-flex size-[1.15rem] shrink-0 items-center justify-center rounded-full bg-primary align-[0.1em] font-heading text-[0.65rem] font-[650] text-primary-foreground">
      {n}
    </span>
  );
}

export function AnnotatedNotePreview() {
  const total = CODES.reduce((sum, code) => sum + code.fee, 0);

  return (
    <div
      className="w-full rounded-2xl border border-border bg-card shadow-floating"
      role="img"
      aria-label={`Exemple : une note de suivi de grossesse avec interprète, ${CODES.length} codes de facturation trouvés, total ${money.format(total)}`}
    >
      <div className="flex items-center justify-between gap-3 px-5 pt-4 pb-3">
        <div>
          <div className="text-[0.72rem] font-[650] tracking-[0.04em] text-muted-foreground uppercase">Note de consultation</div>
          <div className="font-heading text-[0.95rem] font-[650] text-foreground">
            {PATIENT.initials} <span className="font-normal text-muted-foreground">· {PATIENT.time}</span>
          </div>
        </div>
        <span className="shrink-0 whitespace-nowrap rounded-full border border-border bg-background px-2.5 py-0.5 text-[0.7rem] font-[650] text-muted-foreground">
          Exemple fictif
        </span>
      </div>

      <p className="mx-5 mb-4 rounded-lg bg-background p-3.5 font-serif text-[0.88rem] leading-[1.7] text-foreground">
        {NOTE.map((segment, i) =>
          segment.code ? (
            <mark
              key={i}
              className="rounded-sm bg-[color:var(--color-primary-tint)] px-0.5 text-foreground underline decoration-primary decoration-2 underline-offset-[3px]"
            >
              {segment.text} <Marker n={markerOf(segment.code)} />
            </mark>
          ) : (
            <span key={i}>{segment.text}</span>
          ),
        )}
      </p>

      <div className="border-t border-border px-5 pt-3 pb-4">
        <div className="mb-2 text-[0.72rem] font-[650] tracking-[0.04em] text-muted-foreground uppercase">Codes trouvés</div>
        <ul className="m-0 list-none space-y-2 p-0">
          {CODES.map((code, i) => (
            <li key={code.code} className="flex items-center gap-2.5">
              <Marker n={i + 1} />
              <span className="font-mono text-[0.8rem] font-[650] text-primary">{code.code}</span>
              <span className="min-w-0 flex-1 text-[0.85rem] leading-snug text-foreground">
                {code.label}
                {code.oftenForgotten && (
                  <span className="ml-1.5 inline-block whitespace-nowrap rounded-full bg-[color:var(--color-warning-bg)] px-1.5 py-0.5 text-[0.65rem] font-[650] text-[color:var(--color-warning-text)]">
                    souvent oublié
                  </span>
                )}
              </span>
              <span className="text-[0.85rem] tabular-nums text-foreground">{money.format(code.fee)}</span>
            </li>
          ))}
        </ul>
        <div className="mt-3 flex items-center justify-between border-t border-border pt-3">
          <span className="text-[0.82rem] text-muted-foreground">À confirmer d&rsquo;un clic</span>
          <span className="font-heading text-[1.15rem] font-[650] text-foreground">{money.format(total)}</span>
        </div>
      </div>
    </div>
  );
}
