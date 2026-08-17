import { Link, Outlet } from "react-router-dom";
import { NavItem, Sidebar, SidebarFooter } from "../../components";

export default function AppLayout() {
  return (
    <div className="app-layout">
      <Sidebar>
        <NavItem to="/app/extraction">Extraction de codes</NavItem>
        <NavItem to="/app/chat">Clavardage</NavItem>
        <SidebarFooter>
          <Link to="/" className="nav-item logout-link">
            Se déconnecter
          </Link>
        </SidebarFooter>
      </Sidebar>
      <div className="app-content">
        <Outlet />
      </div>
    </div>
  );
}
