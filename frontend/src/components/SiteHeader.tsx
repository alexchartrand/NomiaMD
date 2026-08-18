import { Link } from "react-router-dom";
import { Button } from "./Button";
import { PageHeader } from "./PageHeader";

export function SiteHeader() {
  return (
    <div className="site-header">
      <div className="landing-inner">
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
