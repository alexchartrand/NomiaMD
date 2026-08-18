import { SiteHeader } from "../components";

export default function Pricing() {
  return (
    <main className="landing">
      <SiteHeader />
      <div className="landing-inner">
        <section className="static-page">
          <h1>Tarification</h1>
          <p className="lede">
            NomiaMD est actuellement en version d&rsquo;aperçu. Les détails de tarification
            seront annoncés prochainement — contactez-nous en attendant.
          </p>
        </section>
      </div>
    </main>
  );
}
