import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { MenuIcon, XIcon } from "lucide-react";
import { Button } from "./Button";
import { PageHeader } from "./PageHeader";

const NAV_LINKS = [
  { to: "/", label: "Accueil" },
  { to: "/prix", label: "Tarifs" },
  { to: "/securite", label: "Sécurité" },
  { to: "/#faq", label: "FAQ" },
  { to: "/contact", label: "Contact" },
];

export function SiteHeader() {
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => setMenuOpen(false), [location.pathname, location.hash]);

  return (
    <div className="sticky top-0 z-50 border-b border-border bg-[color-mix(in_srgb,var(--background)_97%,transparent)] backdrop-blur-[14px]">
      <div className="mx-auto max-w-[1080px] px-6 py-4">
        <PageHeader
          logoSize={36}
          nav={NAV_LINKS.map((link) => (
            <Link key={link.to} to={link.to}>
              {link.label}
            </Link>
          ))}
          actions={
            <div className="flex items-center gap-2">
              <Button asChild className="h-10 px-4 text-base max-[700px]:hidden">
                <Link to="/login">Connexion</Link>
              </Button>
              <Button
                variant="ghost"
                className="min-[701px]:hidden"
                aria-label={menuOpen ? "Fermer le menu" : "Ouvrir le menu"}
                aria-expanded={menuOpen}
                aria-controls="site-mobile-menu"
                onClick={() => setMenuOpen((open) => !open)}
              >
                {menuOpen ? <XIcon className="size-5" /> : <MenuIcon className="size-5" />}
              </Button>
            </div>
          }
        />
        {menuOpen && (
          <nav id="site-mobile-menu" className="mt-4 flex flex-col gap-1 border-t border-border pt-3 min-[701px]:hidden">
            {NAV_LINKS.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                className="rounded-lg px-2 py-2 font-semibold text-foreground no-underline hover:bg-muted"
              >
                {link.label}
              </Link>
            ))}
            <Button asChild className="mt-2 h-10 text-base">
              <Link to="/login">Connexion</Link>
            </Button>
          </nav>
        )}
      </div>
    </div>
  );
}
