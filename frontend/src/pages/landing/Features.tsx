import {
  CopyIcon,
  FileTextIcon,
  InboxIcon,
  MessageCircleQuestionIcon,
  ReceiptIcon,
  ShieldCheckIcon,
} from "lucide-react";
import { Section, SectionHeading } from "../site/Section";

const FEATURES = [
  {
    icon: InboxIcon,
    title: "Boîte de réception quotidienne",
    body: "Toutes vos rencontres de la journée au même endroit, avec leur statut et les codes proposés.",
  },
  {
    icon: ShieldCheckIcon,
    title: "Admissibilité vérifiée par des règles",
    body: "Âge, vulnérabilité, inscription et clientèle viennent de vos données, jamais devinés par l'IA.",
  },
  {
    icon: ReceiptIcon,
    title: "Tarifs calculés automatiquement",
    body: "Chaque code est accompagné de son tarif officiel, selon le lieu et le contexte de la visite.",
  },
  {
    icon: CopyIcon,
    title: "Doublons signalés",
    body: "Une même rencontre importée deux fois ? NomiaMD la signale avant qu'elle soit facturée en double.",
  },
  {
    icon: FileTextIcon,
    title: "Factures regroupées",
    body: "Regroupez les réclamations d'une période dans une facture, téléchargeable en PDF.",
  },
  {
    icon: MessageCircleQuestionIcon,
    title: "Assistant RAMQ",
    body: "Une question sur une règle de facturation ? Posez-la : l'assistant répond à partir du manuel des omnipraticiens.",
  },
];

export function Features() {
  return (
    <Section>
      <SectionHeading eyebrow="Fonctionnalités" title="Tout ce qu'il faut pour facturer sans effort" />
      <div className="grid grid-cols-1 gap-x-8 gap-y-10 min-[641px]:grid-cols-2 min-[961px]:grid-cols-3">
        {FEATURES.map((feature) => (
          <div key={feature.title}>
            <div className="mb-4 flex size-11 items-center justify-center rounded-xl bg-[color:var(--color-primary-tint)] text-primary">
              <feature.icon className="size-5" aria-hidden="true" />
            </div>
            <h3 className="mb-2 font-heading font-[620] text-[1.05rem] text-foreground">{feature.title}</h3>
            <p className="m-0 text-[0.93rem] text-muted-foreground">{feature.body}</p>
          </div>
        ))}
      </div>
    </Section>
  );
}
