import { Link } from "react-router-dom";
import { Button } from "@/components";
import { contactLink } from "@/site/config";
import { Eyebrow } from "../site/Section";
import { InboxPreview } from "./InboxPreview";

export function Hero() {
  return (
    <div className="relative overflow-hidden border-b border-border bg-[linear-gradient(180deg,var(--card),var(--background))] before:pointer-events-none before:absolute before:-top-48 before:-right-32 before:h-[30rem] before:w-[30rem] before:rounded-full before:bg-[radial-gradient(circle,var(--color-brand-accent)_0%,transparent_70%)] before:opacity-[0.16] before:content-['']">
      <section className="relative mx-auto grid max-w-[1080px] grid-cols-1 items-center gap-12 px-6 pt-12 pb-16 min-[881px]:grid-cols-[minmax(0,1fr)_minmax(0,25rem)] min-[881px]:pt-20 min-[881px]:pb-24">
        <div>
          <Eyebrow>Facturation RAMQ · Médecins de famille</Eyebrow>
          <h1 className="m-0 font-heading text-[clamp(2.3rem,5vw,3.4rem)] leading-[1.08] font-[650] tracking-[-0.025em] text-foreground">
            Simplifiez votre facturation grâce à l&rsquo;intelligence artificielle
          </h1>
          <p className="mt-5 mb-8 max-w-[34rem] text-[1.1rem] text-muted-foreground">
            NomiaMD lit vos notes de consultation, repère les codes de facturation RAMQ applicables et
            prépare vos réclamations. Votre facturation est prête à la fin de la journée, avec moins de
            codes oubliés.
          </p>
          <div className="flex flex-wrap items-center gap-5">
            <Button asChild className="h-11 px-5 text-[0.95rem]">
              <Link to={contactLink("demo")}>Demander une démo</Link>
            </Button>
            <Link
              to="/#fonctionnement"
              className="text-[0.95rem] font-semibold text-muted-foreground no-underline hover:text-primary"
            >
              Voir comment ça marche ↓
            </Link>
          </div>
        </div>
        <InboxPreview />
      </section>
    </div>
  );
}
