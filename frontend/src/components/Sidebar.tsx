import type { ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { Logo } from "../Logo";

type SidebarProps = {
  children: ReactNode;
  footer?: ReactNode;
};

export function Sidebar({ children, footer }: SidebarProps) {
  return (
    <aside className="flex w-[240px] shrink-0 flex-col overflow-y-auto border-r border-border bg-card px-3 pt-5 pb-3">
      <Link to="/app" className="mb-6 inline-flex px-2.5 py-1" aria-label="NomiaMD accueil">
        <Logo size={26} />
      </Link>
      <nav aria-label="Navigation principale" className="flex flex-1 flex-col gap-5">
        {children}
      </nav>
      {footer && <div className="mt-4 border-t border-border pt-3">{footer}</div>}
    </aside>
  );
}

// A titled group of links ("Référence RAMQ"); untitled for the first one.
export function NavSection({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      {title && (
        <span className="px-2.5 pb-1 text-[0.7rem] font-semibold tracking-wider text-muted-foreground uppercase">
          {title}
        </span>
      )}
      {children}
    </div>
  );
}

type NavItemProps = {
  to: string;
  icon: LucideIcon;
  children: ReactNode;
  // Active only on `to` itself, not on the pages below it (the dashboard at /app).
  end?: boolean;
  // Other pages this item stands for, without a nav item of their own (/app/facturer).
  alsoActiveOn?: string[];
  // How many things wait there (notes to handle…): a pill on the right, hidden at 0. Visual
  // only — the dashboard says the same in words.
  count?: number | null;
};

export function NavItem({ to, icon: Icon, children, end, alsoActiveOn = [], count }: NavItemProps) {
  const { pathname } = useLocation();
  const activeElsewhere = alsoActiveOn.some((path) => pathname.startsWith(path));
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        cn(
          "group flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium text-muted-foreground no-underline transition-colors hover:bg-accent hover:text-foreground",
          (isActive || activeElsewhere) && "bg-accent font-semibold text-primary hover:text-primary",
        )
      }
    >
      <Icon aria-hidden className="size-[18px] shrink-0" />
      <span className="flex-1">{children}</span>
      {count != null && count > 0 && (
        <span
          aria-hidden
          className="min-w-5 rounded-full bg-primary px-1.5 py-px text-center text-[0.7rem] font-bold tabular-nums text-primary-foreground"
        >
          {count}
        </span>
      )}
    </NavLink>
  );
}
