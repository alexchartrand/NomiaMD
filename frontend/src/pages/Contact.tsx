import { SiteHeader } from "../components";

export default function Contact() {
  return (
    <main>
      <SiteHeader />
      <div className="mx-auto max-w-[1080px] px-6">
        <section className="max-w-[40rem] pt-16 pb-24">
          <h1 className="mb-4 font-heading text-[2rem]">Contactez-nous</h1>
          <p className="max-w-[46rem] text-muted-foreground">
            Une question sur NomiaMD ? Nos coordonnées seront affichées ici sous peu.
          </p>
        </section>
      </div>
    </main>
  );
}
