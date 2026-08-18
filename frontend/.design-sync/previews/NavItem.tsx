import { NavItem } from "facturemd-frontend";

export function Default() {
  return (
    <div style={{ width: 220, padding: "0.5rem", background: "var(--color-surface)" }}>
      <NavItem to="/app/extraction">Extraction de codes</NavItem>
    </div>
  );
}
