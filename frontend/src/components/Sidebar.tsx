import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import { Mark } from "../Logo";

type SidebarProps = {
  children: ReactNode;
};

export function Sidebar({ children }: SidebarProps) {
  return (
    <aside className="sidebar">
      <Link to="/" className="sidebar-brand" aria-label="NomiaMD home">
        <Mark size={26} />
      </Link>
      <nav className="sidebar-nav">{children}</nav>
    </aside>
  );
}

type NavItemProps = {
  to: string;
  children: ReactNode;
};

export function NavItem({ to, children }: NavItemProps) {
  return (
    <NavLink to={to} className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
      {children}
    </NavLink>
  );
}

type SidebarFooterProps = {
  children: ReactNode;
};

export function SidebarFooter({ children }: SidebarFooterProps) {
  return <div className="sidebar-footer">{children}</div>;
}
