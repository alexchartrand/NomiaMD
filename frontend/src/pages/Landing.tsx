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
    <main>
      <SiteHeader />

      <div className="relative overflow-hidden border-b border-border bg-[linear-gradient(180deg,var(--card),var(--background))] pb-16 before:pointer-events-none before:absolute before:-top-48 before:-right-32 before:h-[26rem] before:w-[26rem] before:rounded-full before:bg-[radial-gradient(circle,var(--color-brand-accent)_0%,transparent_70%)] before:opacity-[0.16] before:content-['']">
        <div className="mx-auto max-w-[1080px] px-6">
          <section className="relative grid grid-cols-1 items-center gap-12 pt-8 pb-4 min-[801px]:grid-cols-[minmax(0,1fr)_minmax(0,22rem)] min-[801px]:pt-12">
            <div>
              <span className="mb-4 inline-block rounded-full bg-[color:var(--color-primary-tint)] px-[0.7rem] py-[0.3rem] text-[0.78rem] font-[650] tracking-[0.03em] text-primary uppercase">
                Ébauche &mdash; médecins
              </span>
              <h1 className="mb-4 font-heading text-[2.5rem] leading-[1.15]">
                Un processus de facturation simplifié grâce à l&rsquo;IA
              </h1>
              <p className="mb-7 max-w-[46rem] text-muted-foreground">
                NomiaMD vous permet d&rsquo;automatiser votre facturation grâce à l&rsquo;extraction des codes de
                facturation RAMQ provenant d&rsquo;une note de consultation. L&rsquo;IA vous fait sauver du temps et
                de l&rsquo;argent en simplifiant et en optimisant votre facturation.
              </p>
              <div className="flex flex-wrap items-center gap-5">
                <Link to="/login">
                  <Button>Commencer</Button>
                </Link>
                <a
                  href="#comment-ca-marche"
                  className="text-[0.9rem] font-semibold text-muted-foreground no-underline hover:text-primary"
                >
                  Voir comment ça marche ↓
                </a>
              </div>
            </div>

            <div className="order-first flex justify-center min-[801px]:order-none">
              <Card className="w-full gap-0 p-5 shadow-[0_20px_45px_-20px_rgba(18,35,44,0.25)]">
                <div className="mb-3 flex items-center justify-between font-heading text-[0.95rem] font-[650]">
                  <span>Codes suggérés</span>
                  <span className="rounded-full border border-border bg-background px-[0.55rem] py-[0.15rem] text-[0.72rem] font-[650] text-muted-foreground">
                    Exemple
                  </span>
                </div>
                {PREVIEW_ROWS.map((row) => (
                  <div className="border-t border-border py-3" key={row.code}>
                    <div className="flex flex-wrap items-baseline gap-[0.6rem]">
                      <span className="font-mono text-[0.9rem] font-[650] text-primary">{row.code}</span>
                      <span className="text-[0.9rem] font-semibold">{row.description}</span>
                      <span className="ml-auto rounded-full bg-[color:var(--color-primary-tint)] px-2 py-[0.1rem] text-[0.78rem] font-[650] text-primary">
                        {row.confidence}%
                      </span>
                    </div>
                    <p className="mt-[0.35rem] text-[0.85rem] text-muted-foreground italic">
                      &laquo; {row.quote} &raquo;
                    </p>
                  </div>
                ))}
              </Card>
            </div>
          </section>
        </div>
      </div>

      <div className="mx-auto max-w-[1080px] px-6">
        <section className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-6 border-b border-border pt-16 pb-12">
          {FEATURES.map((feature) => (
            <div key={feature.title}>
              <div className="mb-[0.9rem] flex size-11 items-center justify-center rounded-xl bg-[color:var(--color-primary-tint)] text-primary">
                <feature.icon />
              </div>
              <h2 className="mb-[0.4rem] font-heading text-[1.05rem]">{feature.title}</h2>
              <p className="text-[0.92rem] text-muted-foreground">{feature.body}</p>
            </div>
          ))}
        </section>

        <section className="border-b border-border pt-16 pb-12" id="comment-ca-marche">
          <h2 className="mb-8 font-heading text-2xl">Comment ça marche</h2>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-8">
            {STEPS.map((step, index) => (
              <div key={step.title}>
                <span className="mb-[0.9rem] flex size-7 items-center justify-center rounded-full bg-primary font-heading text-[0.85rem] font-[650] text-primary-foreground">
                  {index + 1}
                </span>
                <h3 className="mb-[0.4rem] font-heading text-base">{step.title}</h3>
                <p className="text-[0.9rem] text-muted-foreground">{step.body}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="pt-12 pb-16">
          <h2 className="mb-[0.6rem] font-heading text-[1.3rem]">Conçu pour les médecins du Québec</h2>
          <p className="max-w-[42rem] text-muted-foreground">
            Le corpus de codes provient du manuel de rémunération des omnipraticiens de la
            RAMQ. La facturation des spécialistes n&rsquo;est pas couverte pour l&rsquo;instant.
          </p>
        </section>
      </div>

      {/* Fixed (not theme-flipped) so contrast against the white CTA button stays reliable
          in both light and dark mode. */}
      <div className="bg-[#123e49] text-white">
        <div className="mx-auto flex max-w-[1080px] flex-col items-center gap-[0.6rem] px-6 py-14 text-center">
          <h2 className="m-0 font-heading text-[1.6rem]">Prêt à essayer NomiaMD ?</h2>
          <p className="mb-3 text-[0.9rem] text-white/75">Version d&rsquo;aperçu — connectez-vous.</p>
          <Link to="/login">
            <Button variant="secondary" className="border-transparent bg-white text-[#123e49] hover:bg-[#eef2f2]">
              Commencer
            </Button>
          </Link>
        </div>
      </div>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-[1080px] flex-wrap items-center justify-between gap-4 px-6 py-6 text-[0.85rem] text-muted-foreground">
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
