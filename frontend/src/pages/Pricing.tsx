import { Link } from "react-router-dom";
import { CheckIcon } from "lucide-react";
import { Button } from "@/components";
import { cn } from "@/lib/utils";
import { INCLUDED_IN_ALL_PLANS, PLANS, PRICING_FAQ, type Plan } from "@/site/pricing";
import { useDocumentTitle } from "@/site/useDocumentTitle";
import { FinalCta } from "./landing/FinalCta";
import { FaqList } from "./site/FaqList";
import { Section, SectionHeading } from "./site/Section";

export default function Pricing() {
  useDocumentTitle("Tarifs");
  return (
    <>
      <Section className="pb-12 min-[801px]:pb-14">
        <SectionHeading
          as="h1"
          align="center"
          eyebrow="Tarifs"
          title="Un forfait pour chaque pratique"
          lead="Commencez gratuitement, passez à un forfait payant quand NomiaMD fait partie de votre routine."
        />
        <div className="grid grid-cols-1 items-stretch gap-6 min-[901px]:grid-cols-3">
          {PLANS.map((plan) => (
            <PlanCard key={plan.id} plan={plan} />
          ))}
        </div>
      </Section>

      <Section tone="raised" className="py-12 min-[801px]:py-14">
        <h2 className="mb-6 font-heading font-[620] text-[1.3rem] text-foreground">Inclus dans tous les forfaits</h2>
        <ul className="m-0 grid list-none grid-cols-1 gap-4 p-0 min-[641px]:grid-cols-2">
          {INCLUDED_IN_ALL_PLANS.map((item) => (
            <li key={item} className="flex items-start gap-3 text-[0.95rem] text-foreground">
              <CheckIcon className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden="true" />
              {item}
            </li>
          ))}
        </ul>
      </Section>

      <Section>
        <SectionHeading title="Questions sur la tarification" />
        <FaqList items={PRICING_FAQ} />
      </Section>

      <FinalCta title="Vous hésitez entre deux forfaits ?" body="Parlons de votre pratique : nous vous aiderons à choisir." />
    </>
  );
}

function PlanCard({ plan }: { plan: Plan }) {
  return (
    <div
      className={cn(
        "relative flex flex-col rounded-2xl border bg-card p-7",
        plan.highlighted ? "border-primary shadow-floating" : "border-border",
      )}
    >
      {plan.highlighted && (
        <span className="absolute -top-3 left-7 rounded-full bg-primary px-3 py-0.5 text-[0.75rem] font-[650] text-primary-foreground">
          Pour les GMF
        </span>
      )}
      <h2 className="m-0 font-heading font-[620] text-[1.35rem] text-foreground">{plan.name}</h2>
      <p className="mt-2 mb-5 min-h-[4.5rem] text-[0.92rem] text-muted-foreground">{plan.audience}</p>
      <div className="mb-6 flex flex-wrap items-baseline gap-x-2 gap-y-1">
        {plan.price === null ? (
          <span className="font-heading text-[1.35rem] leading-[2.2rem] font-[650] text-foreground">Communiquez avec nous</span>
        ) : (
          <span className="font-heading text-[2.2rem] leading-none font-[650] text-foreground">{plan.price}</span>
        )}
        {plan.unit && <span className="text-[0.88rem] text-muted-foreground">{plan.unit}</span>}
      </div>
      <ul className="m-0 mb-8 flex flex-1 list-none flex-col gap-3 p-0">
        {plan.features.map((feature) => (
          <li key={feature} className="flex items-start gap-2.5 text-[0.93rem] text-foreground">
            <CheckIcon className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
            {feature}
          </li>
        ))}
      </ul>
      <Button asChild variant={plan.highlighted ? "primary" : "secondary"} className="h-11 w-full text-[0.95rem]">
        <Link to={plan.cta.to}>{plan.cta.label}</Link>
      </Button>
    </div>
  );
}
