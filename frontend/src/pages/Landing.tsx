import { Link } from "react-router-dom";
import { Button, PageHeader } from "../components";

const FEATURES = [
  {
    title: "Extraire des codes candidats",
    body: "Collez la transcription d'une consultation et obtenez des codes de facturation RAMQ suggérés, chacun appuyé par une citation exacte de la note.",
  },
  {
    title: "Posez des questions de facturation",
    body: "Un clavardage pour poser librement des questions de facturation RAMQ, sans lien avec une consultation précise.",
  },
  {
    title: "Révision médicale, toujours",
    body: "Rien n'est jamais soumis automatiquement. Chaque code suggéré est une ébauche que le médecin doit vérifier.",
  },
];

export default function Landing() {
  return (
    <main className="landing">
      <PageHeader
        actions={
          <Link to="/login">
            <Button variant="secondary">Se connecter</Button>
          </Link>
        }
      />

      <section className="landing-hero">
        <h1>Des codes de facturation ébauchés à partir de la consultation, vérifiés par vous.</h1>
        <p className="lede">
          NomiaMD lit la transcription d&rsquo;une consultation et ébauche les codes de
          facturation RAMQ qu&rsquo;elle appuie — pour les omnipraticiens seulement. Un
          médecin révise et confirme toujours avant toute soumission.
        </p>
        <Link to="/login">
          <Button>Commencer</Button>
        </Link>
      </section>

      <section className="landing-features">
        {FEATURES.map((feature) => (
          <div className="landing-feature" key={feature.title}>
            <h2>{feature.title}</h2>
            <p>{feature.body}</p>
          </div>
        ))}
      </section>
    </main>
  );
}
