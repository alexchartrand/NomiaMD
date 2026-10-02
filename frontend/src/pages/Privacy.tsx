import { Link } from "react-router-dom";
import { SITE } from "@/site/config";
import { useDocumentTitle } from "@/site/useDocumentTitle";
import { ProseSection } from "./site/ProseSection";
import { Section, SectionHeading } from "./site/Section";

// Draft (2026-10-02) — have it reviewed by privacy counsel before relying on it (see
// docs/intake-step-05-privacy-compliance-package.md), and bump SITE.privacyPolicyUpdatedOn
// with every change.
export default function Privacy() {
  useDocumentTitle("Politique de confidentialité");
  const email = (
    <a href={`mailto:${SITE.contactEmail}`} className="font-semibold text-primary no-underline hover:underline">
      {SITE.contactEmail}
    </a>
  );

  return (
    <Section>
      <SectionHeading
        as="h1"
        eyebrow="Confidentialité"
        title="Politique de confidentialité"
        lead={`Dernière mise à jour : ${SITE.privacyPolicyUpdatedOn}`}
      />

      <ProseSection title="Qui sommes-nous">
        <p className="m-0">
          {SITE.name} offre aux médecins de famille du Québec un logiciel qui suggère les codes de facturation RAMQ
          à partir de leurs notes de consultation. Cette politique explique quels renseignements personnels nous
          recueillons, pourquoi, et comment nous les protégeons, conformément à la <em>Loi sur la protection des
          renseignements personnels dans le secteur privé</em> (Loi 25).
        </p>
      </ProseSection>

      <ProseSection title="Responsable de la protection des renseignements personnels">
        <p className="m-0">
          <strong>{SITE.privacyOfficer.name}</strong>, {SITE.privacyOfficer.title.toLowerCase()}. Pour toute
          question, demande ou plainte : {email}.
        </p>
      </ProseSection>

      <ProseSection title="Renseignements que nous recueillons">
        <p className="m-0">
          <strong>Sur ce site.</strong> Quand vous remplissez le formulaire de contact : votre nom, votre courriel,
          et, si vous les fournissez, votre téléphone, votre organisation, votre rôle, le nombre de médecins et votre
          message.
        </p>
        <p className="m-0">
          <strong>Dans l&rsquo;application.</strong> Pour les médecins qui l&rsquo;utilisent : les renseignements de
          leur compte et de leur profil de pratique, les notes de consultation qu&rsquo;ils nous transmettent et les
          renseignements des patients nécessaires à la facturation (nom, numéro d&rsquo;assurance maladie, date de
          naissance). Pour ces données, {SITE.name} agit comme mandataire de la clinique ou du médecin, qui en
          demeure responsable.
        </p>
      </ProseSection>

      <ProseSection title="Pourquoi nous les utilisons">
        <ul>
          <li>Répondre à votre demande et vous présenter {SITE.name} (formulaire de contact).</li>
          <li>Suggérer les codes de facturation et préparer les réclamations (application).</li>
          <li>Assurer la sécurité du service et respecter nos obligations légales.</li>
        </ul>
        <p className="m-0">
          Nous ne vendons aucun renseignement personnel et ne les utilisons pas à des fins publicitaires.
        </p>
      </ProseSection>

      <ProseSection title="Où sont-ils conservés">
        <p className="m-0">
          Les renseignements sont hébergés et traités au Canada. Seules les personnes qui en ont besoin pour leur
          travail y ont accès.
        </p>
      </ProseSection>

      <ProseSection title="Combien de temps les gardons-nous">
        <ul>
          <li>Demandes de contact : le temps de traiter votre demande et de maintenir la relation, puis elles sont supprimées.</li>
          <li>
            Notes de consultation : le temps nécessaire à la facturation, selon la durée convenue avec la clinique,
            puis elles sont supprimées.
          </li>
          <li>Réclamations et factures : selon les durées exigées par la loi.</li>
        </ul>
      </ProseSection>

      <ProseSection title="Témoins (cookies)">
        <p className="m-0">
          Nous n&rsquo;utilisons qu&rsquo;un témoin de session, nécessaire pour vous garder connecté à
          l&rsquo;application. Aucun témoin publicitaire ni de suivi.
        </p>
      </ProseSection>

      <ProseSection title="Vos droits">
        <p className="m-0">
          Vous pouvez demander d&rsquo;accéder à vos renseignements personnels, de les faire rectifier ou de retirer
          votre consentement, en écrivant à {email}. Nous vous répondrons dans un délai de 30 jours. Si vous êtes un
          patient, adressez d&rsquo;abord votre demande à votre clinique : nous l&rsquo;aiderons à y répondre.
        </p>
        <p className="m-0">
          Vous pouvez aussi porter plainte auprès de la Commission d&rsquo;accès à l&rsquo;information du Québec.
        </p>
      </ProseSection>

      <ProseSection title="Incidents de confidentialité">
        <p className="m-0">
          En cas d&rsquo;incident présentant un risque de préjudice sérieux, nous avisons la Commission
          d&rsquo;accès à l&rsquo;information, les cliniques concernées et les personnes touchées, comme le prévoit
          la loi.
        </p>
      </ProseSection>

      <ProseSection title="Nous joindre">
        <p className="m-0">
          Pour toute question sur cette politique : {email}, ou par notre{" "}
          <Link to="/contact" className="font-semibold text-primary no-underline hover:underline">
            formulaire de contact
          </Link>
          .
        </p>
      </ProseSection>
    </Section>
  );
}
