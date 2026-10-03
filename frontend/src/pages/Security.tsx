import { Fragment } from "react";
import { ArrowDownIcon, ArrowRightIcon } from "lucide-react";
import { SITE } from "@/site/config";
import { useDocumentTitle } from "@/site/useDocumentTitle";
import { ProseSection } from "./site/ProseSection";
import { Section, SectionHeading } from "./site/Section";

const FLOW = [
  { title: "Votre note signée", body: "Copiée ou téléversée par vous" },
  { title: "NomiaMD, au Canada", body: "L'IA repère les actes, les règles vérifient l'admissibilité" },
  { title: "Votre confirmation", body: "Vous gardez le dernier mot" },
  { title: "Votre facture", body: "Réclamations regroupées, en PDF" },
];

export default function Security() {
  useDocumentTitle("Sécurité et confidentialité");
  return (
    <>
      <Section className="pb-10">
        <SectionHeading
          as="h1"
          eyebrow="Sécurité et confidentialité"
          title="La confiance avant tout"
          lead="Vos notes contiennent des renseignements de santé. Voici comment NomiaMD les traite et les protège."
        />
        <div className="flex flex-col items-stretch gap-2 min-[901px]:flex-row">
          {FLOW.map((step, index) => (
            <Fragment key={step.title}>
              {index > 0 && (
                <div className="flex items-center justify-center text-muted-foreground" aria-hidden="true">
                  <ArrowDownIcon className="size-5 min-[901px]:hidden" />
                  <ArrowRightIcon className="size-5 max-[900px]:hidden" />
                </div>
              )}
              <div
                className={
                  index === 1
                    ? "flex-1 rounded-xl border border-primary bg-[color:var(--color-primary-tint)] p-4"
                    : "flex-1 rounded-xl border border-border bg-card p-4"
                }
              >
                <div className="font-heading text-[0.98rem] font-[650] text-foreground">{step.title}</div>
                <div className="mt-1 text-[0.85rem] text-muted-foreground">{step.body}</div>
              </div>
            </Fragment>
          ))}
        </div>
      </Section>

      <Section tone="raised">
        <ProseSection title="Hébergement au Canada">
          <p className="m-0">
            Les données de vos patients sont hébergées et traitées au Canada, y compris par les modèles
            d&rsquo;intelligence artificielle qui analysent vos notes. Les connexions à NomiaMD sont chiffrées
            (HTTPS).
          </p>
        </ProseSection>
        <ProseSection title="L'IA propose, les règles décident">
          <ul>
            <li>
              L&rsquo;IA ne peut proposer que des codes du manuel des omnipraticiens de la RAMQ ; tout autre code
              est écarté.
            </li>
            <li>
              Les faits administratifs (âge, inscription, vulnérabilité, taille de clientèle) viennent de votre
              profil et du dossier du patient, jamais du texte de la note.
            </li>
            <li>Les conditions d&rsquo;admissibilité sont vérifiées par des règles, et les tarifs viennent du manuel officiel.</li>
            <li>Rien n&rsquo;est facturé sans votre confirmation.</li>
          </ul>
        </ProseSection>
        <ProseSection title="Accès et traçabilité">
          <ul>
            <li>Chaque médecin a son propre compte ; un accès peut être révoqué immédiatement.</li>
            <li>Les sessions sont protégées et expirent automatiquement.</li>
            <li>
              Chaque réclamation conserve le contexte qui l&rsquo;a justifiée (codes, tarifs, contexte de
              facturation) au moment où elle a été enregistrée.
            </li>
            <li>Rien n&rsquo;est effacé en silence : une réclamation ou une facture annulée reste au dossier.</li>
          </ul>
        </ProseSection>
        <ProseSection title="Conservation des notes">
          <p className="m-0">
            Le texte des notes est conservé le temps nécessaire à la facturation, pour une durée limitée, puis
            supprimé ; les réclamations, elles, sont conservées. Cette durée est en cours de définition avec nos
            conseillers et sera précisée dans notre politique de confidentialité.
          </p>
        </ProseSection>
        <ProseSection title="Loi 25">
          <p className="m-0">
            NomiaMD agit comme mandataire des cliniques qui l&rsquo;utilisent. Notre cadre de conformité à la Loi 25
            est en cours de mise en place :
          </p>
          <ul>
            <li>
              un responsable de la protection des renseignements personnels désigné ({SITE.privacyOfficer.name}) ;
            </li>
            <li>une évaluation des facteurs relatifs à la vie privée (ÉFVP) pour chaque clinique et partenaire ;</li>
            <li>une entente de mandataire avec chaque clinique ;</li>
            <li>un registre des incidents de confidentialité et une procédure d&rsquo;intervention.</li>
          </ul>
        </ProseSection>
      </Section>

      <Section>
        <div className="max-w-[760px] rounded-2xl border border-border bg-card p-6 min-[641px]:p-8">
          <h2 className="mb-2 font-heading font-[620] text-[1.3rem] text-foreground">Vous avez un questionnaire de sécurité ?</h2>
          <p className="mt-0 mb-4 text-muted-foreground">
            Clinique, établissement ou partenaire : écrivez-nous, nous y répondrons et vous transmettrons notre
            documentation.
          </p>
          <a href={`mailto:${SITE.contactEmail}`} className="font-semibold text-primary no-underline hover:underline">
            {SITE.contactEmail}
          </a>
        </div>
      </Section>
    </>
  );
}
