import { Section, SectionHeading } from "../site/Section";

const STEPS = [
  {
    title: "Vos notes arrivent",
    body: "Copiez-collez ou téléversez vos notes de consultation signées. Les intégrations directes avec les DMÉ et les scribes IA utilisés au Québec sont en développement.",
  },
  {
    title: "NomiaMD trouve les codes de facturation",
    body: "L'IA repère les actes facturables dans la note et les associe aux codes de facturation du manuel des omnipraticiens de la RAMQ.",
  },
  {
    title: "Les règles sont vérifiées",
    body: "L'admissibilité de chaque code de facturation est vérifiée à partir de votre profil de pratique et du dossier du patient, et le tarif est calculé.",
  },
  {
    title: "Votre facture est prête",
    body: "Un coup d'œil pour confirmer, et les réclamations de la journée sont regroupées dans une facture.",
  },
];

export function HowItWorks() {
  return (
    <Section id="fonctionnement" tone="raised">
      <SectionHeading
        eyebrow="Fonctionnement"
        title="De la note de consultation à la facture, en quatre étapes"
      />
      <ol className="m-0 grid list-none grid-cols-1 gap-8 p-0 min-[641px]:grid-cols-2 min-[961px]:grid-cols-4">
        {STEPS.map((step, index) => (
          <li key={step.title} className="relative">
            <span className="mb-4 flex size-9 items-center justify-center rounded-full bg-primary font-heading text-[0.95rem] font-[650] text-primary-foreground">
              {index + 1}
            </span>
            <h3 className="mb-2 font-heading font-[620] text-[1.05rem] text-foreground">{step.title}</h3>
            <p className="m-0 text-[0.93rem] text-muted-foreground">{step.body}</p>
          </li>
        ))}
      </ol>
    </Section>
  );
}
