import { Link } from "react-router-dom";
import { Logo } from "@/Logo";
import { SITE } from "@/site/config";

const COLUMNS = [
  {
    title: "Produit",
    links: [
      { to: "/#fonctionnement", label: "Fonctionnement" },
      { to: "/prix", label: "Tarifs" },
      { to: "/#faq", label: "Questions fréquentes" },
    ],
  },
  {
    title: "Mentions légales",
    links: [
      { to: "/securite", label: "Sécurité" },
      { to: "/confidentialite", label: "Politique de confidentialité" },
    ],
  },
  {
    title: "Nous joindre",
    links: [{ to: "/contact", label: "Contact" }],
  },
];

export function SiteFooter() {
  return (
    <footer className="border-t border-border bg-card">
      <div className="mx-auto grid max-w-[1080px] grid-cols-1 gap-10 px-6 pt-12 pb-8 min-[701px]:grid-cols-[1.4fr_1fr_1fr_1.2fr]">
        <div>
          <Logo size={30} />
          <p className="mt-3 max-w-[18rem] text-sm text-muted-foreground">
            La facturation RAMQ simplifiée pour les médecins du Québec.
          </p>
        </div>
        {COLUMNS.map((column) => (
          <div key={column.title}>
            <h2 className="mb-3 font-heading text-sm font-[650] text-foreground">{column.title}</h2>
            <ul className="m-0 flex list-none flex-col gap-2 p-0">
              {column.links.map((link) => (
                <li key={link.to}>
                  <Link to={link.to} className="text-sm text-muted-foreground no-underline hover:text-primary">
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="mx-auto max-w-[1080px] px-6">
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border py-5 text-[0.8rem] text-muted-foreground">
          <span>Conçu au {SITE.region}</span>
          <span>
            © {new Date().getFullYear()} {SITE.name}
          </span>
        </div>
      </div>
    </footer>
  );
}
