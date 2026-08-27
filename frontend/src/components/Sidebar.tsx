import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import { cn } from "@/lib/utils";
import { Logo } from "../Logo";

type SidebarProps = {
  children: ReactNode;
};

export function Sidebar({ children }: SidebarProps) {
  return (
    <aside className="flex w-[220px] shrink-0 flex-col gap-6 border-r border-border bg-card p-4 pt-6">
      <Link to="/app" className="inline-flex p-1" aria-label="NomiaMD accueil">
        <Logo size={26} />
      </Link>
      <nav className="flex flex-1 flex-col gap-1">{children}</nav>
    </aside>
  );
}

type NavItemProps = {
  to: string;
  children: ReactNode;
};

export function NavItem({ to, children }: NavItemProps) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn(
          "block rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground no-underline transition-colors hover:bg-accent hover:text-foreground",
          isActive && "bg-accent font-semibold text-primary hover:text-primary",
        )
      }
    >
      {children}
    </NavLink>
  );
}

type SidebarFooterProps = {
  children: ReactNode;
};

export function SidebarFooter({ children }: SidebarFooterProps) {
  return <div className="mt-auto border-t border-border pt-4">{children}</div>;
}
