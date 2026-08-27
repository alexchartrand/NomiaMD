import { Link } from "react-router-dom";
import { Button } from "./Button";
import { PageHeader } from "./PageHeader";

export function SiteHeader() {
  return (
    <div className="sticky top-0 z-50 border-b border-border bg-[color-mix(in_srgb,var(--background)_97%,transparent)] backdrop-blur-[14px]">
      <div className="mx-auto max-w-[1080px] px-6 py-4">
        <PageHeader
          logoSize={40}
          nav={
            <>
              <Link to="/prix">Prix</Link>
              <Link to="/contact">Contactez-nous</Link>
            </>
          }
          actions={
            <Link to="/login">
              <Button variant="secondary">Se connecter</Button>
            </Link>
          }
        />
      </div>
    </div>
  );
}
