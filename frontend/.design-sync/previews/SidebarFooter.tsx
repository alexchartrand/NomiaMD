import { SidebarFooter } from "facturemd-frontend";

export function Default() {
  return (
    <div style={{ width: 220, background: "var(--color-surface)" }}>
      <SidebarFooter>
        <a className="nav-item logout-link" href="/">
          Se déconnecter
        </a>
      </SidebarFooter>
    </div>
  );
}
