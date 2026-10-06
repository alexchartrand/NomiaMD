import { Outlet, useNavigate } from "react-router-dom";
import { NavItem, Sidebar, SidebarFooter } from "../../components";
import { useAuth } from "../../AuthContext";
import { RamqChatProvider } from "../../chat/RamqChatProvider";

export default function AppLayout() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  return (
    // The page scrolls inside the content column, not the window: the sidebar stays put and
    // `sticky` elements (the review's save bar, the dashboard's assistant) stick to the screen.
    <div className="flex h-dvh">
      <Sidebar>
        <NavItem to="/app" end>
          Tableau de bord
        </NavItem>
        <NavItem to="/app/inbox">Rencontres</NavItem>
        <NavItem to="/app/facturation">Facturation</NavItem>
        <NavItem to="/app/facturer">Facturer</NavItem>
        <NavItem to="/app/codes">Codes RAMQ</NavItem>
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
      {/* Padded inside the scroll container, not on it: `sticky` offsets count from its padding edge. */}
      <div className="min-w-0 flex-1 overflow-y-auto">
        <div className="py-10 px-12">
          <RamqChatProvider>
            <Outlet />
          </RamqChatProvider>
        </div>
      </div>
    </div>
  );
}
