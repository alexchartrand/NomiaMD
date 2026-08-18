import { SiteHeader } from "../components";

export default function Contact() {
  return (
    <main className="landing">
      <SiteHeader />
      <div className="landing-inner">
        <section className="static-page">
          <h1>Contactez-nous</h1>
          <p className="lede">
            Une question sur NomiaMD ? Nos coordonnées seront affichées ici sous peu.
          </p>
        </section>
      </div>
    </main>
  );
}
