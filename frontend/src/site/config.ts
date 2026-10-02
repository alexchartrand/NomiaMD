import type { ContactTopic } from "@/api";

// Public-site facts shown on several pages — change them here, not in the pages.
// TODO(avant envoi) : remplacer les valeurs provisoires (courriel, responsable).
export const SITE = {
  name: "NomiaMD",
  contactEmail: "a.chartrand@nomiamd.com",
  // Law 25: the person in charge of protecting personal information must be published.
  privacyOfficer: {
    name: "Alexandre Chartrand",
    title: "Président",
  },
  region: "Québec",
  // Shown at the bottom of the privacy policy; update it with every change to that text.
  privacyPolicyUpdatedOn: "2 octobre 2026",
} as const;

// Links into the contact form with its subject (and plan) pre-selected.

export function contactLink(topic: ContactTopic, plan?: string): string {
  const params = new URLSearchParams({ sujet: topic });
  if (plan) params.set("forfait", plan);
  return `/contact?${params.toString()}`;
}
