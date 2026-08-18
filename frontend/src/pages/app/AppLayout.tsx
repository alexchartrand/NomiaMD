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
    <div className="app-layout">
      <Sidebar>
        <NavItem to="/app/extraction">Extraction de codes</NavItem>
        <NavItem to="/app/chat">Clavardage</NavItem>
        <SidebarFooter>
          {user && <span className="sidebar-user">{user.full_name}</span>}
          <button type="button" onClick={handleLogout} className="nav-item logout-link">
            Se déconnecter
          </button>
        </SidebarFooter>
      </Sidebar>
      <div className="app-content">
        <Outlet />
      </div>
    </div>
  );
}
