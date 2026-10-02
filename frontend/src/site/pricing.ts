import { contactLink } from "./config";

export type Plan = {
  id: string;
  name: string;
  audience: string;
  // TODO(prix) : montants provisoires — à remplacer avant l'envoi. null = prix sur demande.
  price: string | null;
  unit: string;
  features: string[];
  cta: { label: string; to: string };
  highlighted?: boolean;
};

// The free plan's daily limit is advertised here only — nothing in the app enforces it yet
// (see BACKLOG.md).
export const PLANS: Plan[] = [
  {
    id: "gratuit",
    name: "Gratuit",
    audience: "Pour découvrir NomiaMD à votre rythme.",
    price: "0 $",
    unit: "pour toujours",
    features: [
      "1 extraction de codes par jour",
      "1 médecin",
      "Codes RAMQ suggérés avec tarifs",
      "Assistant RAMQ",
    ],
    cta: { label: "Essayer gratuitement", to: contactLink("essai", "gratuit") },
  },
  {
    id: "solo",
    name: "Solo",
    audience: "Pour le médecin de famille qui facture lui-même.",
    price: "200 $",
    unit: "par mois",
    features: [
      "Extractions illimitées",
      "1 médecin",
      "Boîte de réception quotidienne",
      "Factures regroupées et PDF",
      "Assistant RAMQ",
      "Soutien par courriel",
    ],
    cta: { label: "Demander une démo", to: contactLink("tarifs", "solo") },
  },
  {
    id: "clinique",
    name: "Clinique",
    audience: "Pour les GMF et cliniques de plusieurs médecins.",
    price: null,
    unit: "",
    features: [
      "Tout le forfait Solo",
      "Plusieurs médecins",
      "Mise en route accompagnée",
      "Soutien prioritaire",
    ],
    cta: { label: "Demander une démo", to: contactLink("tarifs", "clinique") },
    highlighted: true,
  },
];

export const INCLUDED_IN_ALL_PLANS = [
  "Codes du manuel des omnipraticiens de la RAMQ, tenus à jour",
  "Admissibilité vérifiée selon votre profil et le dossier du patient",
  "Hébergement des données au Canada",
  "Aucun engagement à long terme",
];

export const PRICING_FAQ = [
  {
    question: "Y a-t-il un engagement ?",
    answer: "Non. Les forfaits sont mensuels et vous pouvez les annuler en tout temps.",
  },
  {
    question: "Que se passe-t-il une fois la limite quotidienne du forfait gratuit atteinte ?",
    answer:
      "Vous pourrez extraire les codes d'une nouvelle note le lendemain. Vous pouvez passer au forfait Solo en tout temps pour des extractions illimitées.",
  },
  {
    question: "Comment suis-je facturé ?",
    answer:
      "Une facture mensuelle, par médecin actif. Pour une clinique, une seule facture regroupe tous ses médecins.",
  },
];
