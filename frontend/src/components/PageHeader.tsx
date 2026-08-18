import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Logo } from "../Logo";

type PageHeaderProps = {
  tagline?: ReactNode;
  nav?: ReactNode;
  actions?: ReactNode;
  logoSize?: number;
};

export function PageHeader({ tagline, nav, actions, logoSize = 30 }: PageHeaderProps) {
  return (
    <header className="page-header">
      <Link to="/" className="page-header-brand" aria-label="NomiaMD accueil">
        <Logo size={logoSize} />
      </Link>
      {tagline && <span className="tagline">{tagline}</span>}
      {nav && <nav className="page-header-nav">{nav}</nav>}
      {actions && <div className="page-header-actions">{actions}</div>}
    </header>
  );
}
