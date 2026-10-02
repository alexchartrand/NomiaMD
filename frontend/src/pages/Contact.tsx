import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CircleCheckIcon, MailIcon } from "lucide-react";
import {
  describeError,
  submitContactRequest,
  type ContactRequestInput,
  type ContactRole,
  type ContactTopic,
} from "@/api";
import { Banner, Button, Checkbox, Select, TextArea, TextField } from "@/components";
import { SITE } from "@/site/config";
import { useDocumentTitle } from "@/site/useDocumentTitle";
import { Section, SectionHeading } from "./site/Section";

const TOPICS: { value: ContactTopic; label: string }[] = [
  { value: "demo", label: "Demander une démo" },
  { value: "essai", label: "Essayer gratuitement" },
  { value: "tarifs", label: "Tarification" },
  { value: "partenariat", label: "Partenariat ou intégration" },
  { value: "autre", label: "Autre question" },
];

const ROLES: { value: ContactRole; label: string }[] = [
  { value: "medecin", label: "Médecin" },
  { value: "gestionnaire", label: "Gestionnaire de clinique" },
  { value: "partenaire", label: "Partenaire ou fournisseur" },
  { value: "autre", label: "Autre" },
];

const NEXT_STEPS = [
  "Nous vous répondons pour convenir d'un moment.",
  "Une démo de 30 minutes, adaptée à votre pratique.",
  "Nous ouvrons votre compte et vous essayez NomiaMD sur vos propres notes.",
];

const fieldClass = "h-10 w-full";

type FormState = {
  name: string;
  email: string;
  phone: string;
  organization: string;
  role: ContactRole | "";
  physicianCount: string;
  topic: ContactTopic;
  message: string;
  consent: boolean;
  website: string;
};

function topicFrom(value: string | null): ContactTopic {
  return TOPICS.some((topic) => topic.value === value) ? (value as ContactTopic) : "demo";
}

function planFrom(value: string | null): string | null {
  return value && /^[a-z-]{1,32}$/.test(value) ? value : null;
}

export default function Contact() {
  useDocumentTitle("Contact");
  const [searchParams] = useSearchParams();
  const plan = planFrom(searchParams.get("forfait"));

  const [form, setForm] = useState<FormState>(() => ({
    name: "",
    email: "",
    phone: "",
    organization: "",
    role: "",
    physicianCount: "",
    topic: topicFrom(searchParams.get("sujet")),
    message: "",
    consent: false,
    website: "",
  }));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (form.role === "" || !form.consent) return;
    setError(null);
    setSubmitting(true);
    const payload: ContactRequestInput = {
      name: form.name,
      email: form.email,
      phone: form.phone || null,
      organization: form.organization || null,
      role: form.role,
      physician_count: form.physicianCount ? Number(form.physicianCount) : null,
      topic: form.topic,
      plan,
      message: form.message || null,
      consent: true,
      website: form.website,
    };
    try {
      await submitContactRequest(payload);
      setSent(true);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Section>
      <div className="grid grid-cols-1 gap-12 min-[901px]:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <div>
          <SectionHeading
            as="h1"
            eyebrow="Contact"
            title="Parlons de votre facturation"
            lead="Une démo, une question sur la tarification ou un projet de partenariat ? Écrivez-nous : nous vous répondrons rapidement."
          />
          <a
            href={`mailto:${SITE.contactEmail}`}
            className="mb-10 inline-flex items-center gap-2 font-semibold text-primary no-underline hover:underline"
          >
            <MailIcon className="size-5" aria-hidden="true" />
            {SITE.contactEmail}
          </a>
          <h2 className="mb-4 font-heading font-[620] text-[1.1rem] text-foreground">Ce qui se passe ensuite</h2>
          <ol className="m-0 flex list-none flex-col gap-4 p-0">
            {NEXT_STEPS.map((step, index) => (
              <li key={step} className="flex items-start gap-3 text-[0.95rem] text-muted-foreground">
                <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-[color:var(--color-primary-tint)] font-heading text-[0.85rem] font-[650] text-primary">
                  {index + 1}
                </span>
                <span className="pt-0.5">{step}</span>
              </li>
            ))}
          </ol>
        </div>

        <div className="rounded-2xl border border-border bg-card p-6 shadow-[0_24px_50px_-28px_rgba(18,35,44,0.3)] min-[641px]:p-8">
          {sent ? (
            <div className="flex flex-col items-start gap-3 py-8" role="status">
              <CircleCheckIcon className="size-10 text-[color:var(--color-success-text)]" aria-hidden="true" />
              <h2 className="m-0 font-heading font-[620] text-[1.4rem] text-foreground">Merci, votre demande est envoyée</h2>
              <p className="m-0 text-muted-foreground">
                Nous vous répondrons à <strong className="text-foreground">{form.email}</strong> dans les plus brefs délais.
              </p>
              <Link to="/" className="mt-2 font-semibold text-primary no-underline hover:underline">
                ← Retour à l&rsquo;accueil
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="flex flex-col gap-5">
              {error && <Banner tone="error">{error}</Banner>}

              <div className="grid grid-cols-1 gap-5 min-[641px]:grid-cols-2">
                <Field label="Nom" htmlFor="contact-name" required>
                  <TextField
                    id="contact-name"
                    autoComplete="name"
                    required
                    maxLength={120}
                    className={fieldClass}
                    value={form.name}
                    onChange={(event) => update("name", event.target.value)}
                  />
                </Field>
                <Field label="Courriel" htmlFor="contact-email" required>
                  <TextField
                    id="contact-email"
                    type="email"
                    autoComplete="email"
                    required
                    maxLength={255}
                    placeholder="vous@clinique.ca"
                    className={fieldClass}
                    value={form.email}
                    onChange={(event) => update("email", event.target.value)}
                  />
                </Field>
                <Field label="Téléphone" htmlFor="contact-phone">
                  <TextField
                    id="contact-phone"
                    type="tel"
                    autoComplete="tel"
                    maxLength={40}
                    className={fieldClass}
                    value={form.phone}
                    onChange={(event) => update("phone", event.target.value)}
                  />
                </Field>
                <Field label="Clinique ou organisation" htmlFor="contact-organization">
                  <TextField
                    id="contact-organization"
                    autoComplete="organization"
                    maxLength={160}
                    className={fieldClass}
                    value={form.organization}
                    onChange={(event) => update("organization", event.target.value)}
                  />
                </Field>
                <Field label="Vous êtes" htmlFor="contact-role" required>
                  <Select
                    id="contact-role"
                    required
                    containerClassName="max-w-none"
                    className={fieldClass}
                    value={form.role}
                    onChange={(event) => update("role", event.target.value as ContactRole)}
                  >
                    <option value="" disabled>
                      Choisir…
                    </option>
                    {ROLES.map((role) => (
                      <option key={role.value} value={role.value}>
                        {role.label}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Nombre de médecins" htmlFor="contact-physicians">
                  <TextField
                    id="contact-physicians"
                    type="number"
                    inputMode="numeric"
                    min={1}
                    max={10000}
                    className={fieldClass}
                    value={form.physicianCount}
                    onChange={(event) => update("physicianCount", event.target.value)}
                  />
                </Field>
              </div>

              <Field label="Sujet" htmlFor="contact-topic">
                <Select
                  id="contact-topic"
                  containerClassName="max-w-none"
                  className={fieldClass}
                  value={form.topic}
                  onChange={(event) => update("topic", event.target.value as ContactTopic)}
                >
                  {TOPICS.map((topic) => (
                    <option key={topic.value} value={topic.value}>
                      {topic.label}
                    </option>
                  ))}
                </Select>
              </Field>

              <Field label="Message" htmlFor="contact-message">
                <TextArea
                  id="contact-message"
                  rows={5}
                  maxLength={4000}
                  className="font-sans"
                  placeholder="Parlez-nous de votre pratique ou de votre question."
                  value={form.message}
                  onChange={(event) => update("message", event.target.value)}
                />
              </Field>

              {/* Honeypot: off-screen and skipped by keyboard and screen readers, so only bots fill it. */}
              <div aria-hidden="true" className="absolute -left-[9999px] h-px w-px overflow-hidden">
                <label htmlFor="contact-website">Site web</label>
                <input
                  id="contact-website"
                  tabIndex={-1}
                  autoComplete="off"
                  value={form.website}
                  onChange={(event) => update("website", event.target.value)}
                />
              </div>

              <label htmlFor="contact-consent" className="flex cursor-pointer items-start gap-3 text-[0.88rem] text-muted-foreground">
                <Checkbox
                  id="contact-consent"
                  className="mt-0.5"
                  checked={form.consent}
                  onCheckedChange={(checked) => update("consent", checked === true)}
                />
                <span>
                  J&rsquo;accepte que {SITE.name} utilise ces renseignements pour répondre à ma demande, conformément à
                  la{" "}
                  <Link to="/confidentialite" className="font-semibold text-primary no-underline hover:underline">
                    politique de confidentialité
                  </Link>
                  . <span className="text-destructive">*</span>
                </span>
              </label>

              <Button type="submit" disabled={submitting || !form.consent} className="h-11 text-[0.95rem]">
                {submitting ? "Envoi…" : "Envoyer la demande"}
              </Button>
              <p className="m-0 text-[0.8rem] text-muted-foreground">
                <span className="text-destructive">*</span> Champ obligatoire
              </p>
            </form>
          )}
        </div>
      </div>
    </Section>
  );
}

function Field({
  label,
  htmlFor,
  required,
  children,
}: {
  label: string;
  htmlFor: string;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-sm font-semibold text-foreground">
        {label}
        {required && <span className="text-destructive"> *</span>}
      </label>
      {children}
    </div>
  );
}
