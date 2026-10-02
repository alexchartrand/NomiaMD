import { Link } from "react-router-dom";
import { Button } from "@/components";
import { contactLink } from "@/site/config";

type FinalCtaProps = {
  title?: string;
  body?: string;
};

// Fixed colors (not theme-flipped) so contrast against the white button stays reliable in
// both light and dark mode.
export function FinalCta({
  title = "Voyons ce que NomiaMD trouve dans vos notes",
  body = "Une démo de 30 minutes, avec vos propres cas si vous le souhaitez.",
}: FinalCtaProps) {
  return (
    <div className="bg-[#123e49] text-white">
      <div className="mx-auto flex max-w-[1080px] flex-col items-center gap-3 px-6 py-16 text-center">
        <h2 className="m-0 font-heading text-[clamp(1.5rem,3vw,1.9rem)] text-white">{title}</h2>
        <p className="mt-0 mb-4 text-[1rem] text-white/75">{body}</p>
        <Button asChild variant="secondary" className="h-11 border-transparent bg-white px-5 text-[0.95rem] text-[#123e49] hover:bg-[#eef2f2]">
          <Link to={contactLink("demo")}>Demander une démo</Link>
        </Button>
      </div>
    </div>
  );
}
