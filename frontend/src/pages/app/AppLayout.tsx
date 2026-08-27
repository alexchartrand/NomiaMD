import { Outlet, useNavigate } from "react-router-dom";
import { NavItem, Sidebar, SidebarFooter } from "../../components";
import { useAuth } from "../../AuthContext";

export default function AppLayout() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar>
        <NavItem to="/app/extraction">Réclamation</NavItem>
        <NavItem to="/app/facturation">Facturation</NavItem>
        <NavItem to="/app/chat">Clavardage</NavItem>
        <NavItem to="/app/patients">Patients</NavItem>
        <NavItem to="/app/profile">Profil</NavItem>
        <SidebarFooter>
          {user && (
            <span className="block px-3 pt-1 pb-2 text-sm font-semibold text-muted-foreground">
              {user.full_name}
            </span>
          )}
          <button
            type="button"
            onClick={handleLogout}
            className="block w-full cursor-pointer rounded-lg border-none bg-transparent px-3 py-2 text-left text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            Se déconnecter
          </button>
        </SidebarFooter>
      </Sidebar>
      <div className="min-w-0 flex-1 overflow-y-auto py-10 px-12">
        <Outlet />
      </div>
    </div>
  );
}
