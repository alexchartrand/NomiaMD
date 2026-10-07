import { Link, useNavigate } from "react-router-dom";
import { LogOut } from "lucide-react";
import { useAuth } from "../../../AuthContext";
import { useSidebarCollapsed } from "../../../components";
import { cn } from "@/lib/utils";

// "Alex Chartrand" → "AC".
function initials(fullName: string): string {
  const parts = fullName.replace(/^(dre?|dr\.)\s+/i, "").split(/\s+/).filter(Boolean);
  return (parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "");
}

// Who is signed in (opens the profile) and the way out, at the foot of the sidebar. Folded,
// just the initials over the way out.
export function UserMenu() {
  const navigate = useNavigate();
  const collapsed = useSidebarCollapsed();
  const { user, logout } = useAuth();

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  if (!user) return null;
  return (
    <div className={cn("flex items-center gap-1", collapsed && "flex-col")}>
      <Link
        to="/app/profile"
        className={cn(
          "flex min-w-0 items-center gap-2.5 rounded-lg px-2 py-1.5 no-underline transition-colors hover:bg-accent",
          !collapsed && "flex-1",
        )}
        aria-label={`Profil — ${user.full_name}`}
        title="Profil"
      >
        <span
          aria-hidden
          className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground uppercase"
        >
          {initials(user.full_name)}
        </span>
        <span className={collapsed ? "sr-only" : "flex min-w-0 flex-col leading-tight"}>
          <span className="truncate text-sm font-semibold text-foreground">{user.full_name}</span>
          <span className="truncate text-xs text-muted-foreground">
            {user.practice_number ? `No de pratique ${user.practice_number}` : "Profil"}
          </span>
        </span>
      </Link>
      <button
        type="button"
        onClick={handleLogout}
        aria-label="Se déconnecter"
        title="Se déconnecter"
        className="inline-flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-lg border-none bg-transparent text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
      >
        <LogOut aria-hidden className="size-4" />
      </button>
    </div>
  );
}
