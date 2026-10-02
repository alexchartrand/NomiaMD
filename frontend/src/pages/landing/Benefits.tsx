import { BookOpenIcon, CircleDollarSignIcon, MoonIcon } from "lucide-react";
import { Section, SectionHeading } from "../site/Section";

const BENEFITS = [
  {
    icon: CircleDollarSignIcon,
    problem: "Des codes oubliés",
    title: "Facturez tout ce que vous faites",
    body: "Suppléments, majorations, visites de prise en charge : NomiaMD repère dans votre note les actes facturables que l'on oublie facilement en fin de journée.",
  },
  {
    icon: BookOpenIcon,
    problem: "Un manuel complexe",
    title: "Les règles appliquées pour vous",
    body: "Âge du patient, vulnérabilité, inscription, taille de votre clientèle : les conditions du manuel des omnipraticiens sont vérifiées automatiquement.",
  },
  {
    icon: MoonIcon,
    problem: "La facturation le soir",
    title: "Quelques minutes par jour",
    body: "Vos rencontres de la journée sont prêtes à facturer dans une seule boîte de réception. Fini les soirées passées à chercher le bon code.",
  },
];

export function Benefits() {
  return (
    <Section>
      <SectionHeading
        eyebrow="Pourquoi NomiaMD"
        title="Moins de temps sur la facturation, plus de temps pour vos patients"
      />
      <div className="grid grid-cols-1 gap-6 min-[801px]:grid-cols-3">
        {BENEFITS.map((benefit) => (
          <div key={benefit.title} className="rounded-2xl border border-border bg-card p-6">
            <div className="mb-4 flex size-11 items-center justify-center rounded-xl bg-[color:var(--color-primary-tint)] text-primary">
              <benefit.icon className="size-5" aria-hidden="true" />
            </div>
            <p className="mb-1 text-[0.78rem] font-[650] tracking-[0.03em] text-[color:var(--color-warning-text)] uppercase">
              {benefit.problem}
            </p>
            <h3 className="mb-2 font-heading font-[620] text-[1.15rem] text-foreground">{benefit.title}</h3>
            <p className="m-0 text-[0.95rem] text-muted-foreground">{benefit.body}</p>
          </div>
        ))}
      </div>
    </Section>
  );
}
