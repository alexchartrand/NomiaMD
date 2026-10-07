import { createContext, useContext, type ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { PanelLeftClose, PanelLeftOpen, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { useStoredFlag } from "@/lib/useStoredFlag";
import { Logo, Mark } from "../Logo";

// Folded down to an icon rail: labels stay in the accessibility tree (screen-reader only) and
// show as tooltips, so every link keeps its name.
const SidebarCollapsedContext = createContext(false);

// For what sits in the sidebar (its items, the footer's user menu) to lay itself out folded.
export function useSidebarCollapsed(): boolean {
  return useContext(SidebarCollapsedContext);
}

type SidebarProps = {
  children: ReactNode;
  footer?: ReactNode;
};

export function Sidebar({ children, footer }: SidebarProps) {
  const [collapsed, setCollapsed] = useStoredFlag("nomiamd.sidebar.collapsed");
  const ToggleIcon = collapsed ? PanelLeftOpen : PanelLeftClose;
  const toggleLabel = collapsed ? "Déplier le menu" : "Replier le menu";

  return (
    <SidebarCollapsedContext.Provider value={collapsed}>
      <aside
        className={cn(
          "flex shrink-0 flex-col overflow-x-hidden overflow-y-auto border-r border-border bg-card px-3 pt-5 pb-3 transition-[width] duration-200",
          collapsed ? "w-[64px]" : "w-[240px]",
        )}
      >
        <div className={cn("mb-6 flex items-center gap-1", collapsed ? "flex-col gap-3" : "justify-between")}>
          <Link to="/app" className="inline-flex px-2.5 py-1" aria-label="NomiaMD accueil">
            {collapsed ? <Mark size={26} /> : <Logo size={26} />}
          </Link>
          <button
            type="button"
            onClick={() => setCollapsed(!collapsed)}
            aria-label={toggleLabel}
            aria-expanded={!collapsed}
            title={toggleLabel}
            className="inline-flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-lg border-none bg-transparent text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <ToggleIcon aria-hidden className="size-[18px]" />
          </button>
        </div>
        <nav aria-label="Navigation principale" className="flex flex-1 flex-col gap-5">
          {children}
        </nav>
        {footer && <div className="mt-4 border-t border-border pt-3">{footer}</div>}
      </aside>
    </SidebarCollapsedContext.Provider>
  );
}

// A titled group of links ("Référence RAMQ"); untitled for the first one.
// Folded, the title gives way to a rule between the groups.
export function NavSection({ title, children }: { title?: string; children: ReactNode }) {
  const collapsed = useSidebarCollapsed();
  return (
    <div className="flex flex-col gap-0.5">
      {title &&
        (collapsed ? (
          <span role="separator" aria-label={title} className="mx-2 mb-1 h-px bg-border" />
        ) : (
          <span className="px-2.5 pb-1 text-[0.7rem] font-semibold tracking-wider text-muted-foreground uppercase">
            {title}
          </span>
        ))}
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
  const collapsed = useSidebarCollapsed();
  const activeElsewhere = alsoActiveOn.some((path) => pathname.startsWith(path));
  return (
    <NavLink
      to={to}
      end={end}
      title={collapsed && typeof children === "string" ? children : undefined}
      className={({ isActive }) =>
        cn(
          "group relative flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium whitespace-nowrap text-muted-foreground no-underline transition-colors hover:bg-accent hover:text-foreground",
          collapsed && "justify-center",
          (isActive || activeElsewhere) && "bg-accent font-semibold text-primary hover:text-primary",
        )
      }
    >
      <Icon aria-hidden className="size-[18px] shrink-0" />
      <span className={collapsed ? "sr-only" : "flex-1"}>{children}</span>
      {count != null && count > 0 && collapsed && (
        // No room for the number: a dot on the icon says something waits there.
        <span aria-hidden className="absolute top-1.5 right-2 size-2 rounded-full bg-primary ring-2 ring-card" />
      )}
      {count != null && count > 0 && !collapsed && (
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
