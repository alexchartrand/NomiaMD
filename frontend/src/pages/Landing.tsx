import { useDocumentTitle } from "@/site/useDocumentTitle";
import { Benefits } from "./landing/Benefits";
import { Faq } from "./landing/Faq";
import { Features } from "./landing/Features";
import { FinalCta } from "./landing/FinalCta";
import { Hero } from "./landing/Hero";
import { HowItWorks } from "./landing/HowItWorks";
import { LedgerBackdrop } from "./landing/LedgerBackdrop";
import { TrustTeaser } from "./landing/TrustTeaser";

export default function Landing() {
  useDocumentTitle();
  return (
    <>
      <LedgerBackdrop>
        <Hero />
        <Benefits />
      </LedgerBackdrop>
      <HowItWorks />
      <Features />
      <TrustTeaser />
      <Faq />
      <FinalCta />
    </>
  );
}
