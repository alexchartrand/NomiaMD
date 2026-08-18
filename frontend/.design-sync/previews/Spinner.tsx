import { Spinner } from "facturemd-frontend";

export function WithLabel() {
  return (
    <div style={{ padding: 16 }}>
      <Spinner label="Réflexion…" />
    </div>
  );
}

export function Bare() {
  return (
    <div style={{ padding: 16 }}>
      <Spinner />
    </div>
  );
}
