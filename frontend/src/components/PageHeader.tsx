import type { ReactNode } from "react";
import { Logo } from "../Logo";

type PageHeaderProps = {
  tagline?: ReactNode;
  actions?: ReactNode;
  logoSize?: number;
};

export function PageHeader({ tagline, actions, logoSize = 30 }: PageHeaderProps) {
  return (
    <header className="page-header">
      <Logo size={logoSize} />
      {tagline && <span className="tagline">{tagline}</span>}
      {actions && <div className="page-header-actions">{actions}</div>}
    </header>
  );
}
