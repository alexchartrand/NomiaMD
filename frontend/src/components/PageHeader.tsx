import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";
import { Logo } from "../Logo";

type PageHeaderProps = {
  tagline?: ReactNode;
  nav?: ReactNode;
  actions?: ReactNode;
  logoSize?: number;
};

export function PageHeader({ tagline, nav, actions, logoSize = 30 }: PageHeaderProps) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-4">
      <Link to="/" className="inline-flex leading-none no-underline" aria-label="NomiaMD accueil">
        <Logo size={logoSize} />
      </Link>
      {tagline && <span className="text-sm text-muted-foreground">{tagline}</span>}
      {nav && (
        <nav
          className={cn(
            "flex flex-1 justify-center gap-8 max-[700px]:hidden",
            "[&_a]:text-sm [&_a]:font-semibold [&_a]:text-muted-foreground [&_a]:no-underline [&_a:hover]:text-primary",
          )}
        >
          {nav}
        </nav>
      )}
      {actions && <div className="ml-auto">{actions}</div>}
    </header>
  );
}
