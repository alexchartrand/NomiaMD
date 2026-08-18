import { NavItem, Sidebar, SidebarFooter } from "facturemd-frontend";

export function AppNav() {
  return (
    <Sidebar>
      <NavItem to="/app/extraction">Extraction de codes</NavItem>
      <NavItem to="/app/chat">Clavardage</NavItem>
      <SidebarFooter>
        <a className="nav-item logout-link" href="/">
          Se déconnecter
        </a>
      </SidebarFooter>
    </Sidebar>
  );
}
