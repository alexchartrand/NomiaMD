import { useDocumentTitle } from "@/site/useDocumentTitle";
import { Benefits } from "./landing/Benefits";
import { Faq } from "./landing/Faq";
import { Features } from "./landing/Features";
import { FinalCta } from "./landing/FinalCta";
import { Hero } from "./landing/Hero";
import { HowItWorks } from "./landing/HowItWorks";
import { TrustTeaser } from "./landing/TrustTeaser";

export default function Landing() {
  useDocumentTitle();
  return (
    <>
      <Hero />
      <Benefits />
      <HowItWorks />
      <Features />
      <TrustTeaser />
      <Faq />
      <FinalCta />
    </>
  );
}
