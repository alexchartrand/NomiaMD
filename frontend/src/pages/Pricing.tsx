import { SiteHeader } from "../components";

export default function Pricing() {
  return (
    <main>
      <SiteHeader />
      <div className="mx-auto max-w-[1080px] px-6">
        <section className="max-w-[40rem] pt-16 pb-24">
          <h1 className="mb-4 font-heading text-[2rem]">Tarification</h1>
          <p className="max-w-[46rem] text-muted-foreground">
            NomiaMD est actuellement en version d&rsquo;aperçu. Les détails de tarification
            seront annoncés prochainement — contactez-nous en attendant.
          </p>
        </section>
      </div>
    </main>
  );
}
