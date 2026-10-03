import { Link } from "react-router-dom";
import { contactLink } from "@/site/config";
import { FaqList, type FaqItem } from "../site/FaqList";
import { Section, SectionHeading } from "../site/Section";

const inlineLink = "font-semibold text-primary no-underline hover:underline";

const QUESTIONS: FaqItem[] = [
  {
    question: "À qui s'adresse NomiaMD ?",
    answer:
      "Aux médecins omnipraticiens du Québec, en cabinet, en GMF ou à l'urgence. Les codes de facturation proviennent du manuel des omnipraticiens de la RAMQ ; la facturation des médecins spécialistes n'est pas couverte pour l'instant.",
  },
  {
    question: "Comment mes notes arrivent-elles dans NomiaMD ?",
    answer:
      "Aujourd'hui, vous copiez-collez ou téléversez vos notes de consultation signées, une à une ou pour toute une journée. Des intégrations directes avec les DMÉ et les scribes IA utilisés au Québec sont en développement.",
  },
  {
    question: "Dois-je changer ma façon de rédiger mes notes ?",
    answer:
      "Non. NomiaMD lit vos notes telles que vous les rédigez déjà. Les informations administratives (âge, inscription, vulnérabilité) viennent de votre profil et du dossier du patient, pas du texte de la note.",
  },
  {
    question: "Et si l'IA se trompe ?",
    answer:
      "L'IA ne peut proposer que des codes de facturation du manuel dont les conditions d'admissibilité sont respectées, et les tarifs ne viennent jamais d'elle. Vous gardez toujours le dernier mot : rien n'est facturé sans votre confirmation.",
  },
  {
    question: "NomiaMD transmet-il ma facturation à la RAMQ ?",
    answer:
      "NomiaMD prépare vos réclamations et les regroupe dans une facture. La transmission directe à la RAMQ est en développement.",
  },
  {
    question: "Où sont hébergées mes données ?",
    answer: (
      <>
        Au Canada. Consultez notre page{" "}
        <Link to="/securite" className={inlineLink}>
          Sécurité
        </Link>{" "}
        pour le détail.
      </>
    ),
  },
  {
    question: "Combien ça coûte ?",
    answer: (
      <>
        Un forfait gratuit permet d'essayer NomiaMD sans frais, et des forfaits Solo et Clinique sont offerts.
        Voyez la{" "}
        <Link to="/prix" className={inlineLink}>
          tarification
        </Link>
        .
      </>
    ),
  },
  {
    question: "Comment commencer ?",
    answer: (
      <>
        <Link to={contactLink("demo")} className={inlineLink}>
          Demandez une démo
        </Link>{" "}
        : nous vous montrons NomiaMD en 30 minutes et ouvrons votre compte.
      </>
    ),
  },
];

export function Faq() {
  return (
    <Section id="faq">
      <SectionHeading eyebrow="Questions fréquentes" title="Vos questions, nos réponses" />
      <FaqList items={QUESTIONS} />
    </Section>
  );
}
