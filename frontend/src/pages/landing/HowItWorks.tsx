import { ArrowDownIcon, ArrowRightIcon, CheckIcon, ClipboardPasteIcon, MousePointerClickIcon, SparklesIcon } from "lucide-react";
import { Section, SectionHeading } from "../site/Section";

// The workflow in three steps, labelled by who does them: you add the note, NomiaMD does the
// billing work (the big middle card), you confirm. Readable from the owner tags alone.
const AUTOMATED = [
  "Repère les actes facturables dans la note",
  "Choisit les codes du manuel des omnipraticiens",
  "Vérifie l'admissibilité à partir du dossier",
  "Calcule les tarifs",
];

function Owner({ children, strong = false }: { children: string; strong?: boolean }) {
  return (
    <span
      className={
        strong
          ? "mb-3 inline-block rounded-full bg-primary-foreground/15 px-2.5 py-0.5 text-[0.72rem] font-[650] tracking-[0.04em] uppercase"
          : "mb-3 inline-block rounded-full border border-border bg-card px-2.5 py-0.5 text-[0.72rem] font-[650] tracking-[0.04em] text-muted-foreground uppercase"
      }
    >
      {children}
    </span>
  );
}

function Arrow() {
  return (
    <div className="flex justify-center text-muted-foreground" aria-hidden="true">
      <ArrowRightIcon className="size-5 max-[880px]:hidden" />
      <ArrowDownIcon className="size-5 min-[881px]:hidden" />
    </div>
  );
}

export function HowItWorks() {
  return (
    <Section id="fonctionnement" tone="raised">
      <SectionHeading
        eyebrow="Fonctionnement"
        title="Vous soignez, NomiaMD facture"
        lead="Deux gestes de votre part. Tout le travail de facturation entre les deux est fait pour vous."
      />
      <div className="grid grid-cols-1 items-center gap-4 p-0 min-[881px]:grid-cols-[minmax(0,1fr)_auto_minmax(0,1.4fr)_auto_minmax(0,1fr)]">
        <div className="rounded-2xl border border-border bg-background p-6">
          <Owner>Vous</Owner>
          <ClipboardPasteIcon className="mb-3 size-6 text-primary" aria-hidden="true" />
          <h3 className="mb-1.5 font-heading text-[1.1rem] font-[620] text-foreground">Ajoutez votre note</h3>
          <p className="m-0 text-[0.93rem] text-muted-foreground">
            Collez ou téléversez la note signée. Aucun formulaire à remplir.
          </p>
        </div>
        <Arrow />
        <div className="rounded-2xl bg-primary p-6 text-primary-foreground shadow-floating">
          <Owner strong>NomiaMD · automatique</Owner>
          <SparklesIcon className="mb-3 size-6" aria-hidden="true" />
          <h3 className="mb-3 font-heading text-[1.1rem] font-[620]">Prépare la facturation</h3>
          <ul className="m-0 list-none space-y-2 p-0">
            {AUTOMATED.map((item) => (
              <li key={item} className="flex items-start gap-2 text-[0.93rem]">
                <CheckIcon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                {item}
              </li>
            ))}
          </ul>
        </div>
        <Arrow />
        <div className="rounded-2xl border border-border bg-background p-6">
          <Owner>Vous</Owner>
          <MousePointerClickIcon className="mb-3 size-6 text-primary" aria-hidden="true" />
          <h3 className="mb-1.5 font-heading text-[1.1rem] font-[620] text-foreground">Confirmez</h3>
          <p className="m-0 text-[0.93rem] text-muted-foreground">
            Un coup d&rsquo;œil aux codes proposés, un clic : la facture est prête.
          </p>
        </div>
      </div>
    </Section>
  );
}
