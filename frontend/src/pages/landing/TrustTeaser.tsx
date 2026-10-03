import { Link } from "react-router-dom";
import { MapPinIcon, ScaleIcon, ScrollTextIcon } from "lucide-react";
import { Section, SectionHeading } from "../site/Section";

const POINTS = [
  {
    icon: MapPinIcon,
    title: "Hébergement au Canada",
    body: "Les données de vos patients sont hébergées et traitées au Canada.",
  },
  {
    icon: ScaleIcon,
    title: "Pensé pour la Loi 25",
    body: "Évaluation des facteurs relatifs à la vie privée et entente de mandataire avec chaque clinique : notre cadre de conformité est en cours de mise en place.",
  },
  {
    icon: ScrollTextIcon,
    title: "L'IA propose, les règles décident",
    body: "Les tarifs et les faits administratifs ne viennent jamais de l'IA : ils sont tirés du manuel de la RAMQ et de vos données.",
  },
];

export function TrustTeaser() {
  return (
    <Section tone="raised">
      <SectionHeading
        eyebrow="Sécurité et confidentialité"
        title="Vos données et celles de vos patients sont protégées"
      />
      <div className="grid grid-cols-1 gap-6 min-[801px]:grid-cols-3">
        {POINTS.map((point) => (
          <div key={point.title} className="flex gap-4">
            <point.icon className="mt-1 size-6 shrink-0 text-primary" aria-hidden="true" />
            <div>
              <h3 className="mb-1.5 font-heading font-[620] text-[1.05rem] text-foreground">{point.title}</h3>
              <p className="m-0 text-[0.93rem] text-muted-foreground">{point.body}</p>
            </div>
          </div>
        ))}
      </div>
      <Link to="/securite" className="mt-8 inline-block font-semibold text-primary no-underline hover:underline">
        En savoir plus sur la sécurité →
      </Link>
    </Section>
  );
}
