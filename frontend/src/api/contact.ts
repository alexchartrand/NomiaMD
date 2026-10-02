import { unwrapVoid } from "./http";

// Mirrors app/postgresdb/models.py's ContactRole / ContactTopic.
export type ContactRole = "medecin" | "gestionnaire" | "partenaire" | "autre";
export type ContactTopic = "demo" | "essai" | "tarifs" | "partenariat" | "autre";

// Mirrors app/contact/models.py's ContactRequestIn.
export interface ContactRequestInput {
  name: string;
  email: string;
  phone?: string | null;
  organization?: string | null;
  role: ContactRole;
  physician_count?: number | null;
  topic: ContactTopic;
  plan?: string | null;
  message?: string | null;
  // The Law 25 consent box — the server refuses anything but `true`.
  consent: true;
  // Honeypot: always empty when a person fills in the form.
  website?: string;
}

// Public route (no login). The server answers 204 for a saved request and, on purpose, for
// one its honeypot dropped.
export async function submitContactRequest(payload: ContactRequestInput): Promise<void> {
  const response = await fetch("/api/contact", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (response.status === 429) {
    throw new Error("Trop de demandes envoyées. Réessayez plus tard, ou écrivez-nous directement par courriel.");
  }
  return unwrapVoid(response);
}
