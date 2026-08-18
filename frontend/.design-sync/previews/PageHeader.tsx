import { Button, PageHeader } from "facturemd-frontend";

export function WithTagline() {
  return <PageHeader tagline="Extraction de codes de facturation — brouillon à réviser" />;
}

export function WithActions() {
  return <PageHeader actions={<Button variant="secondary">Se connecter</Button>} />;
}
