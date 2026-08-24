import { Link } from "react-router-dom";
import { Button, Card, SiteHeader } from "../components";

const FEATURES = [
  {
    icon: IconExtract,
    title: "Extraire des codes de facturation",
    body: "Accélérez votre processus de facturation et ne manquez plus aucun code. NomiaMD utilise l'intelligence artificielle pour extraire les codes de facturation de vos consultations",
  },
  {
    icon: IconChat,
    title: "Posez des questions de facturation",
    body: "Grâce à l'IA, NomiaMD vous offre un clavardage automatisé spécialisé en facturation RAMQ.",
  },
  {
    icon: IconShield,
    title: "Facturation à la RAMQ",
    body: "Tout est automatisé pour vous simplifier la vie et mettre vos efforts là où ça compte vraiment. NomiaMD s’occupe de générer automatiquement les factures.",
  },
];

const STEPS = [
  {
    title: "Importez une note de consultation",
    body: "Une note de votre dossier médical électronique (DMÉ) ou le texte produit par un outil de scribe médical.",
  },
  {
    title: "NomiaMD suggère des codes",
    body: "Des codes de facturations RAMQ candidats sont proposés, chacun avec un tarif et une explication.",
  },
  {
    title: "Votre facturation est générée",
    body: "Les codes de facturation retenus sont utilisés pour générer automatiquement votre facturation à la RAMQ.",
  },
];

const PREVIEW_ROWS = [
  {
    code: "00103",
    description: "Examen complet",
    confidence: 92,
    quote: "présente pour un examen périodique complet, sans plainte particulière",
  },
  {
    code: "08820",
    description: "Visite de suivi",
    confidence: 78,
    quote: "revient pour ajuster le traitement de son hypertension",
  },
];

export default function Landing() {
  return (
    <main className="landing">
      <SiteHeader />

      <div className="landing-hero-band">
        <div className="landing-inner">
          <section className="landing-hero">
            <div className="landing-hero-copy">
              <span className="landing-eyebrow">Ébauche &mdash; médecins</span>
              <h1>
                Un processus de facturation simplifié grâce à l&rsquo;IA
              </h1>
              <p className="lede">
                NomiaMD vous permet d&rsquo;automatiser votre facturation grâce à l&rsquo;extraction des codes de
                facturation RAMQ provenant d&rsquo;une note de consultation. L&rsquo;IA vous fait sauver du temps et 
                de l&rsquo;argent en simplifiant et en optimisant votre facturation.
              </p>
              <div className="landing-hero-actions">
                <Link to="/login">
                  <Button>Commencer</Button>
                </Link>
                <a href="#comment-ca-marche" className="landing-hero-link">
                  Voir comment ça marche ↓
                </a>
              </div>
            </div>

            <div className="landing-hero-preview">
              <Card className="preview-card">
                <div className="preview-card-header">
                  <span>Codes suggérés</span>
                  <span className="preview-card-badge">Exemple</span>
                </div>
                {PREVIEW_ROWS.map((row) => (
                  <div className="preview-row" key={row.code}>
                    <div className="preview-row-top">
                      <span className="preview-code">{row.code}</span>
                      <span className="preview-description">{row.description}</span>
                      <span className="preview-confidence">{row.confidence}%</span>
                    </div>
                    <p className="preview-quote">&laquo; {row.quote} &raquo;</p>
                  </div>
                ))}
              </Card>
            </div>
          </section>
        </div>
      </div>

      <div className="landing-inner">
        <section className="landing-features">
          {FEATURES.map((feature) => (
            <div className="landing-feature" key={feature.title}>
              <div className="landing-feature-icon">
                <feature.icon />
              </div>
              <h2>{feature.title}</h2>
              <p>{feature.body}</p>
            </div>
          ))}
        </section>

        <section className="landing-steps" id="comment-ca-marche">
          <h2>Comment ça marche</h2>
          <div className="landing-steps-list">
            {STEPS.map((step, index) => (
              <div className="landing-step" key={step.title}>
                <span className="landing-step-number">{index + 1}</span>
                <h3>{step.title}</h3>
                <p>{step.body}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="landing-scope">
          <h2>Conçu pour les médecins du Québec</h2>
          <p>
            Le corpus de codes provient du manuel de rémunération des omnipraticiens de la
            RAMQ. La facturation des spécialistes n&rsquo;est pas couverte pour l&rsquo;instant.
          </p>
        </section>
      </div>

      <div className="landing-cta-band">
        <div className="landing-inner landing-cta-inner">
          <h2>Prêt à essayer NomiaMD ?</h2>
          <p>Version d&rsquo;aperçu — connectez-vous.</p>
          <Link to="/login">
            <Button variant="secondary">Commencer</Button>
          </Link>
        </div>
      </div>

      <footer className="landing-footer">
        <div className="landing-inner landing-footer-inner">
          <span>NomiaMD — Facturation RAMQ</span>
          <span>© {new Date().getFullYear()} NomiaMD</span>
        </div>
      </footer>
    </main>
  );
}

function IconExtract() {
  return (
    <svg viewBox="0 0 28 28" width="24" height="24" fill="none" aria-hidden="true">
      <g stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
        <path d="M7 4h10l4 4v16H7z" />
        <path d="M17 4v4h4" />
        <path d="M10.5 15.5l2.5 2.5 5-5" />
      </g>
    </svg>
  );
}

function IconChat() {
  return (
    <svg viewBox="0 0 28 28" width="24" height="24" fill="none" aria-hidden="true">
      <path
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M5 6h18v13H12l-5 4v-4H5z"
      />
    </svg>
  );
}

function IconShield() {
  return (
    <svg viewBox="0 0 28 28" width="24" height="24" fill="none" aria-hidden="true">
      <g stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 3l9 3.5v6c0 6-4 9.5-9 12.5-5-3-9-6.5-9-12.5v-6z" />
        <path d="M10.5 14l2.5 2.5 5-5" />
      </g>
    </svg>
  );
}
